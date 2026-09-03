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
from server.models.db import ProjectSettings, ScheduledTask, UpdateLog
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


def test_a_scheduled_task_skips_an_excluded_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """`excluded` means "never update this automatically", on every path.

    The global job filtered on it and the dashboard disabled the manual button, but a
    per-project schedule went straight through and updated the stack anyway.
    """
    import server.services.scheduler as scheduler_module

    stack = tmp_path / "plex"
    stack.mkdir()
    (stack / "docker-compose.yml").write_text("services: {}\n")

    with session_scope() as db:
        db.add(ProjectSettings(name="plex", path=str(stack), excluded=True))
        db.commit()

    monkeypatch.setattr(scheduler_module, "compose_stack_allowed", lambda _path: True)

    called: list[str] = []

    def _never(name, db, *, locale="es"):
        called.append(name)
        return True, []

    monkeypatch.setattr(scheduler_module, "update_single_project_logic", _never)

    scheduler_module._run_job("plex")

    assert called == [], "an excluded project was updated by its schedule"
    # And nothing is written to the history: a schedule that can never run is a property
    # of the schedule, which the UI flags in the schedules table.
    with session_scope() as db:
        assert db.query(UpdateLog).count() == 0


def test_a_scheduled_task_still_runs_for_a_project_that_is_not_excluded(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The guard above must not swallow the ordinary case."""
    import server.services.scheduler as scheduler_module

    stack = tmp_path / "pihole"
    stack.mkdir()
    (stack / "docker-compose.yml").write_text("services: {}\n")

    with session_scope() as db:
        db.add(ProjectSettings(name="pihole", path=str(stack), excluded=False))
        db.commit()

    monkeypatch.setattr(scheduler_module, "compose_stack_allowed", lambda _path: True)

    called: list[str] = []

    def _ok(name, db, *, locale="es"):
        called.append(name)
        return True, ["done"]

    monkeypatch.setattr(scheduler_module, "update_single_project_logic", _ok)

    scheduler_module._run_job("pihole")

    assert called == ["pihole"]
    with session_scope() as db:
        assert db.query(UpdateLog).count() == 1


def test_refresh_does_not_reset_next_run_time_of_an_existing_job(
    client: TestClient,
) -> None:
    """Creating another schedule used to drop every job and re-add them.

    APScheduler's misfire grace is one second, so a refresh in the same minute as a daily
    job skipped that run with nothing on the UI.
    """
    from server.services.scheduler import refresh_scheduler_jobs, scheduler

    first = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "cron",
            "frequency": "daily",
            "hour": 4,
            "minute": 0,
        },
    )
    assert first.status_code == 200, first.text
    job_id = f"job_{first.json()['id']}"
    before = scheduler.get_job(job_id).next_run_time
    assert before is not None

    second = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "cron",
            "frequency": "daily",
            "hour": 5,
            "minute": 0,
        },
    )
    assert second.status_code == 200, second.text
    assert scheduler.get_job(job_id).next_run_time == before

    refresh_scheduler_jobs()
    assert scheduler.get_job(job_id).next_run_time == before


def test_refresh_removes_only_the_deleted_job(client: TestClient) -> None:
    from server.services.scheduler import scheduler

    first = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "cron",
            "frequency": "daily",
            "hour": 4,
            "minute": 0,
        },
    )
    second = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "cron",
            "frequency": "daily",
            "hour": 5,
            "minute": 0,
        },
    )
    assert first.status_code == 200 and second.status_code == 200
    id_a = first.json()["id"]
    id_b = second.json()["id"]
    next_b = scheduler.get_job(f"job_{id_b}").next_run_time

    assert client.delete(f"/api/schedules/{id_a}").status_code == 200

    assert scheduler.get_job(f"job_{id_a}") is None
    leftover = scheduler.get_job(f"job_{id_b}")
    assert leftover is not None
    assert leftover.next_run_time == next_b


def test_a_persist_failure_does_not_write_an_error_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """SQLite failing after a working deploy used to record that deploy as ERROR."""
    import server.services.scheduler as scheduler_module
    from sqlalchemy.exc import SQLAlchemyError

    stack = tmp_path / "pihole"
    stack.mkdir()
    (stack / "docker-compose.yml").write_text("services: {}\n")

    with session_scope() as db:
        db.add(ProjectSettings(name="pihole", path=str(stack), excluded=False))
        db.commit()

    monkeypatch.setattr(scheduler_module, "compose_stack_allowed", lambda _path: True)
    monkeypatch.setattr(
        scheduler_module,
        "update_single_project_logic",
        lambda name, db, *, locale="es": (True, ["done"]),
    )

    def _boom(*_args, **_kwargs):
        raise SQLAlchemyError("disk full")

    monkeypatch.setattr(scheduler_module, "persist_update_log", _boom)

    scheduler_module._run_job("pihole")

    with session_scope() as db:
        assert db.query(UpdateLog).filter(UpdateLog.status == "ERROR").count() == 0
        assert db.query(UpdateLog).count() == 0


def test_a_job_for_a_missing_project_retires_its_schedule() -> None:
    import server.services.scheduler as scheduler_module

    with session_scope() as db:
        row = ScheduledTask(
            target="ghost",
            task_type="cron",
            expression="0 4 * * *",
            active=True,
        )
        db.add(row)
        db.commit()
        task_id = row.id

    scheduler_module._run_job("ghost", task_id=task_id)

    with session_scope() as db:
        leftover = db.get(ScheduledTask, task_id)
        assert leftover is not None
        assert leftover.active is False
