from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from server.config import HISTORY_RETENTION
from server.database import get_db
from server.locale.http import get_request_locale
from server.locale.log_messages import t
from server.models.db import UpdateLog
from server.models.schemas import UpdateLogOut
from server.services.scheduler import (
    global_update_job,
    global_update_lock,
    snapshot_global_update_status,
)

router = APIRouter(prefix="/api", tags=["status"])


@router.post("/update-all")
def trigger_update_all(
    background_tasks: BackgroundTasks,
    locale: str = Depends(get_request_locale),
):
    # Taken here, released by the job: checking `locked()` and acquiring in the task is
    # the same check-then-act the per-project update already closed. Two POSTs could both
    # answer 200 and the second job would exit on the first line.
    if not global_update_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409, detail=t("http.update_all_in_progress", locale)
        )
    background_tasks.add_task(global_update_job, locale, already_locked=True)
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
    the limit was hardcoded and there was no way to page past it.

    `id` breaks ties: the global job writes one row and every per-project update another,
    so two rows can share a timestamp. Ordering on it alone leaves their relative order up
    to SQLite, and a row that moves across a page boundary is one the caller sees twice or
    never. It also matches _trim_history, which prunes by id.
    """
    return (
        db.query(UpdateLog)
        .order_by(UpdateLog.timestamp.desc(), UpdateLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
