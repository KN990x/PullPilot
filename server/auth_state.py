"""Caché en proceso del estado de autenticación.

El middleware corre en cada petición: no puede abrir una sesión de base de datos solo
para preguntar si ya hay credenciales. Aquí se guarda la respuesta y solo la invalidan
los endpoints que la cambian.

También es el punto donde los tests manipulan el estado. La configuración se congela al
importar `server.config`, así que un test no puede cambiar ALLOW_NO_AUTH: en su lugar
usa `set_open_access()`.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from server.config import ALLOW_NO_AUTH

# Mientras no hay credenciales se reconsulta la base de datos como mucho cada N segundos.
# Es lo que hace correcto el caso de varios workers: el que no atendió el asistente se
# entera enseguida. Una vez configurado ya no se vuelve a consultar nunca.
NEGATIVE_TTL_SEC = 5.0


@dataclass(frozen=True)
class AuthSnapshot:
    configured: bool
    open_access: bool
    token_version: int


_lock = threading.Lock()
_configured: bool | None = None
_token_version: int = 0
_open_access: bool = ALLOW_NO_AUTH
_checked_at: float = 0.0


def _load_from_db() -> tuple[bool, int]:
    # Import diferido: server.database importa server.config, y este módulo lo cargan
    # tanto la app como los tests antes de que exista el esquema.
    from server.database import session_scope
    from server.services.auth import get_credentials

    try:
        with session_scope() as db:
            row = get_credentials(db)
            return (row is not None, row.token_version if row else 0)
    except Exception:  # noqa: BLE001 - la tabla puede no existir todavía
        return (False, 0)


def get_snapshot() -> AuthSnapshot:
    global _configured, _token_version, _checked_at

    with _lock:
        open_access = _open_access
        configured = _configured
        token_version = _token_version
        stale = (time.monotonic() - _checked_at) >= NEGATIVE_TTL_SEC

    if configured is None or (configured is False and stale):
        loaded, version = _load_from_db()
        with _lock:
            # Otro hilo pudo completar el asistente mientras consultábamos: un True ya
            # cacheado nunca se degrada a False.
            if not _configured:
                _configured = loaded
                _token_version = version
            _checked_at = time.monotonic()
            configured = bool(_configured)
            token_version = _token_version

    return AuthSnapshot(
        configured=bool(configured),
        open_access=open_access,
        token_version=token_version,
    )


def prime(*, configured: bool, token_version: int) -> None:
    """Fija el estado conocido al arrancar, para no consultar en la primera petición."""
    global _configured, _token_version, _checked_at
    with _lock:
        _configured = configured
        _token_version = token_version
        _checked_at = time.monotonic()


def mark_configured(*, token_version: int) -> None:
    """El asistente acaba de crear las credenciales."""
    prime(configured=True, token_version=token_version)


def bump_token_version(version: int) -> None:
    """Las credenciales cambiaron: las sesiones con la versión anterior dejan de valer."""
    prime(configured=True, token_version=version)


def set_open_access(value: bool) -> None:
    """Escotilla ALLOW_NO_AUTH. Separada de `prime` para que los tests la controlen."""
    global _open_access
    with _lock:
        _open_access = value


def reset_for_tests() -> None:
    """Vuelve al estado recién importado. No toca `open_access`."""
    global _configured, _token_version, _checked_at
    with _lock:
        _configured = None
        _token_version = 0
        _checked_at = 0.0
