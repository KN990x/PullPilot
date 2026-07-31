import os
import tempfile

os.environ["PULLPILOT_TESTING"] = "1"
if "DATA_DIR" not in os.environ:
    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="pullpilot_test_")

import pytest
from fastapi.testclient import TestClient

from server import auth_state, login_rate_limit
from server.app import app
from server.database import session_scope
from server.models.db import AuthCredential
from server.services import auth as auth_service

SETUP_USERNAME = "admin"
SETUP_PASSWORD = "supersecreta"


@pytest.fixture(autouse=True)
def _clean_auth_state():
    """Deja el estado de autenticación como estaba.

    La base de datos de test es in-memory con StaticPool, o sea una única conexión
    compartida por todo el proceso: sin esto, un test que crea credenciales las deja
    puestas para todos los que vengan detrás y el resultado depende del orden.
    """
    yield
    with session_scope() as db:
        db.query(AuthCredential).delete()
        db.commit()
    auth_state.reset_for_tests()
    login_rate_limit._failed_attempts.clear()


@pytest.fixture()
def auth_client() -> TestClient:
    """Cliente sin credenciales creadas: la instalación está pendiente."""
    with TestClient(app) as c:
        # Después de entrar en el context manager: el lifespan llama a prime() y
        # sobrescribiría el estado si lo preparásemos antes.
        auth_state.reset_for_tests()
        yield c


@pytest.fixture()
def client(auth_client: TestClient) -> TestClient:
    """Cliente con el asistente completado y la sesión abierta.

    Es el cliente por defecto porque ya no existe ninguna escotilla que abra la API: la
    única forma de llegar a un endpoint es con sesión, igual que en producción.
    """
    response = auth_client.post(
        "/api/auth/setup",
        json={
            "username": SETUP_USERNAME,
            "password": SETUP_PASSWORD,
            "password_confirm": SETUP_PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return auth_client


# Alias histórico: varios tests de autenticación piden explícitamente "el cliente logueado".
@pytest.fixture()
def logged_in_client(client: TestClient) -> TestClient:
    return client


@pytest.fixture()
def db_session():
    with session_scope() as db:
        yield db


@pytest.fixture()
def auth_svc():
    return auth_service
