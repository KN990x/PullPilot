import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from server.config import DB_PATH

# How long a writer waits for another one to finish instead of raising "database is
# locked" straight away. Three paths write concurrently — the FastAPI threadpool, the
# APScheduler thread and the background global update — and the project scan commits on
# every GET /api/projects, which the dashboard polls.
SQLITE_BUSY_TIMEOUT_MS = 5000


class Base(DeclarativeBase):
    pass


_TESTING = os.getenv("PULLPILOT_TESTING") == "1"

if _TESTING:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False, "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000},
    )


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    try:
        # WAL lets the dashboard's reads run while an update writes; without it any
        # write blocked every reader. Skipped in tests, where the database is :memory:
        # and WAL is not available.
        if not _TESTING:
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
