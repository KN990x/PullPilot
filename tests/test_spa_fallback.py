"""El fallback de la SPA no debe tragarse los 404 de la API.

Esto no lo veía ningún test: `server/static` solo existe dentro de la imagen, así que en
desarrollo el handler ni se registraba. En producción sí, y ahí `DELETE /api/schedules/9999`
respondía 200 + index.html — el frontend comprueba `response.ok` y daba por bueno un
borrado que nunca ocurrió. Por eso aquí se monta un directorio estático de mentira: es la
única forma de ejercitar la rama que de verdad corre en la imagen publicada.
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

    # Ruta fuera de /api que sí puede responder 404: sirve para comprobar que el shell
    # solo se sirve en navegaciones (GET/HEAD).
    @app.post("/logout")
    def legacy_logout():
        raise HTTPException(status_code=404, detail="Ya no existe")

    # Igual que en server/app.py: el montaje va después de las rutas.
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
    """Un POST no es navegación: aunque acabe en 404, no le toca el shell de la SPA."""
    response = spa_client.post("/logout")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ya no existe"


def test_post_to_an_unknown_path_never_returns_the_shell(spa_client: TestClient) -> None:
    """StaticFiles contesta 405 antes de llegar al handler; lo que importa es que no es el shell."""
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
