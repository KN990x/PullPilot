"""Configuration. Four optional variables; everything else is a constant.

See the README for what each variable does. If something here becomes an environment
variable again, it should be because a real problem needed it.
"""

import logging
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from server.secret_store import SECRET_FILENAME, load_or_create_session_secret

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_STACKS_ROOT = "/srv/docker-stacks"
# DOCKER_ROOT_PATH and PROJECTS_ROOT are the old names, still read so an existing .env
# does not silently end up with an empty project list.
STACKS_PATH = Path(
    os.getenv("STACKS_PATH")
    or os.getenv("DOCKER_ROOT_PATH")
    or os.getenv("PROJECTS_ROOT")
    or DEFAULT_STACKS_ROOT
)
PROJECTS_ROOT = STACKS_PATH

os.environ.setdefault("TZ", "UTC")

PUBLIC_URL = (os.getenv("PUBLIC_URL") or "").strip()
_public_scheme = urlparse(PUBLIC_URL).scheme if PUBLIC_URL else ""
# Secure only over https: setting it on a plain-HTTP install means the browser never sends
# the cookie back and nobody can log in.
SESSION_HTTPS_ONLY = _public_scheme == "https"
# With a proxy in front, the client IP for rate limiting is in X-Forwarded-For.
TRUST_X_FORWARDED_FOR = bool(PUBLIC_URL)

# Undocumented: the container fixes it to /app/data, `make dev-server` points it at .devdata.
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "pullpilot.db"
STATIC_DIR = BASE_DIR / "static"

# Before anything else: the session secret is written here and reports failures by log.
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("pullpilot")

HEALTHCHECK_TIMEOUT = 60
COMMAND_TIMEOUT = 300

# Language of scheduled update logs. The only thing that cannot be derived from a request:
# the scheduler runs them with no browser behind to read Accept-Language from.
_raw_log_locale = (os.getenv("LOG_LOCALE") or "es").strip().lower()
LOG_LOCALE: Literal["es", "en"] = (
    _raw_log_locale if _raw_log_locale in ("es", "en") else "es"
)

# SameSite=lax and nothing else: `none` would need HTTPS and allow cross-site requests,
# `strict` buys nothing in an app that serves its own frontend.
SESSION_MAX_AGE = 30 * 24 * 60 * 60
SESSION_COOKIE_NAME = "pullpilot_session"
SESSION_SAME_SITE: Literal["lax"] = "lax"

SESSION_SECRET, SESSION_SECRET_SOURCE = load_or_create_session_secret(DATA_DIR)


def validate_startup_security() -> None:
    """Startup warnings. Never aborts: a fresh install is resolved through the UI."""
    if SESSION_SECRET_SOURCE == "ephemeral":
        logger.warning(
            "No se pudo persistir el secreto de sesión en %s: se usa uno en memoria y "
            "las sesiones caducarán en cada reinicio. Revisa que %s exista y sea "
            "escribible.",
            DATA_DIR / SECRET_FILENAME,
            DATA_DIR,
        )
    elif SESSION_SECRET_SOURCE == "file":
        logger.info("Secreto de sesión persistente en %s.", DATA_DIR / SECRET_FILENAME)
