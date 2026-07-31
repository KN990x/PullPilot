"""Authentication endpoints.

The path operations are sync (`def`, not `async def`) on purpose: FastAPI runs those in
the threadpool, so scrypt's 25-200 ms never blocks the event loop. With `async def` every
login would freeze the whole server.
"""

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from server import auth_state
from server.config import TRUST_X_FORWARDED_FOR
from server.database import get_db
from server.login_rate_limit import (
    ClientIdentity,
    clear_login_failures,
    is_login_rate_limited,
    record_login_failure,
    seconds_until_reset,
)
from server.models.db import AuthCredential
from server.models.schemas import (
    AuthResultOut,
    AuthStatusOut,
    CredentialsInput,
    LoginInput,
    SetupInput,
)
from server.services import auth as auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])
# Old routes, kept only so bookmarks and PWAs on the previous bundle do not hit a 404 or
# a redirect loop.
legacy_router = APIRouter(tags=["auth"])


def _client_identity(request: Request) -> ClientIdentity:
    """The IP we act on plus the socket it really came from.

    `X-Forwarded-For` is sent by the client, so on its own it is a way to get a fresh
    rate-limit bucket per request. The peer is kept alongside it as the identity nobody
    can forge; see server/login_rate_limit.py.
    """
    peer = request.client.host if request.client else "unknown"
    reported = peer
    if TRUST_X_FORWARDED_FOR:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            reported = xff.split(",")[0].strip() or peer
    return ClientIdentity(reported_ip=reported, peer_ip=peer)


def _error(status_code: int, detail: str, code: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail, "code": code, **extra})


def _rate_limited(who: ClientIdentity) -> JSONResponse:
    retry_after = seconds_until_reset(who)
    response = _error(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Demasiados intentos. Inténtalo más tarde.",
        "rate_limited",
        retry_after=retry_after,
    )
    response.headers["Retry-After"] = str(retry_after)
    return response


def _open_session(request: Request, row: AuthCredential) -> None:
    # clear() before writing: the new session inherits nothing from the old one.
    request.session.clear()
    request.session["user"] = row.username
    request.session["v"] = row.token_version


@router.get("/status", response_model=AuthStatusOut)
def auth_status(request: Request, db: Session = Depends(get_db)):
    """SPA bootstrap: public and always 200, including before setup."""
    row = auth_service.get_credentials(db)

    session_valid = bool(
        row is not None
        and request.session.get("user") == row.username
        and request.session.get("v") == row.token_version
    )
    return AuthStatusOut(
        setup_complete=row is not None,
        authenticated=session_valid,
        # The username is only returned with a real session behind it, never to anonymous.
        username=row.username if (session_valid and row is not None) else None,
    )


@router.post("/setup", status_code=status.HTTP_201_CREATED, response_model=AuthResultOut)
def setup(request: Request, body: SetupInput, db: Session = Depends(get_db)):
    who = _client_identity(request)
    if is_login_rate_limited(who):
        return _rate_limited(who)

    # Checked before hashing: otherwise this endpoint stays a 16 MiB, 200 ms amplifier
    # long after the install is done.
    if auth_service.is_setup_complete(db):
        return _error(
            status.HTTP_409_CONFLICT,
            "La configuración inicial ya se completó.",
            "setup_already_completed",
        )

    try:
        row = auth_service.create_initial_credentials(
            db, username=body.username, password=body.password
        )
    except auth_service.SetupAlreadyCompletedError:
        return _error(
            status.HTTP_409_CONFLICT,
            "La configuración inicial ya se completó.",
            "setup_already_completed",
        )
    except ValueError as exc:
        record_login_failure(who)
        return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc), "validation_error")

    auth_state.mark_configured(token_version=row.token_version)
    clear_login_failures(who)
    _open_session(request, row)
    return AuthResultOut(username=row.username)


@router.post("/login", response_model=AuthResultOut)
def login(request: Request, body: LoginInput, db: Session = Depends(get_db)):
    who = _client_identity(request)
    if is_login_rate_limited(who):
        return _rate_limited(who)

    row = auth_service.get_credentials(db)
    if row is None:
        return _error(
            status.HTTP_409_CONFLICT,
            "Configuración inicial pendiente",
            "setup_required",
        )

    if not auth_service.verify_credentials(db, username=body.username, password=body.password):
        record_login_failure(who)
        # Generic message: never distinguish "no such user" from "wrong password".
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "Usuario o contraseña incorrectos",
            "invalid_credentials",
        )

    clear_login_failures(who)
    _open_session(request, row)
    return AuthResultOut(username=row.username)


@router.post("/logout")
def logout(request: Request):
    """Public and idempotent: closing an already expired session must not 401."""
    request.session.clear()
    return {"status": "ok"}


@router.post("/credentials", response_model=AuthResultOut)
def change_credentials(request: Request, body: CredentialsInput, db: Session = Depends(get_db)):
    who = _client_identity(request)
    if is_login_rate_limited(who):
        return _rate_limited(who)

    try:
        row = auth_service.change_credentials(
            db,
            current_password=body.current_password,
            new_username=body.username,
            new_password=body.new_password,
        )
    except auth_service.SetupRequiredError:
        return _error(
            status.HTTP_409_CONFLICT,
            "Configuración inicial pendiente",
            "setup_required",
        )
    except auth_service.InvalidCredentialsError:
        # Same attempt budget as login: guessing current_password is guessing a
        # password, and a separate quota would hand out twice the attempts.
        record_login_failure(who)
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "La contraseña actual no es correcta",
            "invalid_current_password",
        )
    except ValueError as exc:
        return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc), "validation_error")

    auth_state.bump_token_version(row.token_version)
    clear_login_failures(who)
    # Our own session is reissued on the new version; every other one is invalidated.
    _open_session(request, row)
    return AuthResultOut(username=row.username)


@legacy_router.get("/login")
def legacy_login_page():
    """Login lives in the SPA now. 302, not 301: a 301 is cached forever."""
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@legacy_router.post("/logout")
def legacy_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
