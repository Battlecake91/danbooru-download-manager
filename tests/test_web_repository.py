from __future__ import annotations

from pathlib import Path

from app.core.database import Database
from app.web.repository import SORT_SQL, build_post_filter, list_posts, matching_post_ids, post_detail, resolve_media_path
from app.web.runtime import fetch_overrides_from_payload


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


def test_web_viewer_can_reopen_post_after_status_removes_it_from_filter(tmp_path: Path) -> None:
    db = make_db(tmp_path / "viewer-history.db")
    db.execute("UPDATE posts SET status = 'rejected' WHERE id = 3")
    db.commit()
    try:
        result = post_detail(db, 3, status="worklist", search="", sort="id_desc")
    finally:
        db.close()

    assert result is not None
    assert result["id"] == 3
    assert result["status"] == "rejected"
    assert result["navigation"] == {
        "index": -1,
        "total": 1,
        "previous_id": None,
        "next_id": None,
    }
    assert [item["id"] for item in result["preview_strip"]] == [3]


def test_web_preselection_sort_and_summary_use_live_tag_scores(tmp_path: Path) -> None:
    db = make_db(tmp_path / "preselection.db")
    db.set_tag_manual_score("blue_hair", 2.5)
    db.set_tag_manual_score("red_hair", -3.0)
    try:
        best_first = list_posts(db, status="all", search="", sort="recommendation_desc", offset=0, limit=8)
        worst_first = list_posts(db, status="all", search="", sort="recommendation_asc", offset=0, limit=8)
    finally:
        db.close()

    assert [item["id"] for item in best_first["items"]] == [3, 2, 1]
    assert [item["recommendation_score"] for item in best_first["items"]] == [2.5, 2.5, -3.0]
    assert [item["id"] for item in worst_first["items"]] == [1, 3, 2]
    assert best_first["preselection_summary"] == {"best": 2.5, "worst": -3.0, "average": 0.67}


def test_every_web_preview_sort_executes(tmp_path: Path) -> None:
    db = make_db(tmp_path / "sorts.db")
    try:
        for sort in [*SORT_SQL, "recommendation_desc", "recommendation_asc"]:
            result = list_posts(db, status="all", search="", sort=sort, offset=0, limit=8)
            assert result["total"] == 3, sort
            assert len(result["items"]) == 3, sort
    finally:
        db.close()


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


def test_media_resolver_maps_windows_database_path_to_container_root(tmp_path: Path) -> None:
    active = tmp_path / "thumbnails" / "active"
    active.mkdir(parents=True)
    thumbnail = active / "12345_large.jpg"
    thumbnail.write_bytes(b"thumbnail")

    resolved = resolve_media_path(
        {"active_thumbnail_dir": active},
        {"id": 12345, "thumbnail_path": r"C:\desktop\cache\12345_large.jpg"},
        "thumbnail",
    )

    assert resolved == thumbnail.resolve()


def test_viewer_does_not_treat_thumbnail_as_full_image(tmp_path: Path) -> None:
    active = tmp_path / "thumbnails" / "active"
    active.mkdir(parents=True)
    thumbnail = active / "12345_large.jpg"
    thumbnail.write_bytes(b"thumbnail")

    resolved = resolve_media_path(
        {
            "active_thumbnail_dir": active,
            "original_cache_dir": tmp_path / "originals",
            "default_output_dir": tmp_path / "archive",
        },
        {"id": 12345, "thumbnail_path": str(thumbnail)},
        "viewer",
    )

    assert resolved is None


def test_desktop_fetch_preset_translates_for_web_runtime() -> None:
    overrides = fetch_overrides_from_payload(
        {
            "source_mode": "saved_searches",
            "saved_search_labels": "favorites, review",
            "saved_search_queries": "blue_hair",
            "rating_states": {"g": "include", "e": "exclude"},
            "max_posts_per_query": 250,
            "max_consecutive_known_posts": 40,
            "max_total_posts": 800,
            "fetch_exclude_enabled": False,
            "resolution_filters": {"min_width": 1200},
        }
    )

    assert overrides["use_saved_searches"] is True
    assert overrides["saved_search_labels"] == ["favorites", "review"]
    assert overrides["saved_search_queries"] == ["blue_hair"]
    assert overrides["saved_search_extra_tags"] == "rating:g -rating:e"
    assert overrides["max_consecutive_known_posts"] == 40
    assert overrides["fetch_exclude_enabled"] is False
    assert overrides["resolution_filters"] == {"min_width": 1200}


def test_fetch_presets_are_shared_through_database(tmp_path: Path) -> None:
    db = make_db(tmp_path / "presets.db")
    try:
        db.save_fetch_preset("Daily", {"source_mode": "tags", "manual_query": "blue_hair"})
        rows = db.list_fetch_presets()
        payload = db.get_fetch_preset("Daily")
        db.delete_fetch_preset("Daily")
        remaining = db.list_fetch_presets()
    finally:
        db.close()

    assert [row["name"] for row in rows] == ["Daily"]
    assert payload == {"manual_query": "blue_hair", "source_mode": "tags"}
    assert remaining == []
