from typing import Callable, List, Literal, TypeVar

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from server.config import logger
from server.database import session_scope
from server.locale.http import get_request_locale
from server.locale.log_messages import t
from server.models.db import ProjectSettings
from server.models.schemas import Project
from server.services import update_state
from server.services.locks import release_project_slot, try_acquire_project_slot
from server.services.projects import scan_projects_logic, update_single_project_logic
from server.services.update_logs import persist_update_log

router = APIRouter(prefix="/api", tags=["projects"])

_ToggleField = Literal["excluded", "full_stop"]
T = TypeVar("T")


async def _run_in_session(work: Callable[[Session], T]) -> T:
    def task() -> T:
        with session_scope() as db:
            return work(db)

    return await run_in_threadpool(task)


def _toggle_project_field(
    name: str, field: _ToggleField, db: Session, *, locale: str
) -> dict:
    project = db.query(ProjectSettings).filter(ProjectSettings.name == name).first()
    if not project:
        raise HTTPException(
            status_code=404, detail=t("http.project_not_found", locale)
        )
    setattr(project, field, not getattr(project, field))
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=t("http.project_save_failed", locale)
        ) from None
    return {"status": "ok"}


@router.get("/projects", response_model=List[Project])
async def get_projects():
    return await _run_in_session(scan_projects_logic)


def _run_update_in_background(name: str, locale: str) -> None:
    """Deploy the stack and record how it went. Owns the slot the endpoint took.

    Its own session: the request's is long closed by the time this runs.
    """
    success = False
    try:
        with session_scope() as db:
            success = _run_update(name, db, locale)
    except Exception:
        # Nothing is left to raise to — the 202 went out long ago — so an unhandled error
        # here would surface only as "Exception in ASGI application" while the SPA polled
        # a `running` entry that never resolved. Same reasoning as global_update_job.
        logger.exception("La actualización de %s terminó con una excepción.", name)
    finally:
        update_state.mark_finished(name, success=success)
        release_project_slot(name)


@router.post("/projects/{name}/update", status_code=202)
async def update_project(
    name: str,
    background_tasks: BackgroundTasks,
    locale: str = Depends(get_request_locale),
):
    """Start the deploy and answer straight away; the SPA follows it on /update-status.

    It used to run inline, holding the connection open for the whole thing.
    """

    def work(db: Session) -> None:
        # Existence first: taking the slot for a name that is not a project answered 500,
        # wrote an ERROR row into the history and created a lock entry that was never
        # collected. The sibling toggle endpoints already answered 404 here.
        exists = (
            db.query(ProjectSettings.id).filter(ProjectSettings.name == name).first()
        )
        if exists is None:
            raise HTTPException(
                status_code=404, detail=t("http.project_not_found", locale)
            )

        # Then the slot: two requests on the same stack used to overlap, taking the same
        # containers down and up at once. Taken here and released by the background task,
        # so the answer cannot be 202 for an update that never gets to start.
        if not try_acquire_project_slot(name):
            raise HTTPException(
                status_code=409,
                detail=t("http.update_in_progress", locale),
            )
        update_state.mark_running(name)

    await _run_in_session(work)
    background_tasks.add_task(_run_update_in_background, name, locale)
    return {"status": "accepted", "name": name}


def _run_update(name: str, db: Session, locale: str) -> bool:
    """Deploy and write the history row. Returns whether the deploy worked.

    A bool rather than an HTTP answer: this runs after the 202, so there is no response
    left to put a status code on. The logs live in the history row, which is where the UI
    reads them from anyway.
    """
    success, logs = update_single_project_logic(name, db, locale=locale)

    status_word = t("log.status_ok", locale) if success else t("log.status_error", locale)
    summary = t("summary.project", locale, name=name, status=status_word)
    try:
        persist_update_log(
            db,
            status="SUCCESS" if success else "ERROR",
            summary=summary,
            details={name: logs},
        )
    except SQLAlchemyError:
        # Not fatal: the stack has already been pulled, recreated and health-checked, so
        # failing to write the row does not make the deploy a failure.
        logger.error("No se pudo guardar el historial de %s.", name)

    if not success:
        logger.error("Actualización fallida para %s:\n%s", name, "\n".join(logs))

    return success


@router.post("/projects/{name}/toggle_exclude")
async def toggle_exclude(name: str, locale: str = Depends(get_request_locale)):
    def work(db: Session) -> dict:
        return _toggle_project_field(name, "excluded", db, locale=locale)

    return await _run_in_session(work)


@router.post("/projects/{name}/toggle_fullstop")
async def toggle_fullstop(name: str, locale: str = Depends(get_request_locale)):
    def work(db: Session) -> dict:
        return _toggle_project_field(name, "full_stop", db, locale=locale)

    return await _run_in_session(work)
