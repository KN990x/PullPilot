from fastapi.testclient import TestClient
from server.app import app
from server.login_rate_limit import MAX_ATTEMPTS
from tests.conftest import SETUP_PASSWORD, SETUP_USERNAME

SETUP_BODY = {
    "username": SETUP_USERNAME,
    "password": SETUP_PASSWORD,
    "password_confirm": SETUP_PASSWORD,
}


def test_status_is_public_before_setup(auth_client: TestClient) -> None:
    response = auth_client.get("/api/auth/status")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "setup_complete": False,
        "authenticated": False,
        "username": None,
    }


def test_api_is_closed_before_setup(auth_client: TestClient) -> None:
    response = auth_client.get("/api/projects")

    assert response.status_code == 401
    assert response.json()["code"] == "setup_required"


def test_setup_creates_credentials_and_opens_session(auth_client: TestClient) -> None:
    response = auth_client.post("/api/auth/setup", json=SETUP_BODY)

    assert response.status_code == 201
    assert response.json()["username"] == SETUP_USERNAME
    assert "pullpilot_session" in auth_client.cookies

    status = auth_client.get("/api/auth/status").json()
    assert status["setup_complete"] is True
    assert status["authenticated"] is True
    assert status["username"] == SETUP_USERNAME
    assert auth_client.get("/api/projects").status_code == 200


def test_setup_twice_is_rejected(logged_in_client: TestClient) -> None:
    response = logged_in_client.post(
        "/api/auth/setup",
        json={"username": "otro", "password": "otracontra", "password_confirm": "otracontra"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "setup_already_completed"


def test_setup_rejects_mismatched_passwords(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/auth/setup",
        json={
            "username": SETUP_USERNAME,
            "password": SETUP_PASSWORD,
            "password_confirm": "otracontrasena",
        },
    )

    assert response.status_code == 422
    assert auth_client.get("/api/auth/status").json()["setup_complete"] is False


def test_validation_error_does_not_echo_the_password(auth_client: TestClient) -> None:
    """Pydantic echoes the rejected value in `input`; under /api/auth that is the password."""
    response = auth_client.post(
        "/api/auth/setup",
        json={"username": SETUP_USERNAME, "password": "corta", "password_confirm": "corta"},
    )

    assert response.status_code == 422
    assert "corta" not in response.text
    assert '"input"' not in response.text


def test_login_with_wrong_password(logged_in_client: TestClient) -> None:
    logged_in_client.post("/api/auth/logout")

    response = logged_in_client.post(
        "/api/auth/login", json={"username": SETUP_USERNAME, "password": "mala"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    # Never distinguish "no such user" from "wrong password".
    assert SETUP_USERNAME not in response.json()["detail"]


def test_login_and_logout_round_trip(logged_in_client: TestClient) -> None:
    assert logged_in_client.post("/api/auth/logout").status_code == 200
    assert logged_in_client.get("/api/projects").status_code == 401

    response = logged_in_client.post(
        "/api/auth/login", json={"username": SETUP_USERNAME, "password": SETUP_PASSWORD}
    )

    assert response.status_code == 200
    assert logged_in_client.get("/api/projects").status_code == 200


def test_logout_is_idempotent(auth_client: TestClient) -> None:
    """Logging out of an already expired session must not 401."""
    assert auth_client.post("/api/auth/logout").status_code == 200
    assert auth_client.post("/api/auth/logout").status_code == 200


def test_login_before_setup(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/auth/login", json={"username": SETUP_USERNAME, "password": SETUP_PASSWORD}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "setup_required"


def test_login_rate_limit(logged_in_client: TestClient) -> None:
    logged_in_client.post("/api/auth/logout")

    for _ in range(MAX_ATTEMPTS):
        logged_in_client.post(
            "/api/auth/login", json={"username": SETUP_USERNAME, "password": "mala"}
        )

    response = logged_in_client.post(
        "/api/auth/login", json={"username": SETUP_USERNAME, "password": SETUP_PASSWORD}
    )

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert int(response.headers["Retry-After"]) > 0


def test_change_credentials_requires_current_password(logged_in_client: TestClient) -> None:
    response = logged_in_client.post(
        "/api/auth/credentials",
        json={
            "current_password": "mala",
            "new_password": "nuevacontra",
            "new_password_confirm": "nuevacontra",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_current_password"


def test_change_password_switches_the_valid_credentials(logged_in_client: TestClient) -> None:
    response = logged_in_client.post(
        "/api/auth/credentials",
        json={
            "current_password": SETUP_PASSWORD,
            "new_password": "nuevacontra",
            "new_password_confirm": "nuevacontra",
        },
    )
    assert response.status_code == 200
    # Our own session is reissued, so it keeps working.
    assert logged_in_client.get("/api/projects").status_code == 200

    logged_in_client.post("/api/auth/logout")
    assert (
        logged_in_client.post(
            "/api/auth/login", json={"username": SETUP_USERNAME, "password": SETUP_PASSWORD}
        ).status_code
        == 401
    )
    assert (
        logged_in_client.post(
            "/api/auth/login", json={"username": SETUP_USERNAME, "password": "nuevacontra"}
        ).status_code
        == 200
    )


def test_change_credentials_invalidates_other_sessions(logged_in_client: TestClient) -> None:
    other = TestClient(app)
    other.cookies.update(logged_in_client.cookies)
    assert other.get("/api/projects").status_code == 200

    logged_in_client.post(
        "/api/auth/credentials",
        json={
            "current_password": SETUP_PASSWORD,
            "new_password": "nuevacontra",
            "new_password_confirm": "nuevacontra",
        },
    )

    assert other.get("/api/projects").status_code == 401


def test_change_username(logged_in_client: TestClient) -> None:
    response = logged_in_client.post(
        "/api/auth/credentials",
        json={"current_password": SETUP_PASSWORD, "username": "nuevousuario"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "nuevousuario"
    assert logged_in_client.get("/api/auth/status").json()["username"] == "nuevousuario"


def test_change_credentials_without_changes(logged_in_client: TestClient) -> None:
    response = logged_in_client.post(
        "/api/auth/credentials",
        json={"current_password": SETUP_PASSWORD},
    )

    assert response.status_code == 422


def test_change_credentials_requires_session(auth_client: TestClient) -> None:
    auth_client.post("/api/auth/setup", json=SETUP_BODY)
    auth_client.post("/api/auth/logout")

    response = auth_client.post(
        "/api/auth/credentials",
        json={
            "current_password": SETUP_PASSWORD,
            "new_password": "nuevacontra",
            "new_password_confirm": "nuevacontra",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "session_expired"


def test_legacy_login_redirects_to_the_spa(auth_client: TestClient) -> None:
    """PWAs installed on the old bundle still do location.replace('/login')."""
    response = auth_client.get("/login", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/"


def test_legacy_login_post_is_gone(auth_client: TestClient) -> None:
    response = auth_client.post("/login", data={"username": "a", "password": "b"})

    assert response.status_code == 405


def test_legacy_logout_clears_the_session(logged_in_client: TestClient) -> None:
    response = logged_in_client.post("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert logged_in_client.get("/api/projects").status_code == 401
