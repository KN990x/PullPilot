"""`run_command`, the one place the app shells out.

Every other test fakes it, so its own failure paths — timeout, non-zero exit, the
`log_errors=False` probe mode — had no coverage at all. Nothing here needs Docker: the
commands are ordinary shell utilities.
"""

import subprocess

import pytest
from server.services import docker as docker_module
from server.services.docker import get_docker_compose_cmd, run_command


def test_returns_stdout_stripped() -> None:
    assert run_command(["echo", "  hola  "]) == "hola"


def test_a_string_command_is_split_not_shelled_out() -> None:
    """shlex.split + shell=False: the quotes are parsing, not a shell."""
    assert run_command('echo "dos palabras"') == "dos palabras"


def test_no_shell_expansion_happens() -> None:
    """If this reached a shell it would print the contents of the directory."""
    assert run_command(["echo", "*"]) == "*"


def test_runs_in_the_given_cwd(tmp_path) -> None:
    (tmp_path / "marca.txt").write_text("x", encoding="utf-8")

    assert "marca.txt" in run_command(["ls"], cwd=str(tmp_path))


def test_a_non_zero_exit_raises_with_the_stderr(caplog) -> None:
    with pytest.raises(RuntimeError) as exc:
        run_command(["sh", "-c", "echo se rompio >&2; exit 3"])

    assert "se rompio" in str(exc.value)
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_log_errors_false_keeps_a_failed_probe_out_of_the_log(caplog) -> None:
    """Asking whether an image exists locally fails routinely; that is not an error."""
    with pytest.raises(RuntimeError):
        run_command(["sh", "-c", "exit 1"], log_errors=False)

    assert not [r for r in caplog.records if r.levelname == "ERROR"]


def test_a_timeout_raises_and_names_the_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(docker_module, "COMMAND_TIMEOUT", 0.1)

    with pytest.raises(RuntimeError) as exc:
        run_command(["sleep", "5"])

    assert "0.1" in str(exc.value)


def test_a_missing_binary_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """FileNotFoundError is not wrapped: a missing docker is not a command failure."""
    with pytest.raises(FileNotFoundError):
        run_command(["__no_existe_este_binario__"])


def test_compose_v2_is_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_module.subprocess, "run", lambda *a, **kw: None)

    assert get_docker_compose_cmd() == "docker compose"


@pytest.mark.parametrize("failure", [FileNotFoundError, subprocess.CalledProcessError])
def test_falls_back_to_the_v1_binary(
    monkeypatch: pytest.MonkeyPatch, failure: type[Exception]
) -> None:
    def _boom(*_args, **_kwargs):
        raise failure(1, "docker") if failure is subprocess.CalledProcessError else failure()

    monkeypatch.setattr(docker_module.subprocess, "run", _boom)

    assert get_docker_compose_cmd() == "docker-compose"
