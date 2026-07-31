"""Endpoints de autenticación.

Los path operations son síncronos (`def`, no `async def`) a propósito: FastAPI los
ejecuta en el threadpool, así que los 25-200 ms que tarda scrypt no bloquean el event
loop. Con `async def` y el hashing en línea, cada login congelaría el servidor entero.
"""

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from server import auth_state
from server.config import TRUST_X_FORWARDED_FOR
from server.database import get_db
from server.login_rate_limit import (
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
# Rutas antiguas: existen solo para que los marcadores y las PWA con el bundle viejo no
# se queden en un 404 o en un bucle de redirección.
legacy_router = APIRouter(tags=["auth"])


def _client_ip(request: Request) -> str:
    if TRUST_X_FORWARDED_FOR:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host
    return "unknown"


def _error(status_code: int, detail: str, code: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail, "code": code, **extra})


def _rate_limited(ip: str) -> JSONResponse:
    retry_after = seconds_until_reset(ip)
    response = _error(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Demasiados intentos. Inténtalo más tarde.",
        "rate_limited",
        retry_after=retry_after,
    )
    response.headers["Retry-After"] = str(retry_after)
    return response


def _open_session(request: Request, row: AuthCredential) -> None:
    # clear() antes de escribir: higiene, la sesión nueva no hereda nada de la anterior.
    request.session.clear()
    request.session["user"] = row.username
    request.session["v"] = row.token_version


@router.get("/status", response_model=AuthStatusOut)
def auth_status(request: Request, db: Session = Depends(get_db)):
    """Bootstrap de la SPA: público y siempre 200, también sin configurar."""
    row = auth_service.get_credentials(db)

    session_valid = bool(
        row is not None
        and request.session.get("user") == row.username
        and request.session.get("v") == row.token_version
    )
    return AuthStatusOut(
        setup_complete=row is not None,
        authenticated=session_valid,
        # El nombre de usuario solo se devuelve con una sesión real detrás, nunca a un
        # anónimo.
        username=row.username if (session_valid and row is not None) else None,
    )


@router.post("/setup", status_code=status.HTTP_201_CREATED, response_model=AuthResultOut)
def setup(request: Request, body: SetupInput, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    if is_login_rate_limited(ip):
        return _rate_limited(ip)

    # Se comprueba antes de hashear: si no, una vez instalado el endpoint seguiría siendo
    # un amplificador de 16 MiB y 200 ms por petición.
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
        record_login_failure(ip)
        return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc), "validation_error")

    auth_state.mark_configured(token_version=row.token_version)
    clear_login_failures(ip)
    _open_session(request, row)
    return AuthResultOut(username=row.username)


@router.post("/login", response_model=AuthResultOut)
def login(request: Request, body: LoginInput, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    if is_login_rate_limited(ip):
        return _rate_limited(ip)

    row = auth_service.get_credentials(db)
    if row is None:
        return _error(
            status.HTTP_409_CONFLICT,
            "Configuración inicial pendiente",
            "setup_required",
        )

    if not auth_service.verify_credentials(db, username=body.username, password=body.password):
        record_login_failure(ip)
        # Mensaje genérico: nunca se distingue "el usuario no existe" de "la contraseña
        # es incorrecta".
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "Usuario o contraseña incorrectos",
            "invalid_credentials",
        )

    clear_login_failures(ip)
    _open_session(request, row)
    return AuthResultOut(username=row.username)


@router.post("/logout")
def logout(request: Request):
    """Público e idempotente: si la sesión ya caducó, cerrarla no debe dar 401."""
    request.session.clear()
    return {"status": "ok"}


@router.post("/credentials", response_model=AuthResultOut)
def change_credentials(request: Request, body: CredentialsInput, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    if is_login_rate_limited(ip):
        return _rate_limited(ip)

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
        # Misma bolsa de intentos que el login: acertar current_password es adivinar una
        # contraseña, y darle cuota propia regalaría el doble de intentos.
        record_login_failure(ip)
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "La contraseña actual no es correcta",
            "invalid_current_password",
        )
    except ValueError as exc:
        return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc), "validation_error")

    auth_state.bump_token_version(row.token_version)
    clear_login_failures(ip)
    # La sesión propia se re-emite con la versión nueva; las demás quedan invalidadas.
    _open_session(request, row)
    return AuthResultOut(username=row.username)


@legacy_router.get("/login")
def legacy_login_page():
    """El login ya vive en la SPA. 302 y no 301: un 301 se cachea para siempre."""
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@legacy_router.post("/logout")
def legacy_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
