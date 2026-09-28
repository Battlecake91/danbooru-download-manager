from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import app.web.app as web_app
from app.services.final_save_service import AlreadySavedError
from app.web.runtime import open_database


def test_bulk_save_continues_after_skipped_and_failed_posts(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "archive"
    monkeypatch.setenv("DANBOORU_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DANBOORU_OUTPUT_DIR", str(output_dir))
    app = web_app.create_app()

    db = open_database(app.state.config)
    try:
        db.executemany(
            "INSERT INTO posts (id, status) VALUES (?, 'new')",
            [(101,), (102,), (103,)],
        )
        db.commit()
    finally:
        db.close()

    calls: list[int] = []

    class FakeSaveService:
        def __init__(self, config, db) -> None:
            pass

        def save_post(self, post_id: int):
            calls.append(post_id)
            if post_id == 102:
                raise AlreadySavedError(post_id, "already.jpg")
            if post_id == 103:
                raise RuntimeError("disk full")
            return SimpleNamespace(
                post_id=post_id,
                category=SimpleNamespace(name="_unmatched"),
                category_source="auto",
                final_path=output_dir / f"{post_id}.jpg",
            )

    monkeypatch.setattr(web_app, "FinalSaveService", FakeSaveService)
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/posts/save")
    db = open_database(app.state.config)
    try:
        payload = endpoint(
            web_app.BulkPostSaveRequest(post_ids=[101, 102, 103]),
            SimpleNamespace(app=app),
            db,
        )
    finally:
        db.close()

    assert calls == [101, 102, 103]
    assert [item["post_id"] for item in payload["saved"]] == [101]
    assert [item["post_id"] for item in payload["skipped"]] == [102]
    assert payload["failed"] == [{"post_id": 103, "error": "disk full"}]
    assert payload["ok"] is False

    db = open_database(app.state.config)
    try:
        status = db.execute("SELECT status FROM posts WHERE id = 102").fetchone()["status"]
    finally:
        db.close()
    assert status == "saved"
