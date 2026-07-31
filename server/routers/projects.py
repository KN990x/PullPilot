from typing import Callable, List, Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from server.config import logger
from server.locale.http import get_request_locale
from server.locale.log_messages import t
from server.database import session_scope
from server.models.db import ProjectSettings
from server.models.schemas import Project
from server.services.locks import ProjectBusyError, project_update_slot
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


@router.post("/projects/{name}/update")
async def update_project(name: str, locale: str = Depends(get_request_locale)):
    def work(db: Session):
        # El turno se toma antes que nada: dos peticiones a la vez sobre el mismo stack
        # (doble clic, dos pestañas, o una actualización global en curso) se solapaban
        # bajando y levantando los mismos contenedores.
        try:
            with project_update_slot(name):
                return _run_update(name, db, locale)
        except ProjectBusyError:
            raise HTTPException(
                status_code=409,
                detail=t("http.update_in_progress", locale),
            ) from None

    return await _run_in_session(work)


def _run_update(name: str, db: Session, locale: str) -> dict:
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
        raise HTTPException(
            status_code=500, detail=t("http.history_save_failed", locale)
        ) from None

    if not success:
        logger.error("Actualización fallida para %s:\n%s", name, "\n".join(logs))
        raise HTTPException(status_code=500, detail=t("http.update_failed", locale))

    return {"success": success, "logs": logs}


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
