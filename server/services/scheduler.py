import time
from pathlib import Path
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from server.config import LOG_LOCALE, logger
from server.database import SessionLocal
from server.locale.log_messages import t
from server.models.db import ProjectSettings, ScheduledTask
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


def snapshot_global_update_status() -> dict[str, object]:
    """Defensive copy for HTTP readers: never share the live `processed` list."""
    s = global_update_status
    processed = s.get("processed")
    if isinstance(processed, list):
        processed_copy: list[object] = list(processed)
    else:
        processed_copy = []
    return {
        "is_running": s["is_running"],
        "total": s["total"],
        "current": s["current"],
        "current_project": s["current_project"],
        "processed": processed_copy,
    }


global_update_lock = Lock()


def build_trigger(task_type: str, expression: str) -> CronTrigger | DateTrigger:
    """Build an APScheduler trigger. ValueError if the expression is not valid."""
    expr = (expression or "").strip()
    if task_type == "cron":
        if not expr:
            raise ValueError("La expresion cron esta vacia")
        parts = expr.split()
        if len(parts) < 5:
            raise ValueError("La expresion cron debe tener 5 campos")
        try:
            return CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )
        except Exception as exc:
            raise ValueError(f"Cron invalido: {exc}") from exc
    if task_type == "date":
        if not expr:
            raise ValueError("La fecha programada esta vacia")
        try:
            return DateTrigger(run_date=expr)
        except Exception as exc:
            raise ValueError(f"Fecha invalida: {exc}") from exc
    raise ValueError(f"Tipo de tarea no soportado: {task_type}")


def global_update_job(locale: str | None = None) -> None:
    loc = locale if locale is not None else LOG_LOCALE

    if not global_update_lock.acquire(blocking=False):
        logger.warning("Actualizacion global ya en curso. Omitiendo tarea.")
        return

    global_update_status["is_running"] = True
    global_update_status["processed"] = []
    db = SessionLocal()
    try:
        logger.info("Iniciando tarea programada: Actualizacion Global Segura")

        rows = db.query(ProjectSettings).filter(ProjectSettings.excluded.is_(False)).all()
        projects = [p for p in rows if compose_stack_allowed(Path(p.path))]
        global_update_status["total"] = len(projects)
        global_update_status["current"] = 0

        global_logs: dict[str, list[str] | str] = {}
        success_count = 0
        error_count = 0

        for index, project in enumerate(projects):
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
            global_update_status["current_project"] = t("scheduler.status_pruning", loc)
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
    finally:
        db.close()
        global_update_status["is_running"] = False
        global_update_status["current_project"] = ""
        global_update_lock.release()


def job_wrapper(target: str) -> None:
    if target == "GLOBAL":
        logger.info("Ejecutando tarea programada: GLOBAL")
        global_update_job()
        return

    sloc = LOG_LOCALE
    db = SessionLocal()
    try:
        logger.info("Ejecutando tarea programada: %s", target)
        project = db.query(ProjectSettings).filter(ProjectSettings.name == target).first()
        if not project or not compose_stack_allowed(Path(project.path)):
            logger.warning(
                "Omitiendo tarea programada %s: no existe en BD o la ruta no es un stack compose valido.",
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
        persist_update_log(
            db,
            status="SUCCESS" if success else "ERROR",
            summary=summary,
            details={target: logs},
        )
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


def refresh_scheduler_jobs() -> None:
    scheduler.remove_all_jobs()

    db = SessionLocal()
    count = 0
    try:
        tasks = db.query(ScheduledTask).filter(ScheduledTask.active.is_(True)).all()

        for task in tasks:
            try:
                job_id = f"job_{task.id}"
                trigger = build_trigger(task.task_type, task.expression)
                scheduler.add_job(
                    job_wrapper,
                    trigger,
                    args=[task.target],
                    id=job_id,
                    replace_existing=True,
                )
                count += 1
            except Exception as exc:
                logger.error("Error cargando tarea %s: %s", task.id, exc)
    finally:
        db.close()

    logger.info("Scheduler refrescado: %s tareas activas.", count)


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
    refresh_scheduler_jobs()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
