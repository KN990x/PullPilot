import datetime
import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from server.config import HEALTHCHECK_TIMEOUT, PROJECTS_ROOT, logger
from server.locale.log_messages import t
from server.models.db import ProjectSettings
from server.services.docker import COMPOSE_CMD, run_command


IGNORED_PROJECT_NAMES = {"pullpilot", "pullpilot-ui", "docker-updater", "data"}


def _resolved_projects_root() -> Path:
    return PROJECTS_ROOT.resolve()


def resolve_allowed_project_workdir(raw: str, *, locale: str = "es") -> Path:
    """Resolve the stack path and check it stays under the stacks root."""
    root = _resolved_projects_root()
    candidate = Path(raw).expanduser()
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(t("error.path_resolve_failed", locale, exc=exc)) from exc
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(t("error.path_outside_root", locale)) from None
    return resolved


def compose_stack_allowed(path: Path) -> bool:
    """True if the directory is a valid compose stack under the stacks root."""
    try:
        resolved = path.expanduser().resolve()
        resolved.relative_to(_resolved_projects_root())
    except (OSError, RuntimeError, ValueError):
        return False
    return compose_project_path_ok(resolved)


def _dir_has_compose_file(path: Path) -> bool:
    return (path / "docker-compose.yml").exists() or (path / "docker-compose.yaml").exists()


def compose_project_path_ok(path: Path) -> bool:
    """An existing directory with docker-compose.yml or .yaml, same rule as the scan."""
    return path.is_dir() and _dir_has_compose_file(path)


def _compose_ps_q_ids(
    project_path: str, *, log_exec: bool, locale: str = "es"
) -> list[str]:
    """Container IDs from `docker compose ps -q` (non-empty lines only)."""
    out = run_command(
        f"{COMPOSE_CMD} ps -q", cwd=project_path, log_exec=log_exec, locale=locale
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def _compose_ps_status(path_str: str) -> tuple[str, int]:
    try:
        ids = _compose_ps_q_ids(path_str, log_exec=False)
    except Exception:
        return "error", 0
    running_count = len(ids)
    status = "running" if running_count > 0 else "stopped"
    return status, running_count


def _wait_for_compose_healthy(
    project_path: str,
    log: Callable[..., None],
    *,
    locale: str,
) -> None:
    start_time = time.time()
    while True:
        elapsed = time.time() - start_time
        if elapsed > HEALTHCHECK_TIMEOUT:
            raise RuntimeError(
                t("health.timeout", locale, timeout=HEALTHCHECK_TIMEOUT)
            )

        try:
            container_ids = _compose_ps_q_ids(
                project_path, log_exec=True, locale=locale
            )
        except Exception:
            container_ids = []

        if not container_ids:
            if elapsed > 5:
                raise RuntimeError(t("health.no_containers", locale))
            time.sleep(1)
            continue

        all_healthy = True
        for container_id in container_ids:
            inspect_raw = run_command(
                ["docker", "inspect", container_id], locale=locale
            )
            data = json.loads(inspect_raw)[0]
            state = data.get("State", {})
            status = state.get("Status")
            health = state.get("Health", {}).get("Status")
            cid = container_id[:12]

            if status == "restarting":
                raise RuntimeError(t("health.restarting", locale, cid=cid))
            if status in {"exited", "dead"}:
                exit_code = state.get("ExitCode")
                if exit_code != 0:
                    raise RuntimeError(
                        t("health.exited", locale, cid=cid, code=exit_code)
                    )

            if health == "unhealthy":
                raise RuntimeError(t("health.unhealthy", locale, cid=cid))

            if health == "starting":
                all_healthy = False
                continue

            if health is None and status != "running":
                all_healthy = False

        if all_healthy:
            log(t("update.health_passed", locale), "SUCCESS")
            break

        time.sleep(2)


def scan_projects_logic(db: Session) -> list[dict]:
    if not PROJECTS_ROOT.exists():
        return []

    pending_db_write = False
    ordered: list[tuple[str, Path, ProjectSettings]] = []

    for path in PROJECTS_ROOT.iterdir():
        entry = path.name
        if entry.lower() in IGNORED_PROJECT_NAMES:
            continue

        if not compose_project_path_ok(path):
            continue

        proj = db.query(ProjectSettings).filter(ProjectSettings.name == entry).first()
        if not proj:
            proj = ProjectSettings(name=entry, path=str(path))
            db.add(proj)
            pending_db_write = True
        elif proj.path != str(path):
            proj.path = str(path)
            pending_db_write = True

        ordered.append((entry, path, proj))

    if pending_db_write:
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.warning(
                "No se pudo persistir cambios del escaneo de proyectos (altas o rutas)."
            )

    status_by_entry: dict[str, tuple[str, int]] = {}
    if ordered:
        max_workers = min(8, len(ordered))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_entry = {
                pool.submit(_compose_ps_status, str(path)): entry
                for entry, path, _ in ordered
            }
            for fut in as_completed(future_to_entry):
                entry = future_to_entry[fut]
                status_by_entry[entry] = fut.result()

    found: list[dict] = []
    for entry, path, proj in ordered:
        status, running_count = status_by_entry[entry]
        found.append(
            {
                "name": entry,
                "path": str(path),
                "status": status,
                "containers": running_count,
                "excluded": proj.excluded,
                "full_stop": proj.full_stop,
            }
        )

    return found


def update_single_project_logic(
    name: str, db: Session, *, locale: str = "es"
) -> tuple[bool, list[str]]:
    project = db.query(ProjectSettings).filter(ProjectSettings.name == name).first()
    if not project:
        err = t("error.db_project_not_found", locale)
        return False, [f"{t('error.error_prefix', locale)} {err}"]

    logs: list[str] = []

    def log(message: str, level: str = "INFO") -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        if level == "SUCCESS":
            prefix = t("log.prefix_ok", locale)
        elif level == "ERROR":
            prefix = t("log.prefix_err", locale)
        elif level == "WARN":
            prefix = t("log.prefix_warn", locale)
        else:
            prefix = t("log.prefix_info", locale)
        logs.append(f"[{ts}] {prefix} {message}")

    log(t("update.header", locale, name=name))

    try:
        workdir = resolve_allowed_project_workdir(project.path, locale=locale)
    except ValueError as exc:
        return False, [f"{t('error.error_prefix', locale)} {exc}"]

    if not compose_project_path_ok(workdir):
        err = t("error.invalid_compose_stack", locale)
        return False, [f"{t('error.error_prefix', locale)} {err}"]

    workdir_str = str(workdir)

    git_hash_before: str | None = None
    is_git_repo = (workdir / ".git").is_dir()

    if is_git_repo:
        try:
            git_hash_before = run_command(
                "git rev-parse HEAD", cwd=workdir_str, locale=locale
            )
            log(
                t("update.git_snapshot", locale, commit=git_hash_before[:7]),
            )
        except Exception as exc:
            log(t("update.git_snapshot_warn", locale, exc=exc), "WARN")

    try:
        if is_git_repo:
            log(t("update.git_pull", locale))
            run_command("git pull", cwd=workdir_str, locale=locale)

        log(t("update.compose_pull", locale))
        run_command(f"{COMPOSE_CMD} pull", cwd=workdir_str, locale=locale)

        if project.full_stop:
            log(t("update.full_stop_down", locale))
            run_command(f"{COMPOSE_CMD} down", cwd=workdir_str, locale=locale)
        else:
            log(t("update.compose_stop", locale))
            run_command(f"{COMPOSE_CMD} stop", cwd=workdir_str, locale=locale)

        log(t("update.compose_up", locale))
        run_command(
            f"{COMPOSE_CMD} up -d --build --remove-orphans",
            cwd=workdir_str,
            locale=locale,
        )

        log(t("update.health_wait", locale, timeout=HEALTHCHECK_TIMEOUT))
        _wait_for_compose_healthy(workdir_str, log, locale=locale)

        logs.append(t("update.completed_banner", locale))
        return True, logs
    except Exception as exc:
        log(t("update.critical_failure", locale, exc=exc), "ERROR")

        if git_hash_before:
            log(t("update.rollback_start", locale), "WARN")
            try:
                run_command(
                    ["git", "reset", "--hard", git_hash_before],
                    cwd=workdir_str,
                    locale=locale,
                )
                log(t("update.rollback_git_reset", locale, commit=git_hash_before[:7]))

                log(t("update.rollback_redeploy", locale))
                run_command(
                    f"{COMPOSE_CMD} up -d --build --remove-orphans",
                    cwd=workdir_str,
                    locale=locale,
                )
                log(t("update.rollback_success", locale), "SUCCESS")
                logs.append(t("update.rollback_note", locale))
            except Exception as rollback_exc:
                log(t("update.rollback_fatal", locale, exc=rollback_exc), "ERROR")
        else:
            log(t("update.rollback_impossible", locale), "WARN")

        return False, logs
