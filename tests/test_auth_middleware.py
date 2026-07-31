import pytest
from fastapi.testclient import TestClient

from server import auth_state


@pytest.mark.parametrize("path", ["/api/loquesea.json", "/api/projects.json", "/api/x.js"])
def test_api_paths_ending_in_a_public_extension_are_not_public(
    logged_in_client: TestClient, path: str
) -> None:
    """Regresión: bastaba con que la ruta acabara en .json para saltarse la autenticación."""
    logged_in_client.post("/api/auth/logout")

    assert logged_in_client.get(path).status_code == 401


def test_openapi_schema_requires_a_session(logged_in_client: TestClient) -> None:
    """El esquema describe la API entera y quedaba abierto por el sufijo .json."""
    logged_in_client.post("/api/auth/logout")

    assert logged_in_client.get("/openapi.json").status_code == 401


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_docs_require_a_session(logged_in_client: TestClient, path: str) -> None:
    logged_in_client.post("/api/auth/logout")

    assert logged_in_client.get(path).status_code == 401


def test_openapi_is_reachable_with_a_session(logged_in_client: TestClient) -> None:
    assert logged_in_client.get("/openapi.json").status_code == 200


def test_status_endpoint_is_reachable_in_every_state(auth_client: TestClient) -> None:
    # Instalación pendiente.
    assert auth_client.get("/api/auth/status").status_code == 200

    auth_client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "supersecreta", "password_confirm": "supersecreta"},
    )
    # Con sesión.
    assert auth_client.get("/api/auth/status").status_code == 200

    auth_client.post("/api/auth/logout")
    # Configurado pero sin sesión.
    assert auth_client.get("/api/auth/status").status_code == 200


def test_open_access_lets_everything_through(client: TestClient) -> None:
    """ALLOW_NO_AUTH sigue funcionando como escotilla, sin asistente."""
    assert client.get("/api/projects").status_code == 200
    assert client.get("/api/auth/status").json()["auth_enabled"] is False


def test_setup_is_disabled_under_open_access(client: TestClient) -> None:
    response = client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "supersecreta", "password_confirm": "supersecreta"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "setup_disabled"


def test_session_from_a_previous_token_version_is_rejected(logged_in_client: TestClient) -> None:
    """Simula el reinicio tras un cambio de credenciales hecho por otro worker."""
    assert logged_in_client.get("/api/projects").status_code == 200

    auth_state.bump_token_version(99)

    assert logged_in_client.get("/api/projects").status_code == 401
    assert logged_in_client.get("/api/projects").json()["code"] == "session_expired"
