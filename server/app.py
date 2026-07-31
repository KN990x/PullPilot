import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from server import auth_state
from server.config import (
    AUTH_SEED_PASS,
    AUTH_SEED_USER,
    CORS_ORIGINS,
    DEFAULT_STACKS_ROOT,
    PROJECTS_ROOT,
    SESSION_HTTPS_ONLY,
    SESSION_SAME_SITE,
    SESSION_SECRET,
    STATIC_DIR,
    logger,
    validate_startup_security,
)
from server.database import Base, engine, session_scope
from server.models import db as _db_models  # noqa: F401
from server.routers.auth import legacy_router as auth_legacy_router
from server.routers.auth import router as auth_router
from server.routers.projects import router as projects_router
from server.routers.schedules import router as schedules_router
from server.routers.status import router as status_router
from server.services import auth as auth_service
from server.services.scheduler import start_scheduler, stop_scheduler

# Endpoints de la API que tienen que responder sin sesión: son los que permiten a la SPA
# averiguar en qué estado está la instalación y salir de él.
AUTH_PUBLIC_API_PATHS = frozenset(
    {
        "/api/auth/status",
        "/api/auth/login",
        "/api/auth/setup",
        "/api/auth/logout",
    }
)
AUTH_PUBLIC_PATHS = frozenset({"/login", "/logout"})
# Rutas que acaban en una extensión "pública" pero no lo son: el esquema de OpenAPI
# describe la API entera y hasta ahora se servía sin sesión por culpa del sufijo .json.
AUTH_NEVER_PUBLIC_PATHS = frozenset({"/openapi.json", "/docs", "/redoc"})
AUTH_PUBLIC_PATH_EXTENSIONS = (
    ".png",
    ".ico",
    ".js",
    ".css",
    ".svg",
    ".json",
    ".webmanifest",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # create_all va primero porque todo lo que sigue consulta la base de datos. En una
    # instalación existente esto solo añade auth_credentials: create_all crea tablas
    # nuevas pero no altera las que ya están.
    Base.metadata.create_all(bind=engine)

    with session_scope() as db:
        seeded = auth_service.seed_from_env(
            db, username=AUTH_SEED_USER, password=AUTH_SEED_PASS
        )
        row = auth_service.get_credentials(db)
        configured = row is not None
        token_version = row.token_version if row else 0

    if seeded:
        logger.info(
            "Credenciales creadas a partir de AUTH_USER/AUTH_PASS: no hace falta pasar "
            "por el asistente de configuración."
        )
    elif AUTH_SEED_USER and AUTH_SEED_PASS:
        logger.warning(
            "AUTH_USER y AUTH_PASS siguen definidos en el entorno pero ya no se usan: "
            "las credenciales viven hasheadas en la base de datos. Puedes borrarlas del .env."
        )

    auth_state.prime(configured=configured, token_version=token_version)
    if not configured:
        logger.info(
            "Sin credenciales: al abrir la interfaz se mostrará el asistente de "
            "configuración inicial."
        )

    # Después del estado real de la base de datos, porque ya no aborta el arranque: lo
    # que emite son avisos, y varios dependen de lo anterior.
    validate_startup_security()

    if not PROJECTS_ROOT.exists():
        logger.warning(
            "La carpeta de stacks no existe: %s. Por defecto el compose oficial usa "
            "/srv/docker-stacks (${DOCKER_ROOT_PATH:-%s}); en .env puedes definir "
            "DOCKER_ROOT_PATH u override avanzado PROJECTS_ROOT. Créala en el host y "
            "revisa el bind mount en docker-compose; hasta entonces la lista de proyectos "
            "estará vacía.",
            PROJECTS_ROOT,
            DEFAULT_STACKS_ROOT,
        )
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="PullPilot API", lifespan=lifespan)

# Middleware order (Starlette): the last one added via add_middleware receives the
# request first. CORSMiddleware (outermost) → SessionMiddleware → routes and this
# auth_middleware (http), so that request.session is available here.


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def _is_public_path(path: str) -> bool:
    # El orden importa: bajo /api se decide SOLO por lista blanca. Antes bastaba con que
    # la ruta acabara en .json para saltarse la autenticación, así que /api/loquesea.json
    # y /openapi.json quedaban abiertos.
    if _is_api_path(path):
        return path in AUTH_PUBLIC_API_PATHS
    if path in AUTH_NEVER_PUBLIC_PATHS:
        return False
    if path in AUTH_PUBLIC_PATHS or path.startswith("/assets/"):
        return True
    return path.endswith(AUTH_PUBLIC_PATH_EXTENSIONS)


def _requires_session(path: str) -> bool:
    """Rutas que responden 401 en vez de dejar pasar el shell estático de la SPA."""
    return _is_api_path(path) or path in AUTH_NEVER_PUBLIC_PATHS


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    snapshot = auth_state.get_snapshot()

    # Escotilla heredada: ALLOW_NO_AUTH deja pasar todo.
    if snapshot.open_access:
        return await call_next(request)

    path = request.url.path
    if _is_public_path(path):
        return await call_next(request)

    # Instalación pendiente: el shell de la SPA se sirve para que pueda pintar el
    # asistente, pero la API sigue cerrada salvo la lista blanca. El bundle es estático
    # y no lleva datos; todo lo del homelab entra por /api.
    if not snapshot.configured:
        if _requires_session(path):
            return JSONResponse(
                status_code=401,
                content={"detail": "Configuración inicial pendiente", "code": "setup_required"},
            )
        return await call_next(request)

    user = request.session.get("user")
    version = request.session.get("v")
    if not user or version != snapshot.token_version:
        request.session.clear()
        if _requires_session(path):
            return JSONResponse(
                status_code=401,
                content={"detail": "Sesión expirada", "code": "session_expired"},
            )
        # Ya no se redirige a /login: la SPA decide qué pintar consultando
        # /api/auth/status.
        return await call_next(request)

    request.session["user"] = user
    request.session["v"] = version
    request.session["last_seen"] = int(datetime.datetime.now(datetime.UTC).timestamp())
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = jsonable_encoder(exc.errors())
    # Pydantic incluye el valor rechazado en `input`; bajo /api/auth eso significa
    # devolver al navegador (y a los logs de cualquier proxy) la contraseña que el
    # usuario acaba de escribir.
    if request.url.path.startswith("/api/auth"):
        errors = [{k: v for k, v in item.items() if k != "input"} for item in errors]
        return JSONResponse(
            status_code=422,
            content={"detail": errors, "code": "validation_error"},
        )
    return JSONResponse(status_code=422, content={"detail": errors})


app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=2592000,
    session_cookie="pullpilot_session",
    same_site=SESSION_SAME_SITE,
    https_only=SESSION_HTTPS_ONLY,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(auth_legacy_router)
app.include_router(projects_router)
app.include_router(schedules_router)
app.include_router(status_router)

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    # Ojo: este handler intercepta también las HTTPException(404) de los routers, así que
    # un 404 de la API acaba respondiendo 200 + el HTML de la SPA. Es un bug previo y
    # queda fuera del alcance de este cambio; por eso ningún endpoint de /api/auth usa
    # 404 para nada.
    @app.exception_handler(404)
    async def not_found_handler(_: Request, __):
        return FileResponse(str(STATIC_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
