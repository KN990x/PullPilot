"""Configuración de PullPilot.

Filosofía: **no hay nada que configurar**. Las credenciales las crea el asistente en el
primer arranque y viven hasheadas en la base de datos; el secreto de firma de sesión se
genera y persiste solo. Lo único que un usuario necesita decidir es dónde están sus
stacks, en qué puerto escucha y en qué zona horaria vive.

Todo lo demás son constantes. Si algo de aquí abajo vuelve a convertirse en variable de
entorno, que sea porque alguien tenía un problema real que no se podía resolver de otra
forma.
"""

import logging
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from server.secret_store import SECRET_FILENAME, load_or_create_session_secret

BASE_DIR = Path(__file__).resolve().parent

# --- Las tres variables documentadas -----------------------------------------------

# Carpeta de stacks. Misma ruta absoluta en el host y dentro del contenedor.
# DOCKER_ROOT_PATH y PROJECTS_ROOT se siguen leyendo como alias: quien ya tenía un .env
# de una versión anterior no se queda sin proyectos al actualizar.
DEFAULT_STACKS_ROOT = "/srv/docker-stacks"
STACKS_PATH = Path(
    os.getenv("STACKS_PATH")
    or os.getenv("DOCKER_ROOT_PATH")
    or os.getenv("PROJECTS_ROOT")
    or DEFAULT_STACKS_ROOT
)
# Nombre histórico, el que usan los servicios y los mensajes de error.
PROJECTS_ROOT = STACKS_PATH

# TZ y el puerto los consume Docker, no este proceso: TZ la lee la libc y el puerto lo
# publica el compose. Aquí solo se fija un valor por defecto sensato.
os.environ.setdefault("TZ", "UTC")

# URL pública cuando hay un proxy inverso delante. Es opcional y de ella se derivan las
# dos cosas que antes eran variables sueltas.
PUBLIC_URL = (os.getenv("PUBLIC_URL") or "").strip()
_public_scheme = urlparse(PUBLIC_URL).scheme if PUBLIC_URL else ""
# Cookie con Secure solo si la URL pública es https: ponerlo sobre http dejaría al
# navegador sin enviar la cookie y el login no funcionaría nunca.
SESSION_HTTPS_ONLY = _public_scheme == "https"
# Con proxy delante, la IP del cliente para el rate limit está en X-Forwarded-For.
TRUST_X_FORWARDED_FOR = bool(PUBLIC_URL)

# --- Rutas internas ------------------------------------------------------------------

# No se documenta: dentro del contenedor siempre es /app/data (volumen `pullpilot_data`).
# Fuera, `make dev-server` la apunta a .devdata.
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "pullpilot.db"
# El bundle de Vite se copia dentro del propio paquete: no hace falta ninguna variable
# para localizarlo (ver Dockerfile).
STATIC_DIR = BASE_DIR / "static"

# DATA_DIR y el logging van antes que nada: el secreto de sesión se escribe ahí y
# avisa por log si algo falla.
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("pullpilot")

# --- Constantes ----------------------------------------------------------------------

# Espera tras el despliegue a que los contenedores queden sanos, y tope de cualquier
# comando externo (`git pull`, `docker compose ...`).
HEALTHCHECK_TIMEOUT = 60
COMMAND_TIMEOUT = 300

# Idioma de los logs de las tareas programadas. Es lo único que no puede deducirse de la
# petición: las lanza el scheduler, sin navegador detrás del que leer Accept-Language.
# Las actualizaciones disparadas desde la interfaz usan el idioma del navegador.
_raw_log_locale = (os.getenv("LOG_LOCALE") or "es").strip().lower()
LOG_LOCALE: Literal["es", "en"] = (
    _raw_log_locale if _raw_log_locale in ("es", "en") else "es"
)

# Cookie de sesión: 30 días, firmada, SameSite=lax. `none` exigiría HTTPS y abriría la
# puerta a peticiones cross-site; `strict` no aporta nada en una app que se sirve a sí
# misma. Nadie necesita elegir aquí.
SESSION_MAX_AGE = 30 * 24 * 60 * 60
SESSION_COOKIE_NAME = "pullpilot_session"
SESSION_SAME_SITE: Literal["lax"] = "lax"

# El secreto se genera y persiste en $DATA_DIR/session_secret.key con permisos 0600.
SESSION_SECRET, SESSION_SECRET_SOURCE = load_or_create_session_secret(DATA_DIR)


def validate_startup_security() -> None:
    """Avisos de arranque. No aborta: la primera instalación se resuelve por UI."""
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
