from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from server.config import HISTORY_RETENTION
from server.database import get_db
from server.locale.http import get_request_locale
from server.locale.log_messages import t
from server.models.db import UpdateLog
from server.models.schemas import UpdateLogOut
from server.services.scheduler import global_update_job, snapshot_global_update_status

router = APIRouter(prefix="/api", tags=["status"])


@router.post("/update-all")
def trigger_update_all(
    background_tasks: BackgroundTasks,
    locale: str = Depends(get_request_locale),
):
    background_tasks.add_task(global_update_job, locale)
    return {"message": t("api.update_all_started", locale)}


@router.get("/update-status")
def get_update_status():
    return snapshot_global_update_status()


HISTORY_PAGE_DEFAULT = 20


@router.get("/history", response_model=list[UpdateLogOut])
def get_history(
    db: Session = Depends(get_db),
    limit: int = Query(default=HISTORY_PAGE_DEFAULT, ge=1, le=HISTORY_RETENTION),
    offset: int = Query(default=0, ge=0),
):
    """Newest first. HISTORY_RETENTION rows are kept but only 20 were ever reachable:
    the limit was hardcoded and there was no way to page past it."""
    return (
        db.query(UpdateLog)
        .order_by(UpdateLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
