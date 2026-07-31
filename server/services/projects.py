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


def _compose_stack_image_refs(workdir: str, *, locale: str) -> list[str]:
    """Image references the stack declares, one per service.

    `config --images` exists in both Compose v1 and v2, so this survives the COMPOSE_CMD
    fallback in services/docker.py.
    """
    out = run_command(
        f"{COMPOSE_CMD} config --images", cwd=workdir, log_exec=False, locale=locale
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def _local_image_id(ref: str, *, locale: str) -> str | None:
    """Local image ID behind `ref`, or None when it has never been pulled here.

    One `docker image inspect` per reference rather than one batched call: with several
    references the batched form still exits non-zero when any single one is missing, and
    its output can no longer be mapped back to the reference that produced it.
    """
    try:
        out = run_command(
            ["docker", "image", "inspect", "--format", "{{.Id}}", ref],
            log_exec=False,
            log_errors=False,
            locale=locale,
        )
    except Exception:
        return None
    return out.strip() or None


def snapshot_stack_images(workdir: str, *, locale: str = "es") -> dict[str, str]:
    """Map image reference -> local image ID, taken before `compose pull` moves the tags.

    This is what makes a rollback real. With a moving tag (`:latest`, the homelab norm)
    the pull overwrites what the tag points at, so reverting the compose file alone
    redeploys the very image that just broke.
    """
    snapshot: dict[str, str] = {}
    for ref in _compose_stack_image_refs(workdir, locale=locale):
        image_id = _local_image_id(ref, locale=locale)
        if image_id:
            snapshot[ref] = image_id
    return snapshot


def restore_stack_images(
    snapshot: dict[str, str], log: Callable[..., None], *, locale: str
) -> int:
    """Point each tag back at the image it named before the pull. Returns how many moved.

    The newly pulled image is not deleted, only untagged: it stays reachable by ID and
    the safe prune in the scheduler is the one that eventually collects it.
    """
    restored = 0
    for ref, image_id in snapshot.items():
        if _local_image_id(ref, locale=locale) == image_id:
            continue
        try:
            run_command(["docker", "tag", image_id, ref], locale=locale)
        except Exception as exc:
            log(t("update.image_restore_failed", locale, ref=ref, exc=exc), "WARN")
            continue
        log(t("update.image_restored", locale, ref=ref))
        restored += 1
    return restored


def _compose_service_count(path_str: str) -> int | None:
    """Services the stack declares, or None when the file cannot be read.

    `config --services` exists in Compose v1 and v2 alike.
    """
    try:
        out = run_command(
            f"{COMPOSE_CMD} config --services",
            cwd=path_str,
            log_exec=False,
            log_errors=False,
        )
    except Exception:
        return None
    return len([line for line in out.splitlines() if line.strip()]) or None


def _compose_ps_status(path_str: str) -> tuple[str, int]:
    try:
        ids = _compose_ps_q_ids(path_str, log_exec=False)
    except Exception:
        return "error", 0

    running_count = len(ids)
    if running_count == 0:
        return "stopped", 0

    # `ps -q` lists what is up, so fewer than declared means a half-up stack. Reporting
    # that as "running" is how a stack with 2 of 5 services alive looked healthy; the
    # yellow dot the dashboard already draws for `partial` had no way to be reached.
    declared = _compose_service_count(path_str)
    if declared is not None and running_count < declared:
        return "partial", running_count
    return "running", running_count


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

        # One call for every container, not one per container: this loop runs every two
        # seconds for up to a minute, so a six-service stack was spawning ~180 processes
        # per update. `docker inspect` answers a whole list in document order.
        inspect_raw = run_command(
            ["docker", "inspect", *container_ids], log_exec=False, locale=locale
        )
        inspected = json.loads(inspect_raw)

        all_healthy = True
        for container_id, data in zip(container_ids, inspected, strict=False):
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
        # Container-local, unlike the UTC timestamp on the history row: this is the clock
        # `TZ` sets and the one `docker logs` prints, so it lines up when reading both.
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

    # Before `git pull`, so the references match the compose file being replaced, and
    # before `compose pull`, which is what moves the tags.
    image_snapshot: dict[str, str] = {}
    try:
        image_snapshot = snapshot_stack_images(workdir_str, locale=locale)
    except Exception as exc:
        log(t("update.images_snapshot_warn", locale, exc=exc), "WARN")
    if image_snapshot:
        log(t("update.images_snapshot", locale, count=len(image_snapshot)))

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
        log(t("update.rollback_start", locale), "WARN")

        # Each step guarded on its own: failing to move a tag back must not stop the
        # redeploy, which is the part that decides whether the stack ends up running.
        if git_hash_before:
            try:
                run_command(
                    ["git", "reset", "--hard", git_hash_before],
                    cwd=workdir_str,
                    locale=locale,
                )
                log(t("update.rollback_git_reset", locale, commit=git_hash_before[:7]))
            except Exception as reset_exc:
                log(t("update.rollback_git_failed", locale, exc=reset_exc), "WARN")

        restored = restore_stack_images(image_snapshot, log, locale=locale)
        if not git_hash_before and not restored:
            log(t("update.recovery_nothing_to_revert", locale), "WARN")

        # Unconditional: `compose stop`/`down` already ran, so bailing out here is what
        # used to leave a stack without a Git repo down after a failed deploy.
        try:
            log(t("update.rollback_redeploy", locale))
            run_command(
                f"{COMPOSE_CMD} up -d --build --remove-orphans",
                cwd=workdir_str,
                locale=locale,
            )
            log(t("update.rollback_success", locale), "SUCCESS")
            logs.append(t("update.rollback_note", locale))
        except Exception as redeploy_exc:
            log(t("update.rollback_fatal", locale, exc=redeploy_exc), "ERROR")

        return False, logs
