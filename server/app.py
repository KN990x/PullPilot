from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from server import auth_state
from server.config import (
    DEFAULT_STACKS_ROOT,
    SESSION_COOKIE_NAME,
    SESSION_HTTPS_ONLY,
    SESSION_MAX_AGE,
    SESSION_SAME_SITE,
    SESSION_SECRET,
    STACKS_PATH,
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

# The only endpoints that answer without a session: what the SPA needs to find out which
# state the install is in, and to get out of it.
AUTH_PUBLIC_API_PATHS = frozenset(
    {
        "/api/auth/status",
        "/api/auth/login",
        "/api/auth/setup",
        "/api/auth/logout",
    }
)
AUTH_PUBLIC_PATHS = frozenset({"/login", "/logout"})
# Public-looking extension, private content: /openapi.json describes the whole API and was
# served to anonymous callers because of the .json suffix.
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


# index.html is the file that names every hashed asset, so a cached copy can outlive the
# assets it points at. The hashed files themselves keep StaticFiles' own caching.
NO_CACHE = "no-cache"


class _SpaStatics(StaticFiles):
    """StaticFiles that refuses to let the SPA shell be cached."""

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        if str(full_path).endswith("index.html"):
            response.headers["Cache-Control"] = NO_CACHE
        return response


@asynccontextmanager
async def lifespan(_: FastAPI):
    # First, because everything below queries the database. On an existing install this
    # only adds new tables; it never alters the ones already there.
    Base.metadata.create_all(bind=engine)

    with session_scope() as db:
        row = auth_service.get_credentials(db)
        configured = row is not None
        token_version = row.token_version if row else 0
        username = row.username if row else None

    auth_state.prime(
        configured=configured, token_version=token_version, username=username
    )
    if not configured:
        logger.info(
            "Sin credenciales: al abrir la interfaz se mostrará el asistente de "
            "configuración inicial."
        )

    validate_startup_security()

    # Warn, do not fail: the folder can appear later without restarting the container.
    if not STACKS_PATH.exists():
        logger.warning(
            "La carpeta de stacks no existe: %s. Créala en el host (por defecto "
            "%s) o define STACKS_PATH en el .env junto al docker-compose.yml. Hasta "
            "entonces la lista de proyectos estará vacía.",
            STACKS_PATH,
            DEFAULT_STACKS_ROOT,
        )
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="PullPilot API", lifespan=lifespan)

# Middleware order (Starlette): the last one added receives the request first, so
# SessionMiddleware runs before this auth_middleware and request.session is available here.
# No CORSMiddleware on purpose: the backend serves its own SPA and Vite proxies in
# development, so no supported scenario makes a cross-origin request.


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def _is_public_path(path: str) -> bool:
    # Order matters: under /api it is allowlist only. Deciding by suffix left
    # /api/anything.json and /openapi.json open.
    if _is_api_path(path):
        return path in AUTH_PUBLIC_API_PATHS
    if path in AUTH_NEVER_PUBLIC_PATHS:
        return False
    if path in AUTH_PUBLIC_PATHS or path.startswith("/assets/"):
        return True
    return path.endswith(AUTH_PUBLIC_PATH_EXTENSIONS)


def _requires_session(path: str) -> bool:
    """Paths that answer 401 instead of letting the static SPA shell through."""
    return _is_api_path(path) or path in AUTH_NEVER_PUBLIC_PATHS


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    snapshot = auth_state.get_snapshot()

    path = request.url.path
    if _is_public_path(path):
        return await call_next(request)

    # Setup pending: the SPA shell is served so it can draw the wizard, but the API stays
    # closed. The bundle is static and carries no data; the homelab is all behind /api.
    if not snapshot.configured:
        if _requires_session(path):
            return JSONResponse(
                status_code=401,
                content={"detail": "Configuración inicial pendiente", "code": "setup_required"},
            )
        return await call_next(request)

    # The username is compared, not just its presence: token_version restarts at 1 when
    # the credentials are wiped and the wizard is run again (the recovery the README
    # documents), so a cookie from the previous account used to walk straight through
    # while /api/auth/status — which does compare it — reported nobody logged in.
    user = request.session.get("user")
    version = request.session.get("v")
    if not user or user != snapshot.username or version != snapshot.token_version:
        request.session.clear()
        if _requires_session(path):
            return JSONResponse(
                status_code=401,
                content={"detail": "Sesión expirada", "code": "session_expired"},
            )
        # No redirect to /login: the SPA decides what to draw from /api/auth/status.
        return await call_next(request)

    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = jsonable_encoder(exc.errors())
    # Pydantic echoes the rejected value in `input`; under /api/auth that hands the
    # password the user just typed back to the browser and to any proxy's logs.
    if request.url.path.startswith("/api/auth"):
        errors = [{k: v for k, v in item.items() if k != "input"} for item in errors]
        return JSONResponse(
            status_code=422,
            content={"detail": errors, "code": "validation_error"},
        )
    # `code` is part of the error envelope everywhere else, and the SPA keys its i18n off
    # it; without it a malformed request showed the raw Pydantic message.
    return JSONResponse(
        status_code=422, content={"detail": errors, "code": "validation_error"}
    )


app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=SESSION_MAX_AGE,
    session_cookie=SESSION_COOKIE_NAME,
    same_site=SESSION_SAME_SITE,
    https_only=SESSION_HTTPS_ONLY,
)

app.include_router(auth_router)
app.include_router(auth_legacy_router)
app.include_router(projects_router)
app.include_router(schedules_router)
app.include_router(status_router)


def _is_asset_request(path: str) -> bool:
    """A request for a concrete file rather than a route the SPA can draw.

    Everything Vite emits carries a content hash in its name. After a redeploy the old
    names are gone, and answering those with the shell meant a stale tab received HTML
    with status 200 where it expected JavaScript: a blank page instead of a clean 404 the
    browser knows how to report.
    """
    return path.startswith("/assets/") or "." in path.rsplit("/", 1)[-1]


def register_spa_fallback(target: FastAPI, static_dir: Path) -> None:
    """Serve the Vite bundle and resolve SPA routes to its shell.

    A function so it can be tested: `server/static` only exists inside the image, so
    outside it the handler is never registered and no ordinary test reaches it.
    """
    target.mount("/", _SpaStatics(directory=str(static_dir), html=True), name="static")

    @target.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        # This also catches HTTPException(404) from the routers. Returning the SPA shell
        # for those answered `DELETE /api/schedules/9999` with 200 + index.html, and the
        # frontend took the delete as done. The API always answers JSON.
        path = request.url.path
        if (
            _is_api_path(path)
            or request.method not in ("GET", "HEAD")
            or _is_asset_request(path)
        ):
            detail = getattr(exc, "detail", "Not Found")
            return JSONResponse(status_code=404, content={"detail": detail})
        return FileResponse(
            str(static_dir / "index.html"), headers={"Cache-Control": NO_CACHE}
        )


if STATIC_DIR.exists():
    register_spa_fallback(app, STATIC_DIR)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
