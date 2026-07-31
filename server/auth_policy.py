"""Política de usuario y contraseña.

Módulo sin dependencias a propósito: lo necesitan tanto el servicio (que valida de
verdad) como los esquemas de Pydantic (que rechazan pronto), y cualquiera de los dos
importando al otro cierra un ciclo a través de server.models.
"""

from __future__ import annotations

USERNAME_MIN_LEN = 3
USERNAME_MAX_LEN = 64
USERNAME_PATTERN = r"^[A-Za-z0-9._@+-]+$"
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 128
