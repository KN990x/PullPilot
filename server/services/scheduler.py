import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from sqlalchemy.exc import SQLAlchemyError

from server.config import LOG_LOCALE, logger
from server.database import SessionLocal
from server.locale.log_messages import t
from server.models.db import ProjectSettings, ScheduledTask
from server.services import update_state
from server.services.docker import run_command
from server.services.locks import ProjectBusyError, project_update_slot
from server.services.projects import compose_stack_allowed, update_single_project_logic
from server.services.update_logs import persist_update_log

global_update_status = {
    "is_running": False,
    "total": 0,
    "current": 0,
    "current_project": "",
    "processed": [],
}

scheduler = BackgroundScheduler()

global_update_lock = Lock()
# Guards the status dict above, which the job thread mutates while HTTP readers snapshot
# it. Nesting this with update_state's lock is how deadlocks start; keep them apart.
_status_lock = Lock()
# Serialises add/remove of jobs. Create and delete both refresh; two overlapping calls
# used to drop every job, then each re-add a different snapshot.
_refresh_lock = Lock()


def snapshot_global_update_status() -> dict[str, object]:
    """Defensive copy for HTTP readers: never share the live `processed` list.

    Under the lock as well as copied: the job thread mutates these fields between our
    reads, which is how a snapshot could report `current` past `total`.

    `projects` rides along so the SPA learns about both kinds of update from the one
    endpoint it already polls every second, rather than needing a second poll loop for the
    per-project deploys that now run in the background.
    """
    with _status_lock:
        s = global_update_status
        processed = s.get("processed")
        if isinstance(processed, list):
            processed_copy: list[object] = list(processed)
        else:
            processed_copy = []
        snapshot = {
            "is_running": s["is_running"],
            "total": s["total"],
            "current": s["current"],
            "current_project": s["current_project"],
            "processed": processed_copy,
        }
    # Outside `_status_lock`: update_state has its own, and nesting two locks in a fixed
    # order here for no reason is how deadlocks start.
    snapshot["projects"] = update_state.snapshot()
    return snapshot


def trigger_is_past(trigger: CronTrigger | DateTrigger) -> bool:
    """True for a one-shot trigger whose moment has already gone.

    APScheduler normalises `run_date` to an aware datetime, so comparing against UTC is
    safe whatever timezone the expression carried.
    """
    run_date = getattr(trigger, "run_date", None)
    return run_date is not None and run_date < datetime.now(UTC)


def build_trigger(
    task_type: str, expression: str, *, locale: str = "es", reject_past: bool = False
) -> CronTrigger | DateTrigger:
    """Build an APScheduler trigger. ValueError if the expression is not valid.

    Translated because the router hands these straight to the user as a 422 `detail`:
    they were the only messages in the schedules flow that skipped i18n.

    `reject_past` is for the create endpoint only. APScheduler's default misfire grace is
    one second, so a date already gone is dropped as a misfire: job_wrapper never runs,
    retire_one_shot_task never marks the row inactive, and the UI lists it forever as
    pending while every refresh re-registers it. Loading existing rows must not use it —
    those get pruned instead.
    """
    expr = (expression or "").strip()
    if task_type == "cron":
        if not expr:
            raise ValueError(t("schedule.cron_empty", locale))
        parts = expr.split()
        if len(parts) < 5:
            raise ValueError(t("schedule.cron_fields", locale))
        try:
            return CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )
        except Exception as exc:
            raise ValueError(t("schedule.cron_invalid", locale, exc=exc)) from exc
    if task_type == "date":
        if not expr:
            raise ValueError(t("schedule.date_empty", locale))
        try:
            trigger = DateTrigger(run_date=expr)
        except Exception as exc:
            raise ValueError(t("schedule.date_invalid", locale, exc=exc)) from exc
        if reject_past and trigger_is_past(trigger):
            raise ValueError(t("schedule.date_in_past", locale))
        return trigger
    raise ValueError(t("schedule.unsupported_type", locale, task_type=task_type))


def global_update_job(locale: str | None = None, *, already_locked: bool = False) -> None:
    loc = locale if locale is not None else LOG_LOCALE

    # `already_locked` is the HTTP path: the endpoint takes the lock so a second POST
    # can 409 before the background task even starts. The scheduler still acquires here.
    if not already_locked and not global_update_lock.acquire(blocking=False):
        logger.warning("Actualizacion global ya en curso. Omitiendo tarea.")
        return

    # Inside the try, so the finally always turns it back off. Set before it, a failure
    # opening the session left the flag and the lock taken and the progress bar spinning
    # for the rest of the process's life.
    db = None
    try:
        with _status_lock:
            global_update_status["is_running"] = True
            global_update_status["processed"] = []
        db = SessionLocal()
        logger.info("Iniciando tarea programada: Actualización Global Segura")

        rows = db.query(ProjectSettings).filter(ProjectSettings.excluded.is_(False)).all()
        projects = [p for p in rows if compose_stack_allowed(Path(p.path))]
        with _status_lock:
            global_update_status["total"] = len(projects)
            global_update_status["current"] = 0

        global_logs: dict[str, list[str] | str] = {}
        success_count = 0
        error_count = 0

        for index, project in enumerate(projects):
            with _status_lock:
                global_update_status["current"] = index + 1
                global_update_status["current_project"] = project.name

            if index > 0:
                time.sleep(2)

            try:
                # Same slot the API takes: a manual update in flight is not interrupted
                # by the global job.
                with project_update_slot(project.name):
                    success, logs = update_single_project_logic(
                        project.name, db, locale=loc
                    )
            except ProjectBusyError:
                success = False
                logs = [t("scheduler.project_busy", loc, name=project.name)]
                logger.warning(
                    "Omitiendo %s: ya hay una actualizacion en curso.", project.name
                )
            except Exception as exc:
                success = False
                logs = [t("scheduler.internal_loop_error", loc, exc=exc)]

            global_logs[project.name] = logs
            with _status_lock:
                global_update_status["processed"].append(
                    {
                        "name": project.name,
                        "status": t("log.status_ok", loc)
                        if success
                        else t("log.status_error", loc),
                    }
                )

            if success:
                success_count += 1
            else:
                error_count += 1

        if error_count == 0:
            with _status_lock:
                global_update_status["current_project"] = t(
                    "scheduler.status_pruning", loc
                )
            try:
                logger.info("Iniciando espera de seguridad de 5s antes del prune...")
                time.sleep(5)
                prune_out = run_command("docker image prune -f", locale=loc)
                message = t("scheduler.safe_cleanup_done", loc)
                if prune_out:
                    message += f"\n{t('scheduler.docker_output', loc)}\n{prune_out}"
                global_logs["safe_cleanup"] = message
            except Exception as exc:
                global_logs["safe_cleanup"] = t(
                    "scheduler.safe_cleanup_failed", loc, exc=exc
                )
        else:
            warning_msg = t("scheduler.cleanup_skipped", loc, errors=error_count)
            logger.warning(warning_msg)
            global_logs["safe_cleanup"] = warning_msg

        summary = t(
            "scheduler.global_summary", loc, ok=success_count, errors=error_count
        )
        status = "SUCCESS" if error_count == 0 else "ERROR"

        persist_update_log(
            db,
            status=status,
            summary=summary,
            details=global_logs,
        )
    except Exception:
        # Via POST /api/update-all this runs as a Starlette BackgroundTask, i.e. after the
        # 200 has already gone out. Without this the traceback surfaced only as "Exception
        # in ASGI application" and the user was told the update had started.
        logger.exception("La actualización global terminó con una excepción.")
    finally:
        if db is not None:
            db.close()
        with _status_lock:
            # All of them, not just is_running: total and current used to keep the
            # previous run's values, so the progress widget read "5 / 5" forever.
            global_update_status["is_running"] = False
            global_update_status["current_project"] = ""
            global_update_status["total"] = 0
            global_update_status["current"] = 0
        global_update_lock.release()


def retire_one_shot_task(task_id: int) -> None:
    """Mark a fired `date` task inactive.

    APScheduler drops the job once its date has passed, but the row stayed active: the UI
    listed it forever as if it were still going to run, and every refresh re-registered it
    with a date in the past just to log a misfire.
    """
    db = SessionLocal()
    try:
        task = db.get(ScheduledTask, task_id)
        if task is None or not task.active:
            return
        task.active = False
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("No se pudo desactivar la tarea de un solo uso %s.", task_id)
    finally:
        db.close()


def job_wrapper(target: str, task_id: int | None = None, task_type: str = "cron") -> None:
    try:
        _run_job(target, task_id=task_id)
    finally:
        # In a finally: a task that fired has fired, whatever the outcome. Leaving it
        # active on failure would make it misfire on every restart from then on.
        if task_type == "date" and task_id is not None:
            retire_one_shot_task(task_id)


def _run_job(target: str, task_id: int | None = None) -> None:
    if target == "GLOBAL":
        logger.info("Ejecutando tarea programada: GLOBAL")
        global_update_job()
        return

    sloc = LOG_LOCALE
    # Set inside the try and retired in `finally` after `db.close()`: a `return` in the
    # try never reaches code below this block, and retire_one_shot_task opens its own
    # session (nesting that on the testing StaticPool is the same connection).
    retire_id: int | None = None
    db = SessionLocal()
    try:
        logger.info("Ejecutando tarea programada: %s", target)
        project = db.query(ProjectSettings).filter(ProjectSettings.name == target).first()
        if not project or not compose_stack_allowed(Path(project.path)):
            logger.warning(
                "Omitiendo tarea programada %s: no existe en BD o la ruta no es un stack compose valido.",
                target,
            )
            # Same shape as a one-shot that has fired: the UI listed it as pending forever.
            retire_id = task_id
            return

        # `excluded` means "never update this automatically", not "skip it in the global
        # run": global_update_job already filters on it and the dashboard disables the
        # manual button for it, so a per-project schedule was the one path that still
        # updated a stack the user had explicitly fenced off. Logged rather than written
        # to the history, like the ProjectBusyError below: a schedule that can never run
        # is a property of the schedule, and the UI flags it in the schedules table.
        if project.excluded:
            logger.warning(
                "Omitiendo tarea programada %s: el proyecto está marcado como excluido.",
                target,
            )
            return
        try:
            with project_update_slot(target):
                success, logs = update_single_project_logic(target, db, locale=sloc)
        except ProjectBusyError:
            logger.warning(
                "Omitiendo tarea programada %s: ya hay una actualizacion en curso.", target
            )
            return

        summary = (
            t("scheduler.scheduled_ok", sloc, target=target)
            if success
            else t("scheduler.scheduled_error", sloc, target=target)
        )
        try:
            persist_update_log(
                db,
                status="SUCCESS" if success else "ERROR",
                summary=summary,
                details={target: logs},
            )
        except SQLAlchemyError:
            # Same as the HTTP path: the stack has already been pulled and health-checked,
            # so failing to write the row must not rewrite a working deploy as ERROR.
            logger.error("No se pudo persistir el historial de %s.", target)
    except Exception as exc:
        logger.error("Error en tarea programada %s: %s", target, exc)
        try:
            persist_update_log(
                db,
                status="ERROR",
                summary=t("scheduler.scheduled_exception", sloc, target=target),
                details={target: [str(exc)]},
            )
        except Exception as log_exc:
            logger.error("No se pudo persistir log de error para %s: %s", target, log_exc)
    finally:
        db.close()
        if retire_id is not None:
            retire_one_shot_task(retire_id)


def refresh_scheduler_jobs() -> None:
    # Add missing jobs and drop retired ones. `remove_all_jobs()` plus re-add used to
    # reset every CronTrigger's next fire: APScheduler's misfire grace is one second, so
    # creating or deleting a schedule in the same minute as a daily job skipped that run
    # with nothing on the UI. Rows are immutable after create, so an existing id is left
    # alone.
    with _refresh_lock:
        db = SessionLocal()
        count = 0
        pruned = 0
        wanted: set[str] = set()
        try:
            existing = {job.id for job in scheduler.get_jobs()}
            tasks = db.query(ScheduledTask).filter(ScheduledTask.active.is_(True)).all()

            for task in tasks:
                try:
                    trigger = build_trigger(task.task_type, task.expression)
                except Exception as exc:
                    logger.error("Error cargando tarea %s: %s", task.id, exc)
                    continue

                # A one-shot whose moment passed while the container was down can never
                # fire, so registering it only produces a misfire on every refresh and
                # leaves the UI listing it as pending forever.
                if task.task_type == "date" and trigger_is_past(trigger):
                    task.active = False
                    pruned += 1
                    continue

                job_id = f"job_{task.id}"
                if job_id in existing:
                    wanted.add(job_id)
                    count += 1
                    continue
                try:
                    scheduler.add_job(
                        job_wrapper,
                        trigger,
                        args=[task.target, task.id, task.task_type],
                        id=job_id,
                    )
                    wanted.add(job_id)
                    count += 1
                except Exception as exc:
                    logger.error("Error cargando tarea %s: %s", task.id, exc)

            for job_id in existing - wanted:
                try:
                    scheduler.remove_job(job_id)
                except Exception:
                    logger.warning("No se pudo retirar el job %s.", job_id)

            if pruned:
                try:
                    db.commit()
                except SQLAlchemyError:
                    db.rollback()
                    logger.warning("No se pudieron retirar %s tareas vencidas.", pruned)
        finally:
            db.close()

    logger.info(
        "Scheduler refrescado: %s tareas activas, %s vencidas retiradas.", count, pruned
    )


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
    refresh_scheduler_jobs()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
