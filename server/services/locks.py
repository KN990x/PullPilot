"""Exclusión mutua de las actualizaciones, por proyecto.

Actualizar un stack es `git pull` + `compose pull` + `down`/`stop` + `up -d`. Dos de esas
secuencias solapadas sobre el mismo directorio se pisan: la segunda puede levantar
contenedores mientras la primera los está bajando, y el rollback de una revierte el
despliegue de la otra. Pasaba con un doble clic, con dos pestañas abiertas o con una
actualización global corriendo a la vez que una individual.

En proceso y con `Lock` de `threading` porque ahí es donde ocurre: los endpoints corren en
el threadpool de FastAPI y el scheduler en su propio hilo, todo dentro del mismo proceso.
Con varios workers de uvicorn esto no bastaría, pero ese escenario ya está desaconsejado
por el propio scheduler (ver README).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_registry_lock = threading.Lock()
_project_locks: dict[str, threading.Lock] = {}


def _lock_for(name: str) -> threading.Lock:
    with _registry_lock:
        lock = _project_locks.get(name)
        if lock is None:
            lock = threading.Lock()
            _project_locks[name] = lock
        return lock


class ProjectBusyError(Exception):
    """Ya hay una actualización en curso para ese proyecto."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


@contextmanager
def project_update_slot(name: str) -> Iterator[None]:
    """Toma el turno del proyecto o lanza ProjectBusyError.

    No bloquea a propósito: si ya hay una actualización en marcha, quien llega después
    tiene que enterarse (409 en la API, línea en el log del scheduler), no quedarse
    esperando a que termine para lanzar otra igual detrás.
    """
    lock = _lock_for(name)
    if not lock.acquire(blocking=False):
        raise ProjectBusyError(name)
    try:
        yield
    finally:
        lock.release()


def is_busy(name: str) -> bool:
    """Solo informativo: entre esta llamada y un acquire puede cambiar."""
    return _lock_for(name).locked()


def reset_for_tests() -> None:
    with _registry_lock:
        _project_locks.clear()
