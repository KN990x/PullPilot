"""One-shot tasks, timezones and history retention.

A `date` task used to stay `active` after firing: the UI listed it forever as if it were
still coming, and every scheduler refresh re-registered it with a date in the past just to
log a misfire. `active` existed on the model with nothing that ever set it to False.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from server.config import HISTORY_RETENTION
from server.database import SessionLocal, session_scope
from server.models.db import ScheduledTask, UpdateLog
from server.routers.schedules import _normalize_date_expression
from server.services.scheduler import refresh_scheduler_jobs, retire_one_shot_task
from server.services.update_logs import persist_update_log


def _create_once(client: TestClient, date_iso: str) -> dict:
    response = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "date",
            "frequency": "daily",
            "date_iso": date_iso,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_a_browser_offset_survives_normalisation() -> None:
    """`datetime-local` has no zone, so the server used to read it in the container's."""
    assert (
        _normalize_date_expression("2027-06-01T08:15:00+02:00")
        == "2027-06-01 08:15:00+02:00"
    )


def test_seconds_are_added_but_the_offset_is_not_mangled() -> None:
    assert _normalize_date_expression("2027-06-01T08:15+02:00") == "2027-06-01 08:15:00+02:00"
    assert _normalize_date_expression("2027-06-01T08:15") == "2027-06-01 08:15:00"
    assert _normalize_date_expression("2027-06-01T08:15Z") == "2027-06-01 08:15:00Z"


def test_an_offset_schedule_is_accepted_and_stored(client: TestClient) -> None:
    created = _create_once(client, "2027-06-01T08:15:00+02:00")

    assert created["expression"] == "2027-06-01 08:15:00+02:00"


def test_a_fired_one_shot_disappears_from_the_list(client: TestClient) -> None:
    created = _create_once(client, "2027-06-01T08:15")
    assert len(client.get("/api/schedules").json()) == 1

    retire_one_shot_task(created["id"])

    assert client.get("/api/schedules").json() == []


def test_retiring_keeps_the_row_but_deactivates_it(client: TestClient) -> None:
    created = _create_once(client, "2027-06-01T08:15")

    retire_one_shot_task(created["id"])

    db = SessionLocal()
    try:
        row = db.get(ScheduledTask, created["id"])
        assert row is not None, "the row is the record that it ran, not rubbish"
        assert row.active is False
    finally:
        db.close()


def test_retiring_an_unknown_task_is_harmless() -> None:
    """A row deleted between firing and retiring must not raise, nor create anything."""
    retire_one_shot_task(999999)

    db = SessionLocal()
    try:
        assert db.get(ScheduledTask, 999999) is None
        assert db.query(ScheduledTask).count() == 0
    finally:
        db.close()


def test_a_cron_schedule_is_not_retired(client: TestClient) -> None:
    """Only `date` tasks are one-shot; a daily job must survive its own run."""
    response = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "cron",
            "frequency": "daily",
            "hour": 4,
            "minute": 0,
        },
    )
    assert response.status_code == 200

    from server.services.scheduler import job_wrapper

    job_wrapper("GLOBAL", response.json()["id"], "cron")

    assert len(client.get("/api/schedules").json()) == 1


@pytest.mark.parametrize("extra", [5, 30])
def test_history_is_trimmed_to_the_retention_ceiling(extra: int) -> None:
    db = SessionLocal()
    try:
        for n in range(HISTORY_RETENTION + extra):
            persist_update_log(db, status="SUCCESS", summary=f"run {n}", details={})

        assert db.query(UpdateLog).count() == HISTORY_RETENTION
        # The ones kept are the newest.
        newest = db.query(UpdateLog).order_by(UpdateLog.id.desc()).first()
        assert newest is not None
        assert newest.summary == f"run {HISTORY_RETENTION + extra - 1}"
    finally:
        db.close()


def test_a_date_in_the_past_is_rejected(client: TestClient) -> None:
    """APScheduler drops it as a misfire, so job_wrapper never retires the row: the UI
    listed it as pending forever and every refresh re-registered it."""
    response = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "date",
            "frequency": "daily",
            "date_iso": "2020-01-01T03:00",
        },
    )

    assert response.status_code == 422
    assert client.get("/api/schedules").json() == []


def test_a_date_in_the_future_is_accepted(client: TestClient) -> None:
    future = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3650)
    response = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "date",
            "frequency": "daily",
            "date_iso": future.strftime("%Y-%m-%dT%H:%M"),
        },
    )

    assert response.status_code == 200, response.text


def test_a_weekly_schedule_without_a_day_is_rejected(client: TestClient) -> None:
    """`week_day` defaults to `*`, which in cron means every day: a weekly task created
    through the API without naming a day silently ran daily."""
    response = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "cron",
            "frequency": "weekly",
            "hour": 4,
            "minute": 0,
        },
    )

    assert response.status_code == 422


def test_expired_one_shot_rows_are_retired_on_refresh(client: TestClient) -> None:
    """A one-shot whose moment passed while the container was down can never fire."""
    with session_scope() as db:
        db.add(
            ScheduledTask(
                target="GLOBAL",
                task_type="date",
                expression="2020-01-01 03:00:00",
                active=True,
            )
        )
        db.commit()

    assert len(client.get("/api/schedules").json()) == 1

    refresh_scheduler_jobs()

    assert client.get("/api/schedules").json() == []
