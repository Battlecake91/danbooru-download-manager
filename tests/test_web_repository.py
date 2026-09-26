from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.core.database import Database
from app.core.recommendation_engine import RecommendationEngine
from app.web.repository import (
    RecommendationResultCache,
    SORT_SQL,
    build_post_filter,
    list_posts,
    matching_post_ids,
    media_post_data,
    post_detail,
    recommendation_results,
    resolve_media_path,
)
from app.web.runtime import fetch_overrides_from_payload, open_database


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


def test_web_database_connection_can_cross_fastapi_worker_threads(tmp_path: Path) -> None:
    database_file = tmp_path / "threaded-web.db"
    setup = Database(database_file)
    setup.connect()
    setup.initialize_schema()
    setup.close()

    db = open_database({"database_file": str(database_file)})
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            count = executor.submit(
                lambda: int(db.execute("SELECT COUNT(*) FROM posts").fetchone()[0])
            ).result()
    finally:
        db.close()

    assert count == 0


def test_web_post_batches_are_not_capped_to_desktop_preview_limit(tmp_path: Path) -> None:
    db = make_db(tmp_path / "web.db")
    try:
        result = list_posts(db, status="all", search="", sort="id_desc", offset=0, limit=200)
    finally:
        db.close()
    assert [item["id"] for item in result["items"]] == [3, 2, 1]
    assert result["total"] == 3
    assert result["has_more"] is False


def test_web_categories_show_rule_suggestions_and_persist_manual_override(tmp_path: Path) -> None:
    db = make_db(tmp_path / "web-categories.db")
    blue_id = db.create_category("Blue", "blue")
    red_id = db.create_category("Red", "red")
    db.add_category_rule(blue_id, "include", "blue_hair")
    db.add_category_rule(red_id, "include", "red_hair")

    try:
        preview = list_posts(db, status="all", search="", sort="id_desc", offset=0, limit=20)
        by_id = {int(item["id"]): item for item in preview["items"]}
        assert by_id[3]["category_id"] == blue_id
        assert by_id[3]["category"] == "Blue"
        assert by_id[3]["category_source"] == "automatic"
        assert by_id[1]["category_id"] == red_id

        db.assign_post_category(3, red_id, source="manual-web")
        detail = post_detail(db, 3, status="all", search="", sort="id_desc")
    finally:
        db.close()

    assert detail is not None
    assert detail["category_id"] == red_id
    assert detail["category"] == "Red"
    assert detail["category_source"] == "manual-web"


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


def test_web_preselection_relevant_tag_query_matches_full_scoring(tmp_path: Path) -> None:
    db = make_db(tmp_path / "preselection-relevant.db")
    db.set_tag_manual_score("blue_hair", 2.5)
    db.set_tag_manual_score("red_hair", -3.0)
    db.set_tag_scoring_flags("blue_hair", ignore_recommendation_score=True)
    try:
        results = recommendation_results(db, "", [])
        expected = {}
        for post_id in (3, 2, 1):
            tags = [
                str(row["tag"])
                for row in db.execute("SELECT tag FROM post_tags WHERE post_id = ?", (post_id,)).fetchall()
            ]
            expected[post_id] = RecommendationEngine(db).score_tags(tags)
    finally:
        db.close()

    assert results == expected


def test_web_preselection_cache_reuses_and_invalidates_filter_results(tmp_path: Path) -> None:
    db = make_db(tmp_path / "preselection-cache.db")
    cache = RecommendationResultCache(ttl_seconds=60)
    db.set_tag_manual_score("blue_hair", 2.5)
    try:
        first = list_posts(
            db,
            status="all",
            search="",
            sort="recommendation_desc",
            offset=0,
            limit=8,
            recommendation_cache=cache,
        )
        db.set_tag_manual_score("blue_hair", 7.0)
        cached = list_posts(
            db,
            status="all",
            search="",
            sort="recommendation_desc",
            offset=0,
            limit=8,
            recommendation_cache=cache,
        )
        cache.clear()
        refreshed = list_posts(
            db,
            status="all",
            search="",
            sort="recommendation_desc",
            offset=0,
            limit=8,
            recommendation_cache=cache,
        )
    finally:
        db.close()

    assert first["preselection_summary"] == cached["preselection_summary"]
    assert refreshed["preselection_summary"] != first["preselection_summary"]
    assert refreshed["preselection_summary"]["best"] == 7.0


def test_web_preselection_cache_updates_status_membership_incrementally(tmp_path: Path) -> None:
    db = make_db(tmp_path / "preselection-status-cache.db")
    cache = RecommendationResultCache(ttl_seconds=60)
    try:
        worklist = list_posts(
            db,
            status="worklist",
            search="",
            sort="recommendation_desc",
            offset=0,
            limit=8,
            recommendation_cache=cache,
        )
        all_posts = list_posts(
            db,
            status="all",
            search="",
            sort="recommendation_desc",
            offset=0,
            limit=8,
            recommendation_cache=cache,
        )
        cache.apply_status_change(3, "new", "rejected")

        db_path = str(db.path.resolve())
        cached_worklist = cache.get((db_path, "worklist", ""))
        cached_all = cache.get((db_path, "all", ""))
    finally:
        db.close()

    assert worklist["total"] == 2
    assert all_posts["total"] == 3
    assert cached_worklist is not None and 3 not in cached_worklist
    assert cached_all is not None and 3 in cached_all


def test_web_preselection_cache_invalidates_filter_when_status_enters_it(tmp_path: Path) -> None:
    db = make_db(tmp_path / "preselection-enter-status-cache.db")
    cache = RecommendationResultCache(ttl_seconds=60)
    try:
        list_posts(
            db,
            status="worklist",
            search="",
            sort="recommendation_desc",
            offset=0,
            limit=8,
            recommendation_cache=cache,
        )
        db_path = str(db.path.resolve())
        cache.apply_status_change(2, "saved", "new")
        cached_worklist = cache.get((db_path, "worklist", ""))
    finally:
        db.close()

    assert cached_worklist is None


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


def test_media_lookup_uses_lightweight_row_and_direct_thumbnail_names(tmp_path: Path) -> None:
    db = make_db(tmp_path / "media-row.db")
    active = tmp_path / "thumbnails" / "active"
    active.mkdir(parents=True)
    thumbnail = active / "3_large.jpg"
    thumbnail.write_bytes(b"thumbnail")

    try:
        post = media_post_data(db, 3)
    finally:
        db.close()

    assert post is not None
    assert set(post) == {
        "id",
        "thumbnail_path",
        "rejected_thumbnail_path",
        "original_cache_path",
        "original_path",
        "final_file_path",
        "preview_url",
        "large_file_url",
        "file_url",
    }
    assert resolve_media_path({"active_thumbnail_dir": active}, post, "thumbnail") == thumbnail.resolve()


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
