"""Configuration. Four optional variables; everything else is a constant.

See the README for what each variable does. If something here becomes an environment
variable again, it should be because a real problem needed it.
"""

import logging
import os
import time
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

# tzset() is what makes it stick: setting TZ after the interpreter starts does not change
# what localtime_r (and so datetime.now()) returns on glibc. It happened to work in the
# container only because compose exports TZ before the process starts, which left
# `make dev-server` and a bare uvicorn on the host clock.
os.environ.setdefault("TZ", "UTC")
if hasattr(time, "tzset"):  # not available on Windows
    time.tzset()

PUBLIC_URL = (os.getenv("PUBLIC_URL") or "").strip()
_public_scheme = urlparse(PUBLIC_URL).scheme if PUBLIC_URL else ""
# Secure only over https: setting it on a plain-HTTP install means the browser never sends
# the cookie back and nobody can log in.
SESSION_HTTPS_ONLY = _public_scheme == "https"
# With a proxy in front, the client IP for rate limiting is in X-Forwarded-For. Gated on
# https like the cookie: the header is client-supplied, so trusting it without a TLS proxy
# actually terminating in front hands anyone a fresh rate-limit bucket per request.
TRUST_X_FORWARDED_FOR = _public_scheme == "https"

# Undocumented: the container fixes it to /app/data, `make dev-server` points it at .devdata.
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "pullpilot.db"
STATIC_DIR = BASE_DIR / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("pullpilot")

# Before anything else: the session secret is written here, and the database lives here
# too. Unlike the secret, which degrades to an in-memory one, there is no working
# PullPilot without this directory — so say exactly what to fix and then let it fail,
# rather than raising a bare OSError from inside an import.
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    logger.error(
        "No se pudo crear el directorio de datos %s. Ahí viven la base de datos y el "
        "secreto de sesión: revisa que el volumen esté montado y sea escribible.",
        DATA_DIR,
    )
    raise

HEALTHCHECK_TIMEOUT = 60
COMMAND_TIMEOUT = 300

# History rows kept. The UI only ever reads the newest 20; the rest is there to look back
# at a bad night. Without a ceiling the table grew forever, each row holding a full log.
HISTORY_RETENTION = 200

# Language of scheduled update logs: the scheduler runs with no browser behind it, so
# there is no Accept-Language to read. A constant, not a variable — it was read from the
# environment but documented nowhere, so nobody can have it set. Making the scheduler
# speak English is a matter of persisting the UI language, not of a fifth variable.
LOG_LOCALE: Literal["es", "en"] = "es"

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

    # Everything hanging off PUBLIC_URL keys on the scheme, so a bare hostname silently
    # behaves like no PUBLIC_URL at all: cookie without Secure on an HTTPS install.
    if PUBLIC_URL and not _public_scheme:
        logger.warning(
            "PUBLIC_URL=%s no incluye esquema. Sin 'https://' la cookie de sesión no se "
            "marca como Secure y no se confía en X-Forwarded-For. Escríbela completa, "
            "por ejemplo https://%s",
            PUBLIC_URL,
            PUBLIC_URL,
        )
