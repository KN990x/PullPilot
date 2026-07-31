"""Persistencia del secreto de firma de sesión.

Vive fuera de config.py y solo usa stdlib a propósito: database.py importa config.py,
así que cualquier import de más aquí crearía un ciclo. Por el mismo motivo el secreto
va a un fichero y no a una tabla: SessionMiddleware recibe la clave en tiempo de import
de server/app.py, cuando la base de datos todavía no tiene tablas.
"""

from __future__ import annotations

import contextlib
import logging
import os
import secrets
import stat
from pathlib import Path
from typing import Literal

SecretSource = Literal["env", "file", "ephemeral"]

SECRET_FILENAME = "session_secret.key"
# Un secreto válido son 64 caracteres hex; el mínimo detecta ficheros a medio escribir
# por otro worker que ganó la carrera de creación.
_MIN_SECRET_LEN = 32
_MAX_ATTEMPTS = 3

logger = logging.getLogger("pullpilot")


def load_or_create_session_secret(
    data_dir: Path, env_value: str | None = None
) -> tuple[str, SecretSource]:
    """Devuelve (secreto, origen).

    El entorno gana siempre. Si no está definido, se reutiliza el fichero persistente
    de `data_dir` o se crea uno nuevo, de modo que las sesiones sobrevivan a los
    reinicios sin que nadie configure nada.
    """
    if env_value:
        return env_value, "env"

    path = data_dir / SECRET_FILENAME

    # Varias vueltas porque entre nuestra lectura y nuestro link puede colarse otro
    # worker: si él gana, en la siguiente vuelta ya podemos leer lo que escribió.
    for _ in range(_MAX_ATTEMPTS):
        existing = _read_secret(path)
        if existing is not None:
            _warn_if_group_or_world_readable(path)
            return existing, "file"

        # El destino solo aparece vía link(), que es atómico, así que un fichero
        # ilegible no es un worker a medio escribir: es corrupción real (disco lleno,
        # contenedor matado con una versión anterior, edición manual). Se reemplaza, o
        # si no la instalación se quedaría sin sesiones persistentes para siempre.
        corrupt = path.exists()
        if corrupt:
            logger.warning(
                "%s no contiene un secreto válido; se regenera y las sesiones abiertas "
                "dejarán de valer.",
                path,
            )

        created = _create_secret(path, overwrite=corrupt)
        if created is not None:
            return created, "file"

    # Sin fichero utilizable (volumen de solo lectura, permisos, carrera perdida tres
    # veces): arrancamos igualmente con un secreto en memoria. Una instalación con el
    # volumen mal montado debe levantar y quejarse, no negarse a existir.
    return secrets.token_hex(32), "ephemeral"


def _read_secret(path: Path) -> str | None:
    """None si no existe, está truncado o no se puede leer."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if len(raw) < _MIN_SECRET_LEN:
        return None
    return raw


def _create_secret(path: Path, *, overwrite: bool = False) -> str | None:
    """Crea el fichero de forma atómica.

    None si otro proceso ganó la carrera o si el sistema de ficheros no lo permite.
    Con `overwrite` se pisa lo que hubiera: solo para reemplazar un fichero corrupto.
    """
    secret = secrets.token_hex(32)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")

    try:
        # El modo se aplica al crear: nunca existe una ventana con el fichero a 0644.
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError:
        return None

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(secret)
            handle.flush()
            os.fsync(handle.fileno())

        # link() es atómico y falla si el destino existe: justo la primitiva de "crea
        # con este contenido o dime que ya está". os.replace pisaría el secreto que
        # otro worker acabe de escribir e invalidaría sus sesiones, así que solo se usa
        # para sustituir un fichero que ya sabemos que no sirve.
        try:
            if overwrite:
                os.replace(tmp, path)
            else:
                os.link(tmp, path)
        except FileExistsError:
            return None
        except OSError:
            return None
        return secret
    except OSError:
        return None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)


def _warn_if_group_or_world_readable(path: Path) -> None:
    """Avisa (no corrige) si el fichero quedó legible por alguien más que su dueño."""
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return
    if mode & 0o077:
        logger.warning(
            "%s tiene permisos %o: cualquiera que lo lea puede falsificar sesiones. "
            "Ajusta los permisos a 600.",
            path,
            mode,
        )
