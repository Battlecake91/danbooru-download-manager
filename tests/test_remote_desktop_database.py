from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.web.app as web_app
from app.core.connection_profile import (
    REMOTE_MODE,
    apply_connection_profile,
    database_from_config,
    load_connection_profile,
    save_connection_profile,
    validate_connection_profile,
)
from app.core.remote_database import RemoteCursor, RemoteDatabase
from app.web.runtime import open_database


def test_connection_profile_round_trip_and_factory(tmp_path: Path) -> None:
    config = {"work_dir": str(tmp_path), "database_file": str(tmp_path / "local.db")}
    profile = {
        "mode": REMOTE_MODE,
        "remote_url": "http://docker.test:8765/",
        "remote_token": "secret",
    }

    path = save_connection_profile(config, profile)
    loaded = load_connection_profile(config)
    apply_connection_profile(config, loaded)

    assert path == tmp_path / "desktop_connection.json"
    assert loaded == {
        "mode": REMOTE_MODE,
        "remote_url": "http://docker.test:8765",
        "remote_token": "secret",
    }
    database = database_from_config(config)
    assert isinstance(database, RemoteDatabase)
    database.close()


def test_remote_profile_requires_url_and_token() -> None:
    with pytest.raises(ValueError, match="http"):
        validate_connection_profile({"mode": REMOTE_MODE, "remote_url": "docker", "remote_token": "x"})
    with pytest.raises(ValueError, match="token"):
        validate_connection_profile({"mode": REMOTE_MODE, "remote_url": "http://docker", "remote_token": ""})


def test_remote_cursor_supports_sqlite_style_key_and_index_access() -> None:
    cursor = RemoteCursor(
        {
            "columns": ["id", "status"],
            "rows": [{"id": 12, "status": "potential"}],
            "rowcount": 1,
        }
    )
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == 12
    assert row["status"] == "potential"


def test_remote_status_updates_never_send_desktop_paths(monkeypatch) -> None:
    database = RemoteDatabase("http://docker.test:8765", "secret")
    calls: list[tuple[str, str, dict[str, object]]] = []

    def fake_request(method: str, endpoint: str, **kwargs):
        calls.append((method, endpoint, kwargs))
        return {"ok": True}

    monkeypatch.setattr(database, "_request", fake_request)
    desktop_config = {"rejected_thumbnail_dir": r"C:\desktop\thumbnails\rejected"}

    database.set_post_status(12, "rejected", desktop_config)
    database.set_post_statuses([12, 13, 12], "potential", desktop_config)

    assert calls == [
        ("PATCH", "/api/posts/12", {"json": {"status": "rejected"}}),
        (
            "PATCH",
            "/api/posts/status",
            {"json": {"post_ids": [12, 13], "status": "potential"}},
        ),
    ]
    assert "C:\\desktop" not in repr(calls)
    database.close()


def test_desktop_health_requires_configured_matching_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DANBOORU_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DANBOORU_OUTPUT_DIR", str(tmp_path / "archive"))
    monkeypatch.setenv("DANBOORU_DESKTOP_API_TOKEN", "correct-token")
    app = web_app.create_app()
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/desktop/health")

    request = SimpleNamespace(app=app, headers={"Authorization": "Bearer correct-token"})
    assert endpoint(request)["ok"] is True

    request.headers = {"Authorization": "Bearer wrong-token"}
    with pytest.raises(HTTPException) as error:
        endpoint(request)
    assert error.value.status_code == 401


def test_desktop_api_is_disabled_without_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DANBOORU_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DANBOORU_OUTPUT_DIR", str(tmp_path / "archive"))
    monkeypatch.delenv("DANBOORU_DESKTOP_API_TOKEN", raising=False)
    app = web_app.create_app()
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/desktop/health")

    with pytest.raises(HTTPException) as error:
        endpoint(SimpleNamespace(app=app, headers={}))
    assert error.value.status_code == 503


def test_desktop_sql_endpoint_returns_serializable_rows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DANBOORU_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DANBOORU_OUTPUT_DIR", str(tmp_path / "archive"))
    monkeypatch.setenv("DANBOORU_DESKTOP_API_TOKEN", "test-token")
    app = web_app.create_app()
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/desktop/sql")
    request = SimpleNamespace(app=app, headers={"Authorization": "Bearer test-token"})
    db = open_database(app.state.config)
    try:
        db.execute("INSERT INTO posts (id, status) VALUES (?, ?)", (321, "potential"))
        db.commit()
        result = endpoint(
            web_app.DesktopSqlRequest(
                operation="execute",
                sql="SELECT id, status FROM posts WHERE id = ?",
                parameters=[321],
            ),
            request,
            db,
        )
    finally:
        db.close()

    assert result["columns"] == ["id", "status"]
    assert result["rows"] == [{"id": 321, "status": "potential"}]
