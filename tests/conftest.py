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
    """Leave the authentication state as it was.

    The test database is in-memory with StaticPool, one connection shared by the whole
    process: without this, a test that creates credentials leaves them behind and the
    outcome depends on ordering.
    """
    yield
    with session_scope() as db:
        db.query(AuthCredential).delete()
        db.commit()
    auth_state.reset_for_tests()
    login_rate_limit._failed_attempts.clear()


@pytest.fixture()
def auth_client() -> TestClient:
    """Client with no credentials created yet: setup is pending."""
    with TestClient(app) as c:
        # After entering the context manager: the lifespan calls prime() and would
        # overwrite anything set up earlier.
        auth_state.reset_for_tests()
        yield c


@pytest.fixture()
def client(auth_client: TestClient) -> TestClient:
    """Client with the wizard completed and a session open.

    The default, because no escape hatch opens the API any more: a session is the only way
    to reach an endpoint, exactly as in production.
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


# Historic alias: several auth tests ask for "the logged-in client" by name.
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
