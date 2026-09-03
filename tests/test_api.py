from datetime import UTC, datetime

import pytest
import server.routers.projects as projects_router_module
import server.services.projects as projects_module
from fastapi.testclient import TestClient
from server.database import SessionLocal
from server.locale.log_messages import t
from server.models.db import ProjectSettings, UpdateLog
from server.services import locks
from server.services.update_logs import persist_update_log


def test_update_status(client: TestClient) -> None:
    response = client.get("/api/update-status")
    assert response.status_code == 200
    data = response.json()
    assert data["is_running"] is False
    assert "processed" in data


def test_update_status_processed_is_snapshot_not_alias(client: TestClient) -> None:
    data = client.get("/api/update-status").json()
    data["processed"].append({"name": "__fake__", "status": "OK"})
    data2 = client.get("/api/update-status").json()
    assert not any(p.get("name") == "__fake__" for p in data2.get("processed", []))


def test_history_empty(client: TestClient) -> None:
    response = client.get("/api/history")
    assert response.status_code == 200
    assert response.json() == []


def test_create_schedule_invalid_hour(client: TestClient) -> None:
    response = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "cron",
            "frequency": "daily",
            "hour": 99,
            "minute": 0,
        },
    )
    assert response.status_code == 422


def test_create_schedule_date_requires_iso(client: TestClient) -> None:
    response = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "date",
            "frequency": "daily",
        },
    )
    assert response.status_code == 422


def test_create_schedule_cron(client: TestClient) -> None:
    response = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "cron",
            "frequency": "daily",
            "hour": 4,
            "minute": 30,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["task_type"] == "cron"
    assert data["expression"] == "30 4 * * *"
    assert data["target"] == "GLOBAL"


def test_create_schedule_date(client: TestClient) -> None:
    response = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "date",
            "frequency": "daily",
            "date_iso": "2027-06-01T08:15",
        },
    )
    assert response.status_code == 200
    assert response.json()["expression"] == "2027-06-01 08:15:00"


def test_schedules_list_shape(client: TestClient) -> None:
    client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "cron",
            "frequency": "daily",
            "hour": 1,
            "minute": 0,
        },
    )
    response = client.get("/api/schedules")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) >= 1
    row = rows[0]
    required = {"id", "target", "task_type", "expression", "active"}
    assert required.issubset(set(row.keys()))


def test_get_projects(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    root = tmp_path / "projects_root"
    root.mkdir()
    monkeypatch.setattr(projects_module, "PROJECTS_ROOT", root)

    response = client.get("/api/projects")
    assert response.status_code == 200
    assert response.json() == []


def test_delete_schedule_not_found(client: TestClient) -> None:
    response = client.delete("/api/schedules/99999")
    assert response.status_code == 404


def test_trigger_update_all(client: TestClient) -> None:
    response = client.post("/api/update-all")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


def test_trigger_update_all_message_english(client: TestClient) -> None:
    response = client.post(
        "/api/update-all",
        headers={"Accept-Language": "en"},
    )
    assert response.status_code == 200
    assert "background" in response.json()["message"].lower()


def test_update_passes_locale_to_logic(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, make_project
) -> None:
    make_project("any")
    seen: dict[str, str] = {}

    def _fake(name, db, *, locale="es"):
        seen["locale"] = locale
        return True, []

    # The router does `from server.services.projects import ...`, so the name is bound
    # in its own module: patch it there, not in the module it came from.
    monkeypatch.setattr(
        projects_router_module, "update_single_project_logic", _fake
    )

    r = client.post(
        "/api/projects/any/update",
        headers={"Accept-Language": "en"},
    )
    # 202: the deploy runs as a BackgroundTask, which TestClient drives to completion
    # before handing the response back.
    assert r.status_code == 202
    assert seen.get("locale") == "en"


def test_update_of_an_unknown_project_is_404(client: TestClient) -> None:
    """It used to answer 500, write an ERROR row and leak a lock entry per name tried."""
    response = client.post("/api/projects/no-existe/update")

    assert response.status_code == 404
    assert client.get("/api/history").json() == []


def test_a_failed_update_is_reported_through_the_status_endpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, make_project
) -> None:
    """The deploy no longer decides the HTTP status: it has already been sent.

    202 says the work started. Whether it worked comes back on /update-status, which the
    SPA polls, and in the history row that carries the logs.
    """
    make_project("x")
    monkeypatch.setattr(
        projects_router_module,
        "update_single_project_logic",
        lambda _n, _db, **kw: (False, ["boom"]),
    )

    assert client.post("/api/projects/x/update").status_code == 202

    assert client.get("/api/update-status").json()["projects"]["x"] == "error"
    history = client.get("/api/history").json()
    assert len(history) == 1
    assert history[0]["status"] == "ERROR"


def test_a_successful_update_reports_success_and_frees_the_slot(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, make_project
) -> None:
    make_project("y")
    monkeypatch.setattr(
        projects_router_module,
        "update_single_project_logic",
        lambda _n, _db, **kw: (True, ["ok"]),
    )

    assert client.post("/api/projects/y/update").status_code == 202
    assert client.get("/api/update-status").json()["projects"]["y"] == "success"
    # The slot is the background task's to release: leaking it would 409 every later run.
    assert locks.is_busy("y") is False
    assert client.post("/api/projects/y/update").status_code == 202


def test_a_second_update_while_one_runs_is_409(client: TestClient, make_project) -> None:
    """The slot is taken by the request and released by the task, so a double click on the
    same stack cannot get two 202s and two overlapping deploys."""
    make_project("z")

    assert locks.try_acquire_project_slot("z")
    try:
        response = client.post("/api/projects/z/update")
        assert response.status_code == 409
        assert response.json()["detail"] == t("http.update_in_progress", "es")
    finally:
        locks.release_project_slot("z")


def test_create_schedule_rejects_unschedulable_date(client: TestClient) -> None:
    response = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "date",
            "frequency": "daily",
            "date_iso": "__not_a_parseable_datetime__",
        },
    )
    assert response.status_code == 422


def test_build_trigger_rejects_short_cron() -> None:
    from server.services.scheduler import build_trigger

    with pytest.raises(ValueError, match="5 campos"):
        build_trigger("cron", "1 2 3")


def test_api_requires_session_when_auth_enabled(logged_in_client: TestClient) -> None:
    logged_in_client.post("/api/auth/logout")
    response = logged_in_client.get("/api/projects")
    assert response.status_code == 401
    assert response.json().get("detail") == "Sesión expirada"
    assert response.json().get("code") == "session_expired"


def test_scan_syncs_stored_project_path(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    root = tmp_path / "projects_root"
    proj_dir = root / "myapp"
    proj_dir.mkdir(parents=True)
    (proj_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(projects_module, "PROJECTS_ROOT", root)

    def _fake_run_command(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(projects_module, "run_command", _fake_run_command)

    r1 = client.get("/api/projects")
    assert r1.status_code == 200
    db = SessionLocal()
    try:
        row = db.query(ProjectSettings).filter(ProjectSettings.name == "myapp").first()
        assert row is not None
        assert row.path == str(proj_dir)
        row.path = "/stale/wrong/path"
        db.commit()
    finally:
        db.close()

    r2 = client.get("/api/projects")
    assert r2.status_code == 200
    db = SessionLocal()
    try:
        row = db.query(ProjectSettings).filter(ProjectSettings.name == "myapp").first()
        assert row is not None
        assert row.path == str(proj_dir)
    finally:
        db.close()


def test_update_rejects_project_path_outside_projects_root(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    root = tmp_path / "stacks"
    proj_dir = root / "myapp"
    proj_dir.mkdir(parents=True)
    (proj_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(projects_module, "PROJECTS_ROOT", root)

    def _fake_run_command(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(projects_module, "run_command", _fake_run_command)

    assert client.get("/api/projects").status_code == 200
    db = SessionLocal()
    try:
        row = db.query(ProjectSettings).filter(ProjectSettings.name == "myapp").first()
        assert row is not None
        row.path = str(outside)
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/projects/myapp/update",
        headers={"Accept-Language": "es"},
    )
    # 202 only says the work was queued. The containment check runs inside it and fails
    # the deploy, which is what /update-status and the history row report.
    assert response.status_code == 202
    assert "STACKS_PATH" not in response.text

    assert client.get("/api/update-status").json()["projects"]["myapp"] == "error"
    history = client.get("/api/history").json()
    assert len(history) == 1
    assert history[0]["status"] == "ERROR"


def test_update_project_failure_hides_internal_logs_in_http_detail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, make_project
) -> None:
    make_project("anything")

    def _fake_update(_name, _db, **_kw):
        return False, ["INTERNAL_DOCKER_STDERR_SECRET"]

    monkeypatch.setattr(
        projects_router_module, "update_single_project_logic", _fake_update
    )

    response = client.post("/api/projects/anything/update")
    assert response.status_code == 202
    # The 202 body is an acknowledgement, not a report: the logs live in the history row,
    # behind the session, rather than in the answer to the request that started the work.
    assert "INTERNAL_DOCKER" not in response.text


def test_validate_startup_warns_but_never_aborts(
    monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """With no credentials the startup carries on: the wizard creates them.

    It used to assert nothing at all, so it was true by construction. Both branches are
    exercised now, including the ephemeral-secret warning that tells an operator their
    volume is not writable.
    """
    import server.config as cfg

    monkeypatch.setattr(cfg, "SESSION_SECRET_SOURCE", "file")
    with caplog.at_level("INFO"):
        cfg.validate_startup_security()
    assert not [r for r in caplog.records if r.levelname == "WARNING"]

    caplog.clear()
    monkeypatch.setattr(cfg, "SESSION_SECRET_SOURCE", "ephemeral")
    with caplog.at_level("INFO"):
        cfg.validate_startup_security()
    assert [r for r in caplog.records if r.levelname == "WARNING"]


def test_validate_startup_warns_when_public_url_has_no_scheme(
    monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """Without a scheme the cookie silently loses Secure and XFF stops being trusted."""
    import server.config as cfg

    monkeypatch.setattr(cfg, "SESSION_SECRET_SOURCE", "file")
    monkeypatch.setattr(cfg, "PUBLIC_URL", "pullpilot.example.com")
    monkeypatch.setattr(cfg, "_public_scheme", "")

    with caplog.at_level("WARNING"):
        cfg.validate_startup_security()

    assert any("PUBLIC_URL" in r.message for r in caplog.records)


def test_validate_startup_warns_on_an_ephemeral_secret(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Unwritable volume: it still boots, but sessions do not survive a restart."""
    import server.config as cfg

    monkeypatch.setattr(cfg, "SESSION_SECRET_SOURCE", "ephemeral")
    with caplog.at_level("WARNING", logger="pullpilot"):
        cfg.validate_startup_security()
    assert "secreto de sesión" in caplog.text


def test_history_timestamps_carry_an_utc_offset(client: TestClient) -> None:
    """SQLite drops the tzinfo, so the row comes back naive and was serialised naive.

    Without an offset the browser's `new Date(...)` reads the string as local time and
    the history was shown shifted by the viewer's UTC offset.
    """
    from server.services.update_logs import persist_update_log

    db = SessionLocal()
    try:
        persist_update_log(db, status="SUCCESS", summary="x", details={})
    finally:
        db.close()

    row = client.get("/api/history").json()[0]
    assert row["timestamp"].endswith("Z") or "+00:00" in row["timestamp"]

    parsed = datetime.fromisoformat(row["timestamp"])
    assert parsed.tzinfo is not None
    # Within a minute of now: proves it is really UTC and not local read as UTC.
    delta = abs((datetime.now(UTC) - parsed).total_seconds())
    assert delta < 60, f"timestamp is {delta}s away from now"


def _fake_compose(running: int, created: int):
    """`compose ps -q` lists what is up; `ps -a -q` everything Compose has created.

    Compared against created containers rather than the services `config --services`
    declares: that also lists services gated behind `profiles:`, which never run, so any
    stack using profiles was permanently `partial`.
    """

    def run(cmd, cwd=None, **_kwargs):
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        if text.endswith("ps -a -q"):
            return "\n".join(f"container{n}" for n in range(created))
        if text.endswith("ps -q"):
            return "\n".join(f"container{n}" for n in range(running))
        return ""

    return run


@pytest.mark.parametrize(
    ("running", "created", "expected"),
    [
        (3, 3, "running"),
        (2, 5, "partial"),
        (0, 5, "stopped"),
        # More running than created is not reachable in practice; treated as healthy.
        (6, 3, "running"),
    ],
)
def test_project_status_reports_a_half_up_stack(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    running: int,
    created: int,
    expected: str,
) -> None:
    """A stack with 2 of 5 services alive used to report `running` and look healthy."""
    root = tmp_path / "stacks"
    proj = root / "half"
    proj.mkdir(parents=True)
    (proj / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(projects_module, "PROJECTS_ROOT", root)
    monkeypatch.setattr(projects_module, "run_command", _fake_compose(running, created))

    body = client.get("/api/projects").json()

    assert [p["status"] for p in body] == [expected]
    assert body[0]["containers"] == running


@pytest.mark.parametrize(
    ("endpoint", "field"),
    [("toggle_exclude", "excluded"), ("toggle_fullstop", "full_stop")],
)
def test_toggle_flips_the_field_and_is_idempotent_in_pairs(
    client: TestClient, make_project, endpoint: str, field: str
) -> None:
    """Both toggles are advertised in the README and had no test at all."""
    make_project("plex")

    assert client.post(f"/api/projects/plex/{endpoint}").status_code == 200
    assert _project_field("plex", field) is True

    assert client.post(f"/api/projects/plex/{endpoint}").status_code == 200
    assert _project_field("plex", field) is False


@pytest.mark.parametrize("endpoint", ["toggle_exclude", "toggle_fullstop"])
def test_toggle_of_an_unknown_project_is_404(client: TestClient, endpoint: str) -> None:
    assert client.post(f"/api/projects/no-existe/{endpoint}").status_code == 404


def test_toggle_exclude_is_reflected_in_the_projects_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    root = tmp_path / "stacks"
    proj = root / "plex"
    proj.mkdir(parents=True)
    (proj / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(projects_module, "PROJECTS_ROOT", root)
    monkeypatch.setattr(projects_module, "run_command", _fake_compose(1, 1))

    assert client.get("/api/projects").json()[0]["excluded"] is False
    client.post("/api/projects/plex/toggle_exclude")
    assert client.get("/api/projects").json()[0]["excluded"] is True


def _project_field(name: str, field: str):
    db = SessionLocal()
    try:
        row = db.query(ProjectSettings).filter(ProjectSettings.name == name).first()
        return getattr(row, field)
    finally:
        db.close()


def test_delete_schedule_removes_the_row(client: TestClient) -> None:
    """Only the 404 branch was covered; nothing asserted the row actually went away."""
    created = client.post(
        "/api/schedules",
        json={
            "target": "GLOBAL",
            "task_type": "cron",
            "frequency": "daily",
            "hour": 4,
            "minute": 0,
        },
    )
    assert created.status_code == 200, created.text
    schedule_id = created.json()["id"]
    assert len(client.get("/api/schedules").json()) == 1

    assert client.delete(f"/api/schedules/{schedule_id}").status_code == 200

    assert client.get("/api/schedules").json() == []
    assert client.delete(f"/api/schedules/{schedule_id}").status_code == 404


def test_history_can_be_paged_past_the_first_twenty(client: TestClient) -> None:
    """HISTORY_RETENTION keeps 200 rows but only 20 were ever reachable."""
    db = SessionLocal()
    try:
        for n in range(25):
            persist_update_log(db, status="SUCCESS", summary=f"run {n}", details={})
    finally:
        db.close()

    assert len(client.get("/api/history").json()) == 20
    assert len(client.get("/api/history?limit=25").json()) == 25
    assert len(client.get("/api/history?limit=20&offset=20").json()) == 5
    assert client.get("/api/history?limit=0").status_code == 422


def test_update_all_is_rejected_while_one_is_running(client: TestClient) -> None:
    """The endpoint used to answer 200 "started" for a run it never launched.

    `global_update_job` returns after one log line when it cannot take the lock, so the SPA
    was told an update had begun and drew a progress bar for it.
    """
    from server.services.scheduler import global_update_lock

    assert global_update_lock.acquire(blocking=False)
    try:
        response = client.post("/api/update-all")
        assert response.status_code == 409
        assert response.json()["detail"] == t("http.update_all_in_progress", "es")
    finally:
        global_update_lock.release()

    # Released again: the next caller gets through.
    assert client.post("/api/update-all").status_code == 200


def test_history_pages_do_not_repeat_rows_sharing_a_timestamp(
    client: TestClient,
) -> None:
    """Ordering by timestamp alone left rows written in the same instant unordered.

    A row whose position is up to SQLite is one that can cross a page boundary and be
    served twice, or never.
    """
    stamp = datetime(2026, 8, 5, 12, 0, 0, tzinfo=UTC)
    db = SessionLocal()
    try:
        for n in range(30):
            db.add(UpdateLog(timestamp=stamp, status="SUCCESS", summary=f"run {n}", details="{}"))
        db.commit()
    finally:
        db.close()

    first = [row["id"] for row in client.get("/api/history?limit=10&offset=0").json()]
    second = [row["id"] for row in client.get("/api/history?limit=10&offset=10").json()]
    third = [row["id"] for row in client.get("/api/history?limit=10&offset=20").json()]

    seen = first + second + third
    assert len(seen) == 30
    assert len(set(seen)) == 30, "a row was served on two different pages"
    # Newest first, and with equal timestamps that is descending id.
    assert seen == sorted(seen, reverse=True)


def _cron_payload(target: str, *, hour: int = 4) -> dict:
    return {
        "target": target,
        "task_type": "cron",
        "frequency": "daily",
        "hour": hour,
        "minute": 0,
    }


def test_schedule_for_an_unknown_project_is_rejected(client: TestClient) -> None:
    """It used to be accepted and then skipped at fire time with one line in the log.

    The task sat in the list as active forever, promising a run that could never happen.
    """
    response = client.post("/api/schedules", json=_cron_payload("no-existe"))

    assert response.status_code == 404
    assert response.json()["detail"] == t("http.schedule_target_unknown", "es")
    assert client.get("/api/schedules").json() == []


def test_schedule_for_an_excluded_project_is_rejected(
    client: TestClient, make_project
) -> None:
    """`excluded` means never update automatically, so scheduling one is a contradiction."""
    make_project("plex")
    assert client.post("/api/projects/plex/toggle_exclude").status_code == 200

    response = client.post("/api/schedules", json=_cron_payload("plex"))

    assert response.status_code == 409
    assert response.json()["detail"] == t("http.schedule_target_excluded", "es")

    # Un-excluding it makes the very same request work.
    assert client.post("/api/projects/plex/toggle_exclude").status_code == 200
    assert client.post("/api/schedules", json=_cron_payload("plex")).status_code == 200


def test_an_identical_schedule_is_rejected(client: TestClient, make_project) -> None:
    """Two identical rows are two jobs firing on the same stack in the same minute.

    The table has no unique constraint and the form's submit guard only stops a double
    click, not two deliberate creations.
    """
    make_project("plex")
    assert client.post("/api/schedules", json=_cron_payload("plex")).status_code == 200

    duplicate = client.post("/api/schedules", json=_cron_payload("plex"))
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == t("http.schedule_duplicate", "es")

    # A different time is a different schedule, not a duplicate.
    assert (
        client.post("/api/schedules", json=_cron_payload("plex", hour=5)).status_code
        == 200
    )
    assert len(client.get("/api/schedules").json()) == 2


def test_the_global_target_never_needs_a_project_row(client: TestClient) -> None:
    """GLOBAL is not a project name and must skip the existence check entirely."""
    assert client.post("/api/schedules", json=_cron_payload("GLOBAL")).status_code == 200


def _stack(root, name: str):
    d = root / name
    d.mkdir(parents=True)
    (d / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    return d


def test_scan_retires_rows_for_stacks_that_are_gone(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The projects table only ever grew, like the history and the lock registries did."""
    root = tmp_path / "stacks"
    _stack(root, "plex")
    _stack(root, "pihole")
    monkeypatch.setattr(projects_module, "PROJECTS_ROOT", root)
    monkeypatch.setattr(projects_module, "run_command", lambda *_a, **_kw: "")

    assert len(client.get("/api/projects").json()) == 2

    import shutil

    shutil.rmtree(root / "pihole")

    assert [p["name"] for p in client.get("/api/projects").json()] == ["plex"]
    db = SessionLocal()
    try:
        assert db.query(ProjectSettings).filter_by(name="pihole").first() is None
    finally:
        db.close()


def test_scan_keeps_a_gone_stack_that_still_carries_settings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A row leaves `seen` for reasons other than the user deleting the stack.

    A volume mounted at the wrong path, or a compose file missing for the seconds someone
    is editing it, would otherwise silently clear the `excluded` flag on a stack the user
    had deliberately fenced off — an unrecoverable change nobody asked for.
    """
    root = tmp_path / "stacks"
    _stack(root, "plex")
    _stack(root, "pihole")
    monkeypatch.setattr(projects_module, "PROJECTS_ROOT", root)
    monkeypatch.setattr(projects_module, "run_command", lambda *_a, **_kw: "")

    assert len(client.get("/api/projects").json()) == 2
    assert client.post("/api/projects/pihole/toggle_exclude").status_code == 200

    import shutil

    shutil.rmtree(root / "pihole")
    client.get("/api/projects")

    db = SessionLocal()
    try:
        row = db.query(ProjectSettings).filter_by(name="pihole").first()
        assert row is not None and row.excluded is True
    finally:
        db.close()


def test_an_empty_scan_never_prunes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Finding nothing is the shape of a bad mount far more often than of an empty homelab."""
    root = tmp_path / "stacks"
    _stack(root, "plex")
    monkeypatch.setattr(projects_module, "PROJECTS_ROOT", root)
    monkeypatch.setattr(projects_module, "run_command", lambda *_a, **_kw: "")

    assert len(client.get("/api/projects").json()) == 1

    import shutil

    shutil.rmtree(root / "plex")

    assert client.get("/api/projects").json() == []
    db = SessionLocal()
    try:
        assert db.query(ProjectSettings).filter_by(name="plex").first() is not None
    finally:
        db.close()


def test_an_unreadable_stacks_folder_returns_an_empty_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mount that exists but cannot be listed used to 500 the dashboard scan."""
    from unittest.mock import MagicMock

    root = MagicMock()
    root.exists.return_value = True
    root.iterdir.side_effect = PermissionError("EACCES")
    monkeypatch.setattr(projects_module, "PROJECTS_ROOT", root)
    response = client.get("/api/projects")
    assert response.status_code == 200
    assert response.json() == []
