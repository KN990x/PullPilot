import pytest
from fastapi.testclient import TestClient
from server import auth_state
from server.config import SESSION_COOKIE_NAME
from server.database import session_scope
from server.models.db import AuthCredential


@pytest.mark.parametrize("path", ["/api/loquesea.json", "/api/projects.json", "/api/x.js"])
def test_api_paths_ending_in_a_public_extension_are_not_public(
    logged_in_client: TestClient, path: str
) -> None:
    """Regression: a .json suffix used to be enough to skip authentication."""
    logged_in_client.post("/api/auth/logout")

    assert logged_in_client.get(path).status_code == 401


def test_openapi_schema_requires_a_session(logged_in_client: TestClient) -> None:
    """The schema describes the whole API and was left open by its .json suffix."""
    logged_in_client.post("/api/auth/logout")

    assert logged_in_client.get("/openapi.json").status_code == 401


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_docs_require_a_session(logged_in_client: TestClient, path: str) -> None:
    logged_in_client.post("/api/auth/logout")

    assert logged_in_client.get(path).status_code == 401


def test_openapi_is_reachable_with_a_session(logged_in_client: TestClient) -> None:
    assert logged_in_client.get("/openapi.json").status_code == 200


def test_status_endpoint_is_reachable_in_every_state(auth_client: TestClient) -> None:
    # Setup pending.
    assert auth_client.get("/api/auth/status").status_code == 200

    auth_client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "supersecreta", "password_confirm": "supersecreta"},
    )
    # With a session.
    assert auth_client.get("/api/auth/status").status_code == 200

    auth_client.post("/api/auth/logout")
    # Configured, no session.
    assert auth_client.get("/api/auth/status").status_code == 200


def test_session_from_a_previous_token_version_is_rejected(logged_in_client: TestClient) -> None:
    """Simulates a restart after another worker changed the credentials."""
    assert logged_in_client.get("/api/projects").status_code == 200

    auth_state.bump_token_version(99)

    assert logged_in_client.get("/api/projects").status_code == 401
    assert logged_in_client.get("/api/projects").json()["code"] == "session_expired"


def test_session_from_a_wiped_account_is_rejected(logged_in_client: TestClient) -> None:
    """The README's recovery is `DELETE FROM auth_credentials` plus a new wizard run.

    That used to reset token_version to 1, which is what the previous account's cookie
    already carried, so the old session sailed through the middleware and reached every
    endpoint while /api/auth/status reported nobody logged in.
    """
    assert logged_in_client.get("/api/projects").status_code == 200
    stale_cookie = logged_in_client.cookies[SESSION_COOKIE_NAME]

    with session_scope() as db:
        db.query(AuthCredential).delete()
        db.commit()
    auth_state.reset_for_tests()

    response = logged_in_client.post(
        "/api/auth/setup",
        json={"username": "otro", "password": "otrasecreta", "password_confirm": "otrasecreta"},
    )
    assert response.status_code == 201, response.text

    # Setup reissued the cookie for the new account; put back the one the previous
    # owner's browser still holds. Same token_version, different user.
    logged_in_client.cookies.clear()
    logged_in_client.cookies.set(SESSION_COOKIE_NAME, stale_cookie)

    assert logged_in_client.get("/api/projects").status_code == 401
    assert logged_in_client.get("/api/projects").json()["code"] == "session_expired"


def test_session_from_a_wiped_account_is_rejected_even_with_the_same_username(
    logged_in_client: TestClient,
) -> None:
    """The usual recovery reuses `admin`. token_version used to restart at 1, which is
    what the previous cookie already carried, so the old session survived the wipe."""
    assert logged_in_client.get("/api/projects").status_code == 200
    stale_cookie = logged_in_client.cookies[SESSION_COOKIE_NAME]

    with session_scope() as db:
        db.query(AuthCredential).delete()
        db.commit()
    auth_state.reset_for_tests()

    response = logged_in_client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "nuevasecreta", "password_confirm": "nuevasecreta"},
    )
    assert response.status_code == 201, response.text

    logged_in_client.cookies.clear()
    logged_in_client.cookies.set(SESSION_COOKIE_NAME, stale_cookie)

    assert logged_in_client.get("/api/projects").status_code == 401
    assert logged_in_client.get("/api/projects").json()["code"] == "session_expired"
