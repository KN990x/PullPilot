"""Dos actualizaciones a la vez sobre el mismo stack se pisan.

`update_single_project_logic` lanza `compose down`/`stop` y luego `up -d`. Solapadas, la
segunda puede levantar contenedores mientras la primera los baja, y el rollback de una
revierte el despliegue de la otra. Basta un doble clic o dos pestañas abiertas.
"""

import threading

import pytest
import server.routers.projects as projects_router_module
from fastapi.testclient import TestClient

from server.services import locks


@pytest.fixture(autouse=True)
def _clean_locks():
    locks.reset_for_tests()
    yield
    locks.reset_for_tests()


def test_slot_is_exclusive_per_project() -> None:
    with locks.project_update_slot("plex"):
        assert locks.is_busy("plex") is True
        with pytest.raises(locks.ProjectBusyError):
            with locks.project_update_slot("plex"):
                pass
        # Otro proyecto no comparte turno.
        with locks.project_update_slot("pihole"):
            pass

    assert locks.is_busy("plex") is False


def test_slot_is_released_when_the_update_raises() -> None:
    with pytest.raises(RuntimeError):
        with locks.project_update_slot("plex"):
            raise RuntimeError("boom")

    assert locks.is_busy("plex") is False


def test_second_concurrent_update_gets_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    release = threading.Event()

    def _blocking_update(name, db, *, locale="es"):
        started.set()
        release.wait(timeout=5)
        return True, ["ok"]

    # Se parchea en el router y no en el módulo de origen: projects.py fija el nombre al
    # importar (trampa 1 de AGENTS.md).
    monkeypatch.setattr(
        projects_router_module, "update_single_project_logic", _blocking_update
    )

    first: dict[str, int] = {}

    def _run_first():
        first["status"] = client.post("/api/projects/plex/update").status_code

    worker = threading.Thread(target=_run_first)
    worker.start()
    try:
        assert started.wait(timeout=5), "la primera actualizacion no llego a arrancar"
        second = client.post("/api/projects/plex/update")
    finally:
        release.set()
        worker.join(timeout=5)

    assert second.status_code == 409
    assert first["status"] == 200


def test_the_slot_is_free_again_afterwards(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        projects_router_module,
        "update_single_project_logic",
        lambda name, db, *, locale="es": (True, ["ok"]),
    )

    assert client.post("/api/projects/plex/update").status_code == 200
    assert client.post("/api/projects/plex/update").status_code == 200
