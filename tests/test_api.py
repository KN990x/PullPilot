import pytest
import server.routers.projects as projects_router_module
import server.services.projects as projects_module
from fastapi.testclient import TestClient
from server.database import SessionLocal
from server.models.db import ProjectSettings


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


def test_get_projects(client: TestClient) -> None:
    response = client.get("/api/projects")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


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
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    assert r.status_code == 200
    assert seen.get("locale") == "en"


def test_update_failed_detail_english(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        projects_router_module,
        "update_single_project_logic",
        lambda _n, _db, **kw: (False, []),
    )

    r = client.post(
        "/api/projects/x/update",
        headers={"Accept-Language": "en"},
    )
    assert r.status_code == 500
    detail = r.json().get("detail", "")
    assert "history" in detail.lower() or "ui" in detail.lower()


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
    assert response.status_code == 500
    detail = response.json().get("detail", "")
    assert "historial" in detail.lower()
    assert "PROJECTS_ROOT" not in detail


def test_update_project_failure_hides_internal_logs_in_http_detail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_update(_name, _db, **_kw):
        return False, ["INTERNAL_DOCKER_STDERR_SECRET"]

    monkeypatch.setattr(
        projects_router_module, "update_single_project_logic", _fake_update
    )

    response = client.post("/api/projects/anything/update")
    assert response.status_code == 500
    assert "INTERNAL_DOCKER" not in response.text


def test_validate_startup_no_longer_requires_env_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sin credenciales el arranque sigue adelante: las crea el asistente por UI."""
    import server.config as cfg

    monkeypatch.setattr(cfg, "ALLOW_NO_AUTH", False)
    monkeypatch.setattr(cfg, "AUTH_SEED_USER", None)
    monkeypatch.setattr(cfg, "AUTH_SEED_PASS", None)
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    cfg.validate_startup_security()


def test_validate_startup_warns_on_explicit_no_auth(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import server.config as cfg

    monkeypatch.setattr(cfg, "ALLOW_NO_AUTH", True)
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    with caplog.at_level("WARNING", logger="pullpilot"):
        cfg.validate_startup_security()
    assert "ALLOW_NO_AUTH" in caplog.text


def test_validate_startup_warns_on_multiple_workers(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Ya no es un error: el secreto se comparte por fichero. Lo que duplica es el scheduler."""
    import server.config as cfg

    monkeypatch.setenv("UVICORN_WORKERS", "2")
    monkeypatch.setattr(cfg, "ALLOW_NO_AUTH", False)
    with caplog.at_level("WARNING", logger="pullpilot"):
        cfg.validate_startup_security()
    assert "UVICORN_WORKERS=2" in caplog.text
