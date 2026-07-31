"""Persistence of the session signing secret.

Stdlib only and outside config.py on purpose: database.py imports config.py, so any extra
import here would close a cycle. Same reason the secret is a file and not a table —
SessionMiddleware gets the key while server/app.py is still being imported, before the
database has any tables.
"""

from __future__ import annotations

import contextlib
import logging
import os
import secrets
import stat
from pathlib import Path
from typing import Literal

SecretSource = Literal["env", "file", "ephemeral"]

SECRET_FILENAME = "session_secret.key"
# A valid secret is 64 hex chars; the minimum catches a file another worker is halfway
# through writing.
_MIN_SECRET_LEN = 32
_MAX_ATTEMPTS = 3

logger = logging.getLogger("pullpilot")


def load_or_create_session_secret(
    data_dir: Path, env_value: str | None = None
) -> tuple[str, SecretSource]:
    """Return (secret, source).

    Reuses the persisted file in `data_dir` or creates one, so sessions survive restarts
    with nothing to configure. `env_value` wins when given (tests only).
    """
    if env_value:
        return env_value, "env"

    path = data_dir / SECRET_FILENAME

    # Several passes because another worker can slip in between our read and our link:
    # if it wins, the next pass just reads what it wrote.
    for _ in range(_MAX_ATTEMPTS):
        existing = _read_secret(path)
        if existing is not None:
            _warn_if_group_or_world_readable(path)
            return existing, "file"

        # The target only ever appears through an atomic link(), so an unreadable file
        # is real corruption, not a half-written one. Replace it, or the install would
        # never have persistent sessions again.
        corrupt = path.exists()
        if corrupt:
            logger.warning(
                "%s no contiene un secreto válido; se regenera y las sesiones abiertas "
                "dejarán de valer.",
                path,
            )

        created = _create_secret(path, overwrite=corrupt)
        if created is not None:
            return created, "file"

    # No usable file (read-only volume, permissions, race lost three times): start
    # anyway with an in-memory secret. A badly mounted volume should boot and complain,
    # not refuse to exist.
    return secrets.token_hex(32), "ephemeral"


def _read_secret(path: Path) -> str | None:
    """None if it does not exist, is truncated or cannot be read."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if len(raw) < _MIN_SECRET_LEN:
        return None
    return raw


def _create_secret(path: Path, *, overwrite: bool = False) -> str | None:
    """Create the file atomically.

    None if another process won the race or the filesystem refused. `overwrite` clobbers
    whatever is there: only for replacing a corrupt file.
    """
    secret = secrets.token_hex(32)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")

    try:
        # Mode applied at creation: there is never a window with the file at 0644.
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError:
        return None

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(secret)
            handle.flush()
            os.fsync(handle.fileno())

        # link() is atomic and fails if the target exists — exactly "create with this
        # content or tell me it is already there". os.replace would clobber a secret
        # another worker just wrote, so it is only used on a file known to be corrupt.
        try:
            if overwrite:
                os.replace(tmp, path)
            else:
                os.link(tmp, path)
        except FileExistsError:
            return None
        except OSError:
            return None
        return secret
    except OSError:
        return None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)


def _warn_if_group_or_world_readable(path: Path) -> None:
    """Warn (do not fix) if the file ended up readable by anyone but its owner."""
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return
    if mode & 0o077:
        logger.warning(
            "%s tiene permisos %o: cualquiera que lo lea puede falsificar sesiones. "
            "Ajusta los permisos a 600.",
            path,
            mode,
        )
