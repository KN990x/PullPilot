"""Credentials: scrypt hashing (stdlib) and the lifecycle of the single row.

Only one set of credentials can exist, hence everything revolving around AUTH_ROW_ID. The
setup wizard creates it; from then on the database is the only source of truth.
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

# 16 MiB and ~25 ms on a desktop CPU, 100-200 ms on a Raspberry Pi 4: login stays
# imperceptible while an offline GPU attack does not. 2^15 would need an explicit maxmem
# (OpenSSL's default 32 MiB rejects it) and, with FastAPI's 40-thread pool, peak at 1.2 GiB.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024
_ALGO = "scrypt"

# Sanity bounds when verifying: a tampered hash with a huge n would turn login itself into
# a memory bomb.
_MAX_VERIFY_N = 2**20
_MAX_VERIFY_R = 32
_MAX_VERIFY_P = 16

_USERNAME_RE = re.compile(USERNAME_PATTERN)

# Keeps two requests in the same process off the INSERT at once. The cross-process race is
# cut by the primary key; this only avoids the IntegrityError in the common case.
_setup_lock = threading.Lock()


class AuthError(Exception):
    """Base class for the authentication domain errors."""


class SetupAlreadyCompletedError(AuthError):
    """Credentials already exist: the wizard cannot run again."""


class SetupRequiredError(AuthError):
    """No credentials yet."""


class InvalidCredentialsError(AuthError):
    """Wrong username or password."""


def validate_username(value: str) -> str:
    """Normalise and validate the username. ValueError with the reason if it fails."""
    cleaned = (value or "").strip()
    if len(cleaned) < USERNAME_MIN_LEN or len(cleaned) > USERNAME_MAX_LEN:
        raise ValueError(
            f"El usuario debe tener entre {USERNAME_MIN_LEN} y {USERNAME_MAX_LEN} caracteres"
        )
    if not _USERNAME_RE.match(cleaned):
        raise ValueError("El usuario solo admite letras, números y . _ @ + -")
    return cleaned


def validate_password(value: str) -> str:
    """Validate the password. Not stripped: whitespace is part of the password."""
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
    """Return 'scrypt$n$r$p$salt_b64$hash_b64'.

    The parameters travel inside the hash, so they can be hardened later without
    invalidating the hashes already stored.
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
    """Constant-time comparison. False (and a warning) if `stored` is corrupt."""
    parts = (stored or "").split("$")
    if len(parts) != 6 or parts[0] != _ALGO:
        logger.warning("Hash de contraseña con formato desconocido; se rechaza el acceso.")
        return False

    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        # binascii.Error subclasses ValueError, so invalid base64 lands here too.
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
    """Create the single row. SetupAlreadyCompletedError if it already exists."""
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
            # Another process won the race between the SELECT and the INSERT.
            db.rollback()
            raise SetupAlreadyCompletedError from None
        except SQLAlchemyError:
            db.rollback()
            raise
        db.refresh(row)
        return row


def verify_credentials(db: Session, *, username: str, password: str) -> bool:
    """False if there are no credentials, the username differs or the password fails."""
    row = get_credentials(db)
    if row is None:
        return False

    user_ok = hmac.compare_digest(
        (username or "").strip().encode("utf-8"),
        row.username.encode("utf-8"),
    )
    # The KDF always runs, even for the wrong username: otherwise response time would
    # give away which username is the right one.
    pass_ok = verify_password(password, row.password_hash)
    return user_ok and pass_ok


def change_credentials(
    db: Session,
    *,
    current_password: str,
    new_username: str | None = None,
    new_password: str | None = None,
) -> AuthCredential:
    """Change username and/or password, requiring the current password."""
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

    # Invalidates every cookie issued before this change.
    row.token_version += 1
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(row)
    return row
