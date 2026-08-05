"""Two updates at once on the same stack fight each other.

`update_single_project_logic` runs `compose down`/`stop` and then `up -d`. Overlapping, the
second brings containers up while the first takes them down, and one rollback reverts the
other deploy. A double click or two open tabs is enough.
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
        # A different project has its own slot.
        with locks.project_update_slot("pihole"):
            pass

    assert locks.is_busy("plex") is False


def test_slot_is_released_when_the_update_raises() -> None:
    with pytest.raises(RuntimeError):
        with locks.project_update_slot("plex"):
            raise RuntimeError("boom")

    assert locks.is_busy("plex") is False


def test_second_concurrent_update_gets_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, make_project
) -> None:
    make_project("plex")
    started = threading.Event()
    release = threading.Event()

    def _blocking_update(name, db, *, locale="es"):
        started.set()
        release.wait(timeout=5)
        return True, ["ok"]

    # Patched on the router, not the source module: projects.py binds the name at import
    # time (pitfall 1 in AGENTS.md).
    monkeypatch.setattr(
        projects_router_module, "update_single_project_logic", _blocking_update
    )

    first: dict[str, int] = {}

    def _run_first():
        first["status"] = client.post("/api/projects/plex/update").status_code

    worker = threading.Thread(target=_run_first)
    worker.start()
    try:
        assert started.wait(timeout=5), "the first update never started"
        second = client.post("/api/projects/plex/update")
    finally:
        release.set()
        worker.join(timeout=5)

    assert second.status_code == 409
    assert first["status"] == 202


def test_the_slot_is_free_again_afterwards(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, make_project
) -> None:
    make_project("plex")
    monkeypatch.setattr(
        projects_router_module,
        "update_single_project_logic",
        lambda name, db, *, locale="es": (True, ["ok"]),
    )

    assert client.post("/api/projects/plex/update").status_code == 202
    assert client.post("/api/projects/plex/update").status_code == 202
