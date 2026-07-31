import json

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from server.config import HISTORY_RETENTION, logger
from server.models.db import UpdateLog


def persist_update_log(
    db: Session,
    *,
    status: str,
    summary: str,
    details: dict,
) -> None:
    """Persist one history row. Rolls back the session on failure and re-raises."""
    row = UpdateLog(status=status, summary=summary, details=json.dumps(details))
    db.add(row)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    _trim_history(db)


def _trim_history(db: Session) -> None:
    """Keep the newest HISTORY_RETENTION rows.

    The table only ever grew, and each row carries the full log of an update. Never fatal:
    the entry the caller asked for is already committed, so failing to prune is a
    housekeeping problem, not theirs.
    """
    try:
        cutoff = db.scalar(
            select(UpdateLog.id)
            .order_by(UpdateLog.id.desc())
            .offset(HISTORY_RETENTION)
            .limit(1)
        )
        if cutoff is None:
            return
        db.query(UpdateLog).filter(UpdateLog.id <= cutoff).delete(
            synchronize_session=False
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("No se pudo podar el historial de actualizaciones.")
