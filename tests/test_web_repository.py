from __future__ import annotations

from pathlib import Path

from app.core.database import Database
from app.web.repository import build_post_filter, list_posts, matching_post_ids, post_detail


def make_db(path: Path) -> Database:
    db = Database(path)
    db.connect()
    db.initialize_schema()
    for post_id, status, score in ((3, "new", 10), (2, "saved", 50), (1, "potential", 20)):
        db.execute(
            "INSERT INTO posts (id, status, score, preview_url) VALUES (?, ?, ?, ?)",
            (post_id, status, score, f"https://example.test/{post_id}.jpg"),
        )
    db.executemany(
        "INSERT INTO post_tags (post_id, tag, tag_type) VALUES (?, ?, 'general')",
        ((3, "blue_hair"), (2, "blue_hair"), (1, "red_hair")),
    )
    db.commit()
    return db


def test_web_post_batches_are_not_capped_to_desktop_preview_limit(tmp_path: Path) -> None:
    db = make_db(tmp_path / "web.db")
    try:
        result = list_posts(db, status="all", search="", sort="id_desc", offset=0, limit=200)
    finally:
        db.close()
    assert [item["id"] for item in result["items"]] == [3, 2, 1]
    assert result["total"] == 3
    assert result["has_more"] is False


def test_web_viewer_navigation_uses_complete_filtered_result(tmp_path: Path) -> None:
    db = make_db(tmp_path / "viewer.db")
    try:
        ids = matching_post_ids(db, status="all", search="blue_hair", sort="score_desc")
    finally:
        db.close()
    assert ids == [2, 3]


def test_web_viewer_returns_typed_tags_and_preview_strip(tmp_path: Path) -> None:
    db = make_db(tmp_path / "viewer-detail.db")
    db.execute(
        "INSERT INTO post_tags (post_id, tag, tag_type) VALUES (?, ?, ?)",
        (3, "example_artist", "artist"),
    )
    db.commit()
    db.add_filename_excluded_tag("blue_hair", "test")
    db.set_tag_manual_score("blue_hair", 2.5)
    db.set_tag_scoring_flags(
        "blue_hair",
        ignore_category_influence=True,
        ignore_recommendation_score=True,
        ignore_llm_input=True,
    )
    try:
        result = post_detail(db, 3, status="all", search="", sort="id_desc")
    finally:
        db.close()

    assert result is not None
    assert [item["tag"] for item in result["typed_tags"]["artist"]] == ["example_artist"]
    general = next(item for item in result["typed_tags"]["general"] if item["tag"] == "blue_hair")
    assert general["filename_excluded"] is True
    assert general["manual_score"] == 2.5
    assert general["score"] == 2.5
    assert general["ignore_category_influence"] is True
    assert general["ignore_recommendation_score"] is True
    assert general["ignore_llm_input"] is True
    assert [item["id"] for item in result["preview_strip"]] == [3, 2, 1]
    assert result["preview_strip"][0]["active"] is True


def test_negative_tag_filter_is_parameterized() -> None:
    sql, params = build_post_filter("worklist", "blue_hair -comic")
    assert "NOT EXISTS" in sql
    assert params == ["%blue_hair%", "blue_hair", "comic"]
