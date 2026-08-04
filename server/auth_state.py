"""In-process cache of the authentication state.

The middleware runs on every request and cannot open a database session just to ask
whether credentials exist. Only the endpoints that change it invalidate this.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

# While there are no credentials the database is re-checked at most every N seconds, so a
# worker that did not serve the wizard finds out quickly. Once configured, never again.
NEGATIVE_TTL_SEC = 5.0


@dataclass(frozen=True)
class AuthSnapshot:
    configured: bool
    token_version: int
    # The username the cookie has to name. token_version alone does not identify an
    # account: wiping the credentials and running the wizard again starts back at 1, so a
    # cookie issued to the previous account still matched.
    username: str | None = None


_lock = threading.Lock()
_configured: bool | None = None
_token_version: int = 0
_username: str | None = None
_checked_at: float = 0.0


def _load_from_db() -> tuple[bool, int, str | None]:
    # Deferred import: server.database imports server.config, and both the app and the
    # tests load this module before the schema exists.
    from server.database import session_scope
    from server.services.auth import get_credentials

    try:
        with session_scope() as db:
            row = get_credentials(db)
            if row is None:
                return (False, 0, None)
            return (True, row.token_version, row.username)
    except Exception:  # noqa: BLE001 - the table may not exist yet
        return (False, 0, None)


def get_snapshot() -> AuthSnapshot:
    global _configured, _token_version, _username, _checked_at

    with _lock:
        configured = _configured
        token_version = _token_version
        username = _username
        stale = (time.monotonic() - _checked_at) >= NEGATIVE_TTL_SEC

    if configured is None or (configured is False and stale):
        loaded, version, loaded_user = _load_from_db()
        with _lock:
            # Another thread may have completed the wizard while we queried: a cached
            # True never degrades back to False.
            if not _configured:
                _configured = loaded
                _token_version = version
                _username = loaded_user
            _checked_at = time.monotonic()
            configured = bool(_configured)
            token_version = _token_version
            username = _username

    return AuthSnapshot(
        configured=bool(configured), token_version=token_version, username=username
    )


def prime(*, configured: bool, token_version: int, username: str | None = None) -> None:
    """Set the known state at startup, so the first request does not have to query."""
    global _configured, _token_version, _username, _checked_at
    with _lock:
        _configured = configured
        _token_version = token_version
        _username = username
        _checked_at = time.monotonic()


def mark_configured(*, token_version: int, username: str | None = None) -> None:
    """The wizard has just created the credentials."""
    prime(configured=True, token_version=token_version, username=username)


def bump_token_version(version: int, username: str | None = None) -> None:
    """Credentials changed: sessions on the previous version stop being valid."""
    prime(configured=True, token_version=version, username=username)


def reset_for_tests() -> None:
    """Back to the freshly imported state."""
    global _configured, _token_version, _username, _checked_at
    with _lock:
        _configured = None
        _token_version = 0
        _username = None
        _checked_at = 0.0
