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
from server.models.db import ProjectSettings, ScheduledTask
from server.services.docker import COMPOSE_CMD, run_command

IGNORED_PROJECT_NAMES = {"pullpilot", "pullpilot-ui", "docker-updater", "data"}


def _git_argv(workdir: str, *args: str) -> list[str]:
    """Git argv that bind-mounted clones will accept.

    Git 2.35+ refuses a repo whose directory owner is not the process user
    (`fatal: dubious ownership`). Stacks are bind-mounted from the host and this
    container runs as root, so every git call needs `safe.directory` set to the workdir.
    """
    return ["git", "-c", f"safe.directory={workdir}", *args]


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
    project_path: str,
    *,
    log_exec: bool,
    locale: str = "es",
    all_containers: bool = False,
) -> list[str]:
    """Container IDs from `docker compose ps -q` (non-empty lines only).

    `all_containers=True` is `ps -a -q`: running or not. The health loop needs that
    when every service is a one-shot that has already exited.
    """
    flag = "ps -a -q" if all_containers else "ps -q"
    out = run_command(
        f"{COMPOSE_CMD} {flag}", cwd=project_path, log_exec=log_exec, locale=locale
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


def _compose_created_count(path_str: str) -> int | None:
    """Containers Compose has created for the stack, running or not.

    Counted instead of the services `config --services` declares: that lists every service
    in the file, including ones gated behind `profiles:` that were never meant to run, so
    any stack using profiles showed a permanent yellow `partial` dot.
    """
    try:
        out = run_command(
            f"{COMPOSE_CMD} ps -a -q",
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

    # `ps -q` lists what is up, so fewer than exist means a half-up stack. Reporting that
    # as "running" is how a stack with 2 of 5 services alive looked healthy; the yellow
    # dot the dashboard already draws for `partial` had no way to be reached.
    created = _compose_created_count(path_str)
    if created is not None and running_count < created:
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
            # A stack of only one-shots (backup, certbot, a migration) has nothing
            # running after `up -d`. `ps -q` is empty; `ps -a` still has the exited IDs.
            # Giving up here rolled back a deploy that had in fact worked and re-ran the job.
            try:
                container_ids = _compose_ps_q_ids(
                    project_path,
                    log_exec=False,
                    locale=locale,
                    all_containers=True,
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
        #
        # Tolerated rather than raised: the IDs come from a `ps -q` up to two seconds ago,
        # so a container recreated in between makes `docker inspect` exit non-zero. That
        # used to reach the caller's rollback and undo a deploy over a transient race.
        # A short list is the same race, and zip(strict=False) silently called the missing
        # containers healthy. The loop's own timeout stays the real backstop.
        try:
            inspect_raw = run_command(
                ["docker", "inspect", *container_ids],
                log_exec=False,
                log_errors=False,
                locale=locale,
            )
            inspected = json.loads(inspect_raw)
        except Exception:
            time.sleep(2)
            continue

        if len(inspected) != len(container_ids):
            time.sleep(2)
            continue

        all_healthy = True
        for container_id, data in zip(container_ids, inspected, strict=True):
            state = data.get("State", {})
            status = state.get("Status")
            # `Health: null` is a present key, not a missing one: `.get("Health", {})`
            # still returns None and `.get("Status")` on it used to raise and roll back.
            health = (state.get("Health") or {}).get("Status")
            cid = container_id[:12]

            if status == "restarting":
                raise RuntimeError(t("health.restarting", locale, cid=cid))
            if status in {"exited", "dead"}:
                exit_code = state.get("ExitCode")
                if exit_code != 0:
                    raise RuntimeError(
                        t("health.exited", locale, cid=cid, code=exit_code)
                    )
                # A one-shot service that finished cleanly: an init container, a migration
                # or a backup job. It is never going to reach "running", so leaving it to
                # the check below meant the loop could not converge, timed out, and the
                # timeout rolled back a deploy that had in fact worked.
                continue

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


def _prune_orphan_projects(db: Session, seen: set[str]) -> list[str]:
    """Drop rows for stacks that are gone, but only the ones carrying no settings.

    The table only ever grew, like the history and the two lock registries before it. It is
    deliberately not a blanket delete: a row disappears from `seen` for reasons other than
    the user removing the stack — a volume mounted at the wrong path, or a compose file
    missing for the seconds someone is editing it — and wiping `excluded` on a stack the
    user had fenced off would then be a silent, unrecoverable change. A row with default
    settings has nothing to lose: the next scan recreates it identically.

    Returns the names that were deleted, so the caller can retire their schedules and
    commit once.
    """
    # Nothing found at all is the shape of a bad mount far more often than of a homelab
    # with zero stacks, and pruning is never urgent enough to risk acting on it.
    if not seen:
        return []

    orphans = (
        db.query(ProjectSettings)
        .filter(
            ProjectSettings.name.notin_(seen),
            ProjectSettings.excluded.is_(False),
            ProjectSettings.full_stop.is_(False),
        )
        .all()
    )
    names = [row.name for row in orphans]
    for row in orphans:
        db.delete(row)
    if names:
        # Same symptom the create endpoint already refuses: a schedule whose target is
        # gone stayed active, fired, logged one line, and the UI listed it forever.
        db.query(ScheduledTask).filter(
            ScheduledTask.target.in_(names),
            ScheduledTask.active.is_(True),
        ).update({"active": False}, synchronize_session=False)
        logger.info(
            "Escaneo: %s proyecto(s) sin carpeta y sin ajustes retirados de la BD.",
            len(names),
        )
    return names


def scan_projects_logic(db: Session) -> list[dict]:
    if not PROJECTS_ROOT.exists():
        return []

    pending_db_write = False
    ordered: list[tuple[str, Path, ProjectSettings]] = []

    # One query instead of one per directory. The dashboard calls this on every entry, on
    # every manual refresh and after every update, and `name` is unique and indexed, so the
    # whole table is a cheap read whatever the stack count.
    by_name = {row.name: row for row in db.query(ProjectSettings).all()}

    try:
        entries = list(PROJECTS_ROOT.iterdir())
    except OSError as exc:
        # Same user-facing shape as a missing folder: the mount is there but unreadable
        # (permissions, a broken bind). A 500 painted the SPA's "check STACKS_PATH" panel
        # as if the path itself were wrong.
        logger.warning(
            "No se pudo listar la carpeta de stacks %s: %s", PROJECTS_ROOT, exc
        )
        return []

    for path in entries:
        entry = path.name
        if entry.lower() in IGNORED_PROJECT_NAMES:
            continue

        # Containment checked here, not just at update time, and the resolved path is what
        # gets stored. Accepting the raw path listed symlinked stacks on the dashboard that
        # every update then rejected with a "possible tampered DB data" message, and that
        # the scheduler skipped without saying so.
        if not compose_stack_allowed(path):
            continue
        resolved = str(path.resolve())

        proj = by_name.get(entry)
        if not proj:
            proj = ProjectSettings(name=entry, path=resolved)
            db.add(proj)
            by_name[entry] = proj
            pending_db_write = True
        elif proj.path != resolved:
            proj.path = resolved
            pending_db_write = True

        ordered.append((entry, path, proj))

    pruned_names = _prune_orphan_projects(db, {entry for entry, _path, _proj in ordered})
    if pruned_names:
        pending_db_write = True

    if pending_db_write:
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.warning(
                "No se pudo persistir cambios del escaneo de proyectos (altas o rutas)."
            )
        else:
            if pruned_names:
                # Lazy: scheduler imports this module at load time.
                from server.services.scheduler import refresh_scheduler_jobs

                refresh_scheduler_jobs()

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
    # `git reset --hard` in the rollback deletes uncommitted work. Editing compose files
    # or .env in place inside a cloned stack is normal in a homelab, so a dirty tree
    # disables that one step; everything else about the rollback still runs.
    git_tree_dirty = False
    is_git_repo = (workdir / ".git").is_dir()

    if is_git_repo:
        try:
            git_hash_before = run_command(
                _git_argv(workdir_str, "rev-parse", "HEAD"),
                cwd=workdir_str,
                locale=locale,
            )
            log(
                t("update.git_snapshot", locale, commit=git_hash_before[:7]),
            )
        except Exception as exc:
            log(t("update.git_snapshot_warn", locale, exc=exc), "WARN")

        try:
            git_tree_dirty = bool(
                run_command(
                    _git_argv(workdir_str, "status", "--porcelain"),
                    cwd=workdir_str,
                    log_exec=False,
                    locale=locale,
                ).strip()
            )
        except Exception:
            # Unknown state: assume dirty. The branch being guarded is the destructive one.
            git_tree_dirty = True
        if git_tree_dirty:
            log(t("update.git_dirty", locale), "WARN")

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
            run_command(
                _git_argv(workdir_str, "pull"), cwd=workdir_str, locale=locale
            )

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
        git_reverted = False
        if git_hash_before and git_tree_dirty:
            log(t("update.rollback_git_skipped_dirty", locale), "WARN")
        elif git_hash_before:
            try:
                run_command(
                    _git_argv(workdir_str, "reset", "--hard", git_hash_before),
                    cwd=workdir_str,
                    locale=locale,
                )
                log(t("update.rollback_git_reset", locale, commit=git_hash_before[:7]))
                git_reverted = True
            except Exception as reset_exc:
                log(t("update.rollback_git_failed", locale, exc=reset_exc), "WARN")

        restored = restore_stack_images(image_snapshot, log, locale=locale)
        if not git_reverted and not restored:
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
