import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from server.database import get_db
from server.locale.http import get_request_locale
from server.locale.log_messages import t
from server.models.db import ProjectSettings, ScheduledTask
from server.models.schemas import ScheduledTaskOut, ScheduleInput
from server.services.scheduler import build_trigger, refresh_scheduler_jobs

router = APIRouter(prefix="/api", tags=["schedules"])


_OFFSET_RE = re.compile(r"(Z|[+-]\d{2}:\d{2})$")


def _normalize_date_expression(raw: str) -> str:
    """Turn what the browser sends into what APScheduler's parser accepts.

    It requires seconds, which `datetime-local` never produces. The trailing offset, when
    the frontend pins one, is what keeps a wall-clock the user picked in their own
    timezone from being read in the container's.
    """
    s = raw.strip().replace("T", " ", 1)
    offset = ""
    match = _OFFSET_RE.search(s)
    if match:
        offset = match.group(1)
        s = s[: match.start()].strip()
    if s.count(":") == 1:
        s = f"{s}:00"
    return f"{s}{offset}"


def _reject_unrunnable_target(target: str, db: Session, *, locale: str) -> None:
    """Refuse a schedule the scheduler would only ever skip.

    Both cases were accepted and then silently skipped at fire time, with one line in the
    container log: the UI listed the task as active forever. The SPA already greys these
    out in the target picker, but an older tab, a bookmark or curl reaches this anyway,
    and the check that matters is the one on this side.
    """
    if target == "GLOBAL":
        return
    project = (
        db.query(ProjectSettings).filter(ProjectSettings.name == target).first()
    )
    if project is None:
        raise HTTPException(
            status_code=404, detail=t("http.schedule_target_unknown", locale)
        )
    if project.excluded:
        raise HTTPException(
            status_code=409, detail=t("http.schedule_target_excluded", locale)
        )


@router.get("/schedules", response_model=list[ScheduledTaskOut])
def get_schedules(db: Session = Depends(get_db)):
    # Only active ones: a one-shot task that already fired is retired by the scheduler,
    # and listing it still would say it is about to run when it never will again.
    return db.query(ScheduledTask).filter(ScheduledTask.active.is_(True)).all()


@router.post("/schedules", response_model=ScheduledTaskOut)
def create_schedule(
    data: ScheduleInput,
    db: Session = Depends(get_db),
    locale: str = Depends(get_request_locale),
):
    expression = ""
    if data.task_type == "cron":
        if data.frequency == "daily":
            expression = f"{data.minute} {data.hour} * * *"
        elif data.frequency == "weekly":
            expression = f"{data.minute} {data.hour} * * {data.week_day}"
        elif data.frequency == "monthly":
            expression = f"{data.minute} {data.hour} {data.day_of_month} * *"
    elif data.task_type == "date":
        expression = _normalize_date_expression(data.date_iso or "")

    try:
        build_trigger(data.task_type, expression, locale=locale, reject_past=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _reject_unrunnable_target(data.target, db, locale=locale)

    # A schedule is (target, type, expression): the same three again is a second job on the
    # same stack at the same minute, which is two overlapping deploys the per-project lock
    # then has to turn into a 409. There is no unique constraint on the table, and the
    # form's submit guard only stops the double click, not two deliberate creations.
    duplicate = (
        db.query(ScheduledTask.id)
        .filter(
            ScheduledTask.target == data.target,
            ScheduledTask.task_type == data.task_type,
            ScheduledTask.expression == expression,
            ScheduledTask.active.is_(True),
        )
        .first()
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409, detail=t("http.schedule_duplicate", locale)
        )

    new_task = ScheduledTask(
        target=data.target,
        task_type=data.task_type,
        expression=expression,
        active=True,
    )
    db.add(new_task)
    try:
        db.commit()
        db.refresh(new_task)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=t("http.schedule_save_failed", locale)
        ) from None

    refresh_scheduler_jobs()
    return new_task


@router.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    locale: str = Depends(get_request_locale),
):
    task = db.query(ScheduledTask).filter(ScheduledTask.id == schedule_id).first()
    if not task:
        raise HTTPException(
            status_code=404, detail=t("http.schedule_not_found", locale)
        )
    db.delete(task)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=t("http.schedule_delete_failed", locale)
        ) from None
    refresh_scheduler_jobs()
    return {"status": "ok"}
