import os
import stat
from pathlib import Path

import pytest

from server.secret_store import SECRET_FILENAME, load_or_create_session_secret


def test_creates_file_with_owner_only_permissions(tmp_path: Path) -> None:
    secret, source = load_or_create_session_secret(tmp_path)

    assert source == "file"
    assert len(secret) == 64
    path = tmp_path / SECRET_FILENAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_second_call_reuses_the_same_secret(tmp_path: Path) -> None:
    first, _ = load_or_create_session_secret(tmp_path)
    second, source = load_or_create_session_secret(tmp_path)

    assert first == second
    assert source == "file"


def test_env_value_wins_and_writes_nothing(tmp_path: Path) -> None:
    secret, source = load_or_create_session_secret(tmp_path, "secreto-del-entorno")

    assert secret == "secreto-del-entorno"
    assert source == "env"
    assert not (tmp_path / SECRET_FILENAME).exists()


def test_truncated_file_is_replaced(tmp_path: Path) -> None:
    """Un fichero a medio escribir por otro worker no puede firmar sesiones."""
    path = tmp_path / SECRET_FILENAME
    path.write_text("corto", encoding="utf-8")

    secret, source = load_or_create_session_secret(tmp_path)

    assert source == "file"
    assert len(secret) == 64


def test_read_only_directory_degrades_to_ephemeral(tmp_path: Path) -> None:
    """Con el volumen mal montado la app arranca igual, solo pierde las sesiones."""
    target = tmp_path / "ro"
    target.mkdir()
    target.chmod(0o500)
    try:
        secret, source = load_or_create_session_secret(target)
    finally:
        target.chmod(0o700)

    assert source == "ephemeral"
    assert len(secret) == 64


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignora los permisos del directorio")
def test_read_only_directory_does_not_raise(tmp_path: Path) -> None:
    target = tmp_path / "ro2"
    target.mkdir()
    target.chmod(0o500)
    try:
        load_or_create_session_secret(target)
    finally:
        target.chmod(0o700)
