import pytest
from sqlalchemy.orm import Session

from server.services import auth as auth_service


def test_hash_format_is_self_describing() -> None:
    stored = auth_service.hash_password("supersecreta")
    parts = stored.split("$")

    assert len(parts) == 6
    assert parts[0] == "scrypt"
    assert int(parts[1]) == auth_service.SCRYPT_N
    assert int(parts[2]) == auth_service.SCRYPT_R
    assert int(parts[3]) == auth_service.SCRYPT_P


def test_hash_round_trip() -> None:
    stored = auth_service.hash_password("supersecreta")

    assert auth_service.verify_password("supersecreta", stored) is True
    assert auth_service.verify_password("otracosa", stored) is False


def test_same_password_produces_different_hashes() -> None:
    """Sal aleatoria: dos instalaciones con la misma contraseña no comparten hash."""
    assert auth_service.hash_password("supersecreta") != auth_service.hash_password("supersecreta")


@pytest.mark.parametrize(
    "stored",
    [
        "basura",
        "",
        "scrypt$x$8$1$YQ==$Yg==",
        "bcrypt$16384$8$1$YQ==$Yg==",
        "scrypt$16384$8$1$no-es-base64!$Yg==",
        # n desorbitado: sin la cota, verificar sería una bomba de memoria.
        "scrypt$1099511627776$8$1$YQ==$Yg==",
    ],
)
def test_corrupt_hash_is_rejected_without_raising(stored: str) -> None:
    assert auth_service.verify_password("supersecreta", stored) is False


def test_verify_honours_parameters_stored_in_the_hash() -> None:
    """Un hash antiguo con parámetros más flojos sigue validando."""
    stored = auth_service.hash_password("supersecreta", n=2**13)

    assert int(stored.split("$")[1]) == 2**13
    assert auth_service.verify_password("supersecreta", stored) is True


@pytest.mark.parametrize("bad", ["ab", "a" * 65, "con espacio", "acentué"])
def test_validate_username_rejects(bad: str) -> None:
    with pytest.raises(ValueError):
        auth_service.validate_username(bad)


@pytest.mark.parametrize("bad", ["", "corta", "a" * 129])
def test_validate_password_rejects(bad: str) -> None:
    with pytest.raises(ValueError):
        auth_service.validate_password(bad)


def test_setup_lifecycle(db_session: Session) -> None:
    assert auth_service.is_setup_complete(db_session) is False

    row = auth_service.create_initial_credentials(
        db_session, username="admin", password="supersecreta"
    )

    assert auth_service.is_setup_complete(db_session) is True
    assert row.username == "admin"
    assert row.token_version == 1
    assert "supersecreta" not in row.password_hash


def test_second_setup_is_rejected(db_session: Session) -> None:
    auth_service.create_initial_credentials(db_session, username="admin", password="supersecreta")

    with pytest.raises(auth_service.SetupAlreadyCompletedError):
        auth_service.create_initial_credentials(
            db_session, username="otro", password="supersecreta"
        )


def test_verify_credentials(db_session: Session) -> None:
    auth_service.create_initial_credentials(db_session, username="admin", password="supersecreta")

    assert auth_service.verify_credentials(db_session, username="admin", password="supersecreta")
    assert not auth_service.verify_credentials(db_session, username="root", password="supersecreta")
    assert not auth_service.verify_credentials(db_session, username="admin", password="mala")


def test_verify_credentials_without_setup(db_session: Session) -> None:
    assert not auth_service.verify_credentials(
        db_session, username="admin", password="supersecreta"
    )


def test_change_credentials_requires_current_password(db_session: Session) -> None:
    auth_service.create_initial_credentials(db_session, username="admin", password="supersecreta")

    with pytest.raises(auth_service.InvalidCredentialsError):
        auth_service.change_credentials(
            db_session, current_password="mala", new_password="nuevacontra"
        )


def test_change_credentials_bumps_token_version(db_session: Session) -> None:
    auth_service.create_initial_credentials(db_session, username="admin", password="supersecreta")

    row = auth_service.change_credentials(
        db_session, current_password="supersecreta", new_password="nuevacontra"
    )
    assert row.token_version == 2
    assert auth_service.verify_credentials(db_session, username="admin", password="nuevacontra")

    row = auth_service.change_credentials(
        db_session, current_password="nuevacontra", new_username="otro"
    )
    assert row.token_version == 3
    assert row.username == "otro"


def test_change_credentials_without_changes(db_session: Session) -> None:
    auth_service.create_initial_credentials(db_session, username="admin", password="supersecreta")

    with pytest.raises(ValueError, match="nada que cambiar"):
        auth_service.change_credentials(
            db_session, current_password="supersecreta", new_username="admin"
        )


def test_change_credentials_without_setup(db_session: Session) -> None:
    with pytest.raises(auth_service.SetupRequiredError):
        auth_service.change_credentials(
            db_session, current_password="supersecreta", new_password="nuevacontra"
        )


def test_seed_from_env_creates_the_row(db_session: Session) -> None:
    assert auth_service.seed_from_env(db_session, username="admin", password="supersecreta") is True
    assert auth_service.verify_credentials(db_session, username="admin", password="supersecreta")


@pytest.mark.parametrize(
    ("username", "password"),
    [(None, "supersecreta"), ("admin", None), (None, None), ("admin", "corta")],
)
def test_seed_from_env_no_ops(db_session: Session, username, password) -> None:
    assert auth_service.seed_from_env(db_session, username=username, password=password) is False
    assert auth_service.is_setup_complete(db_session) is False


def test_seed_from_env_does_not_override_the_database(db_session: Session) -> None:
    """La base de datos manda: el entorno solo siembra una instalación vacía."""
    auth_service.create_initial_credentials(db_session, username="admin", password="supersecreta")

    assert auth_service.seed_from_env(db_session, username="otro", password="otracontra") is False
    assert auth_service.verify_credentials(db_session, username="admin", password="supersecreta")
