import logging
import os
from pathlib import Path
from typing import Literal

from server.secret_store import SECRET_FILENAME, load_or_create_session_secret


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() == "true"


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
# Same default path as official docker-compose bind mount; PROJECTS_ROOT overrides.
DEFAULT_STACKS_ROOT = "/srv/docker-stacks"
PROJECTS_ROOT = Path(
    os.getenv("PROJECTS_ROOT") or os.getenv("DOCKER_ROOT_PATH", DEFAULT_STACKS_ROOT)
)
DB_PATH = DATA_DIR / "pullpilot.db"
_static_override = os.getenv("STATIC_DIR", "").strip()
STATIC_DIR = Path(_static_override) if _static_override else BASE_DIR / "static"

os.environ.setdefault("TZ", "UTC")
# DATA_DIR y el logging van antes que nada: el secreto de sesión se escribe ahí y
# avisa por log si algo falla.
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("pullpilot")

HEALTHCHECK_TIMEOUT = int(os.getenv("HEALTHCHECK_TIMEOUT", "60"))
COMMAND_TIMEOUT = int(os.getenv("COMMAND_TIMEOUT", "300"))

_raw_log_locale = (os.getenv("LOG_LOCALE") or "es").strip().lower()
LOG_LOCALE: Literal["es", "en"] = (
    _raw_log_locale if _raw_log_locale in ("es", "en") else "es"
)

# Las credenciales viven hasheadas en la base de datos y se crean por UI en el primer
# arranque. AUTH_USER/AUTH_PASS solo sirven ya como semilla para migrar instalaciones
# antiguas sin que el usuario tenga que volver a pasar por el asistente.
AUTH_SEED_USER = os.getenv("AUTH_USER") or None
AUTH_SEED_PASS = os.getenv("AUTH_PASS") or None
# Escotilla heredada: deja la API completamente abierta y desactiva el asistente.
ALLOW_NO_AUTH = _env_bool("ALLOW_NO_AUTH", False)

SESSION_SECRET, SESSION_SECRET_SOURCE = load_or_create_session_secret(
    DATA_DIR, os.getenv("SESSION_SECRET") or None
)
# True cuando el secreto es estable entre reinicios (entorno o fichero persistente).
_SESSION_SECRET_SET = SESSION_SECRET_SOURCE != "ephemeral"
SESSION_HTTPS_ONLY = _env_bool("SESSION_HTTPS_ONLY", False)
_raw_same_site = os.getenv("SESSION_SAME_SITE", "lax").strip().lower()
SESSION_SAME_SITE: Literal["lax", "strict", "none"] = (
    _raw_same_site if _raw_same_site in ("lax", "strict", "none") else "lax"
)

# Comma-separated; empty = allow any origin (the SPA served by FastAPI itself usually needs no CORS).
_raw_cors = os.getenv("CORS_ORIGINS", "").strip()
CORS_ORIGINS: list[str] = (
    ["*"]
    if not _raw_cors
    else [o.strip() for o in _raw_cors.split(",") if o.strip()]
)

LOGIN_RATE_LIMIT_ENABLED = _env_bool("LOGIN_RATE_LIMIT_ENABLED", True)
LOGIN_RATE_LIMIT_MAX = int(os.getenv("LOGIN_RATE_LIMIT_MAX", "15"))
LOGIN_RATE_LIMIT_WINDOW_SEC = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SEC", "300"))

# Behind a trusted reverse proxy: use the first X-Forwarded-For IP for login rate limiting.
TRUST_X_FORWARDED_FOR = _env_bool("TRUST_X_FORWARDED_FOR", False)


def _parse_workers(raw: str | None) -> int:
    try:
        return int(raw or "1")
    except ValueError:
        return 1


def validate_startup_security() -> None:
    """Avisos de arranque. Ya no aborta: la primera instalación se resuelve por UI."""
    workers = _parse_workers(os.getenv("UVICORN_WORKERS"))
    if workers > 1:
        # El secreto ya se comparte entre workers vía fichero, así que esto dejó de ser
        # un error. El problema que queda es otro: APScheduler arranca en el lifespan de
        # cada worker, o sea N schedulers actualizando los mismos contenedores a la vez.
        logger.warning(
            "UVICORN_WORKERS=%s. El scheduler, el límite de intentos de login y el "
            "estado de progreso son por proceso: con más de un worker las tareas "
            "programadas se duplican. Usa un solo worker.",
            workers,
        )

    if SESSION_SECRET_SOURCE == "ephemeral":
        logger.warning(
            "No se pudo persistir el secreto de sesión en %s: se usa uno en memoria y "
            "las sesiones caducarán en cada reinicio. Revisa que %s exista y sea "
            "escribible, o define SESSION_SECRET en el entorno.",
            DATA_DIR / SECRET_FILENAME,
            DATA_DIR,
        )
    elif SESSION_SECRET_SOURCE == "file":
        logger.info(
            "Secreto de sesión persistente en %s.", DATA_DIR / SECRET_FILENAME
        )

    if ALLOW_NO_AUTH:
        logger.warning(
            "ALLOW_NO_AUTH=true: la API no exige login y el asistente de configuración "
            "queda desactivado. Variable obsoleta; quítala del .env salvo en una red "
            "totalmente aislada."
        )
