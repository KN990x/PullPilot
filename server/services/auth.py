"""Credenciales de acceso: hashing con scrypt (stdlib) y ciclo de vida de la fila única.

Solo puede existir un juego de credenciales, por eso todo gira alrededor de la fila con
id = AUTH_ROW_ID. La crea el asistente de primera instalación y a partir de ahí manda la
base de datos: no hay ninguna variable de entorno que pueda cambiarlas.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from server.auth_policy import (
    PASSWORD_MAX_LEN,
    PASSWORD_MIN_LEN,
    USERNAME_MAX_LEN,
    USERNAME_MIN_LEN,
    USERNAME_PATTERN,
)
from server.config import logger
from server.models.db import AUTH_ROW_ID, AuthCredential

# n=2^14, r=8, p=1 => 128*n*r = 16 MiB y ~25 ms en un x86/ARM64 de escritorio, del orden
# de 100-200 ms en una Raspberry Pi 4. Es el punto donde el login sigue siendo
# imperceptible y un ataque offline con GPU deja de ser cómodo. Subir a 2^15 duplicaría
# tiempo y memoria y además exige maxmem explícito: el límite por defecto de OpenSSL son
# 32 MiB y rechaza el cálculo. Ojo al pico agregado: el threadpool de FastAPI son 40
# hilos, o sea hasta 640 MiB si llegan 40 logins a la vez.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024
_ALGO = "scrypt"

# Cotas de cordura al verificar: un hash manipulado en la base de datos con un n enorme
# sería una bomba de memoria en el propio login.
_MAX_VERIFY_N = 2**20
_MAX_VERIFY_R = 32
_MAX_VERIFY_P = 16

_USERNAME_RE = re.compile(USERNAME_PATTERN)

# Evita que dos peticiones del mismo proceso lleguen a la vez al INSERT. La carrera entre
# procesos la corta la clave primaria; esto solo ahorra el IntegrityError en el caso común.
_setup_lock = threading.Lock()


class AuthError(Exception):
    """Base de los errores de dominio de autenticación."""


class SetupAlreadyCompletedError(AuthError):
    """Ya existen credenciales: el asistente no puede volver a ejecutarse."""


class SetupRequiredError(AuthError):
    """Todavía no hay credenciales."""


class InvalidCredentialsError(AuthError):
    """Usuario o contraseña incorrectos."""


def validate_username(value: str) -> str:
    """Normaliza y valida el usuario. ValueError con el motivo si no cumple."""
    cleaned = (value or "").strip()
    if len(cleaned) < USERNAME_MIN_LEN or len(cleaned) > USERNAME_MAX_LEN:
        raise ValueError(
            f"El usuario debe tener entre {USERNAME_MIN_LEN} y {USERNAME_MAX_LEN} caracteres"
        )
    if not _USERNAME_RE.match(cleaned):
        raise ValueError("El usuario solo admite letras, números y . _ @ + -")
    return cleaned


def validate_password(value: str) -> str:
    """Valida la contraseña. No se hace strip: los espacios son parte de la contraseña."""
    if not value or len(value) < PASSWORD_MIN_LEN:
        raise ValueError(f"La contraseña debe tener al menos {PASSWORD_MIN_LEN} caracteres")
    if len(value) > PASSWORD_MAX_LEN:
        raise ValueError(f"La contraseña no puede superar {PASSWORD_MAX_LEN} caracteres")
    return value


def hash_password(
    password: str,
    *,
    n: int = SCRYPT_N,
    r: int = SCRYPT_R,
    p: int = SCRYPT_P,
) -> str:
    """Devuelve 'scrypt$n$r$p$salt_b64$hash_b64'.

    Los parámetros viajan dentro del hash, así que se pueden endurecer en el futuro sin
    invalidar los hashes ya almacenados.
    """
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )
    return "$".join(
        [
            _ALGO,
            str(n),
            str(r),
            str(p),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(derived).decode("ascii"),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    """Comparación en tiempo constante. False (con aviso) si `stored` está corrupto."""
    parts = (stored or "").split("$")
    if len(parts) != 6 or parts[0] != _ALGO:
        logger.warning("Hash de contraseña con formato desconocido; se rechaza el acceso.")
        return False

    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        # binascii.Error hereda de ValueError, así que un base64 inválido cae aquí.
        salt = base64.b64decode(parts[4], validate=True)
        expected = base64.b64decode(parts[5], validate=True)
    except ValueError:
        logger.warning("Hash de contraseña ilegible; se rechaza el acceso.")
        return False

    if not salt or not expected:
        logger.warning("Hash de contraseña sin sal o sin digest; se rechaza el acceso.")
        return False

    if not (0 < n <= _MAX_VERIFY_N and 0 < r <= _MAX_VERIFY_R and 0 < p <= _MAX_VERIFY_P):
        logger.warning("Hash de contraseña con parámetros fuera de rango; se rechaza el acceso.")
        return False

    try:
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=SCRYPT_MAXMEM,
        )
    except ValueError:
        logger.warning("No se pudo recalcular el hash de contraseña; se rechaza el acceso.")
        return False

    return hmac.compare_digest(derived, expected)


def get_credentials(db: Session) -> AuthCredential | None:
    return db.get(AuthCredential, AUTH_ROW_ID)


def is_setup_complete(db: Session) -> bool:
    return get_credentials(db) is not None


def create_initial_credentials(
    db: Session, *, username: str, password: str
) -> AuthCredential:
    """Alta de la fila única. SetupAlreadyCompletedError si ya existe."""
    clean_user = validate_username(username)
    validate_password(password)

    with _setup_lock:
        if is_setup_complete(db):
            raise SetupAlreadyCompletedError

        row = AuthCredential(
            id=AUTH_ROW_ID,
            username=clean_user,
            password_hash=hash_password(password),
            token_version=1,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            # Otro proceso ganó la carrera entre el SELECT y el INSERT.
            db.rollback()
            raise SetupAlreadyCompletedError from None
        except SQLAlchemyError:
            db.rollback()
            raise
        db.refresh(row)
        return row


def verify_credentials(db: Session, *, username: str, password: str) -> bool:
    """False si no hay credenciales, si el usuario no coincide o si la contraseña falla."""
    row = get_credentials(db)
    if row is None:
        return False

    user_ok = hmac.compare_digest(
        (username or "").strip().encode("utf-8"),
        row.username.encode("utf-8"),
    )
    # El KDF se ejecuta siempre, también con el usuario equivocado: si no, el tiempo de
    # respuesta delataría cuál es el usuario correcto.
    pass_ok = verify_password(password, row.password_hash)
    return user_ok and pass_ok


def change_credentials(
    db: Session,
    *,
    current_password: str,
    new_username: str | None = None,
    new_password: str | None = None,
) -> AuthCredential:
    """Cambia usuario y/o contraseña exigiendo la contraseña actual."""
    row = get_credentials(db)
    if row is None:
        raise SetupRequiredError

    if not verify_password(current_password, row.password_hash):
        raise InvalidCredentialsError

    changed = False

    if new_username is not None:
        clean_user = validate_username(new_username)
        if clean_user != row.username:
            row.username = clean_user
            changed = True

    if new_password is not None:
        validate_password(new_password)
        row.password_hash = hash_password(new_password)
        changed = True

    if not changed:
        raise ValueError("No hay nada que cambiar")

    # Invalida las cookies emitidas antes de este cambio.
    row.token_version += 1
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(row)
    return row
