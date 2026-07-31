"""The SPA fallback must not swallow the API's 404s.

No test saw this: `server/static` only exists inside the image, so in development the
handler was never even registered. In production it was, and `DELETE /api/schedules/9999`
answered 200 + index.html — the frontend checks `response.ok` and took a delete that never
happened as done. Hence the fake static directory here.
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from server.app import register_spa_fallback

INDEX_HTML = "<!doctype html><title>PullPilot</title><div id=root></div>"


@pytest.fixture()
def spa_client(tmp_path) -> TestClient:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")

    app = FastAPI()

    @app.delete("/api/schedules/{schedule_id}")
    def delete_schedule(schedule_id: int):
        raise HTTPException(status_code=404, detail="Programacion no encontrada")

    @app.get("/api/projects")
    def projects():
        return []

    # A non-/api route that can 404, to check the shell is only served on GET/HEAD.
    @app.post("/logout")
    def legacy_logout():
        raise HTTPException(status_code=404, detail="Ya no existe")

    # Same as server/app.py: the mount goes after the routes.
    register_spa_fallback(app, static_dir)
    return TestClient(app)


def test_api_404_stays_json(spa_client: TestClient) -> None:
    response = spa_client.delete("/api/schedules/99999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Programacion no encontrada"


def test_unknown_api_route_is_404_not_the_spa(spa_client: TestClient) -> None:
    response = spa_client.get("/api/no-existe")

    assert response.status_code == 404
    assert "text/html" not in response.headers.get("content-type", "")


def test_non_get_404_does_not_get_the_shell(spa_client: TestClient) -> None:
    """A POST is not navigation: even on a 404 it does not get the SPA shell."""
    response = spa_client.post("/logout")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ya no existe"


def test_post_to_an_unknown_path_never_returns_the_shell(spa_client: TestClient) -> None:
    """StaticFiles answers 405 before the handler; what matters is it is not the shell."""
    response = spa_client.post("/lo-que-sea")

    assert response.status_code in (404, 405)
    assert "id=root" not in response.text


def test_navigation_route_serves_the_spa_shell(spa_client: TestClient) -> None:
    response = spa_client.get("/history")

    assert response.status_code == 200
    assert "id=root" in response.text


def test_index_is_served_at_the_root(spa_client: TestClient) -> None:
    response = spa_client.get("/")

    assert response.status_code == 200
    assert "id=root" in response.text


def test_existing_api_route_is_untouched(spa_client: TestClient) -> None:
    assert spa_client.get("/api/projects").json() == []
