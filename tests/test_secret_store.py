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
    """A file another worker is halfway through writing must not sign sessions."""
    path = tmp_path / SECRET_FILENAME
    path.write_text("corto", encoding="utf-8")

    secret, source = load_or_create_session_secret(tmp_path)

    assert source == "file"
    assert len(secret) == 64


# The guard belongs on this one: root writes through mode 0500, so under root the
# assertion below fails. It used to sit on a near-duplicate that asserted nothing, which
# meant the no-op skipped and the real test failed.
@pytest.mark.skipif(os.geteuid() == 0, reason="root ignora los permisos del directorio")
def test_read_only_directory_degrades_to_ephemeral(tmp_path: Path) -> None:
    """A badly mounted volume still boots; it only loses sessions on restart."""
    target = tmp_path / "ro"
    target.mkdir()
    target.chmod(0o500)
    try:
        secret, source = load_or_create_session_secret(target)
    finally:
        target.chmod(0o700)

    assert source == "ephemeral"
    assert len(secret) == 64
