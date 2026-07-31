import shlex
import subprocess
from collections.abc import Sequence

from server.config import COMMAND_TIMEOUT, logger
from server.locale.log_messages import t


def get_docker_compose_cmd() -> str:
    """Prefer Docker Compose V2 (`docker compose`); fall back to legacy `docker-compose` binary.

    The image Dockerfile installs the compose plugin; local dev or odd hosts may only have v1.
    """
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return "docker compose"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "docker-compose"


# Resolved once at import (uvicorn worker / tests).
COMPOSE_CMD = get_docker_compose_cmd()


def run_command(
    cmd: str | Sequence[str],
    cwd: str | None = None,
    *,
    log_exec: bool = True,
    log_errors: bool = True,
    locale: str = "es",
) -> str:
    """Run a command and return its stdout. RuntimeError on failure or timeout.

    `log_errors=False` is for probes where failing is an ordinary answer, such as asking
    whether an image exists locally: those would otherwise fill the log at ERROR level.
    """
    if isinstance(cmd, str):
        cmd_args = shlex.split(cmd)
        cmd_display = cmd
    else:
        cmd_args = list(cmd)
        cmd_display = " ".join(cmd_args)

    try:
        if log_exec:
            logger.info("Exec: %s en %s", cmd_display, cwd)
        result = subprocess.run(
            cmd_args,
            cwd=cwd,
            shell=False,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=COMMAND_TIMEOUT,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired as exc:
        stderr = exc.stderr or ""
        error_msg = (
            f"{t('docker.timeout_command', locale, cmd=cmd_display)}\n"
            f"{t('docker.timeout_configured', locale, seconds=COMMAND_TIMEOUT)}\n"
            f"{t('docker.stderr_label', locale)} {stderr}"
        )
        if log_errors:
            logger.error(error_msg)
        raise RuntimeError(error_msg) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        error_msg = (
            f"{t('docker.error_command', locale, cmd=cmd_display)}\n"
            f"{t('docker.stderr_label', locale)} {stderr}"
        )
        if log_errors:
            logger.error(error_msg)
        raise RuntimeError(error_msg) from exc
