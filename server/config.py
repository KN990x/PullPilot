import logging
import os
import secrets
from pathlib import Path
from typing import Literal


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
TEMPLATES_DIR = BASE_DIR / "templates"

HEALTHCHECK_TIMEOUT = int(os.getenv("HEALTHCHECK_TIMEOUT", "60"))
COMMAND_TIMEOUT = int(os.getenv("COMMAND_TIMEOUT", "300"))

_raw_log_locale = (os.getenv("LOG_LOCALE") or "es").strip().lower()
LOG_LOCALE: Literal["es", "en"] = (
    _raw_log_locale if _raw_log_locale in ("es", "en") else "es"
)

AUTH_USER = os.getenv("AUTH_USER")
AUTH_PASS = os.getenv("AUTH_PASS")
# When false (the default), AUTH_USER and AUTH_PASS are required or startup fails.
ALLOW_NO_AUTH = _env_bool("ALLOW_NO_AUTH", False)
_SESSION_SECRET_SET = os.getenv("SESSION_SECRET") is not None
SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_hex(32)
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

os.environ.setdefault("TZ", "UTC")
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("pullpilot")

if not _SESSION_SECRET_SET:
    logger.warning(
        "SESSION_SECRET no está definido en el entorno: se generó uno aleatorio. "
        "Las sesiones caducarán en cada reinicio. Define SESSION_SECRET en .env (p. ej. openssl rand -hex 32)."
    )


def validate_startup_security() -> None:
    """Llamar al arranque de la app. Falla si la configuración es insegura para el modo elegido."""
    workers_raw = os.getenv("UVICORN_WORKERS", "1") or "1"
    try:
        workers = int(workers_raw)
    except ValueError:
        workers = 1
    if workers > 1 and not _SESSION_SECRET_SET:
        raise RuntimeError(
            "SESSION_SECRET debe estar definido en el entorno cuando UVICORN_WORKERS > 1."
        )

    if ALLOW_NO_AUTH:
        if not AUTH_USER or not AUTH_PASS:
            logger.warning(
                "ALLOW_NO_AUTH=true: la API no exige login. Usar solo en redes de confianza."
            )
        return

    if not AUTH_USER or not AUTH_PASS:
        raise RuntimeError(
            "Definir AUTH_USER y AUTH_PASS, o en entornos totalmente de confianza establecer "
            "ALLOW_NO_AUTH=true. Consulta README (seguridad y variables de entorno)."
        )
