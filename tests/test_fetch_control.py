from __future__ import annotations

import unittest

from app.danbooru.api import DanbooruSearchPage
from app.services.post_import_service import FetchProgress, PostImportService


class _FakeDatabase:
    def fetch_excluded_tag_set(self) -> set[str]:
        return set()


class _FakeApi:
    def __init__(self, posts: list[dict[str, object]]) -> None:
        self.posts = posts
        self.calls = 0

    def get_posts(self, _query: str, *, limit: int, page: str | None = None) -> DanbooruSearchPage:
        _ = limit, page
        self.calls += 1
        return DanbooruSearchPage(posts=self.posts, next_page=None)


class _UnusedThumbnailCache:
    def cache_thumbnail(self, _post: dict[str, object]) -> None:
        raise AssertionError("decided posts must not download thumbnails")


def build_service(
    posts: list[dict[str, object]],
    store_results: dict[int, str],
    *,
    known_streak_limit: int = 0,
    progress_callback=None,
    cancel_requested=None,
) -> PostImportService:
    service = object.__new__(PostImportService)
    service.config = {
        "search_tags": "test_tag",
        "use_saved_searches": False,
        "max_posts_per_query": 100,
        "max_total_posts": 100,
        "limit": 100,
        "max_consecutive_known_posts": known_streak_limit,
        "fetch_exclude_enabled": False,
        "resolution_filters": {},
    }
    service.db = _FakeDatabase()
    service.api = _FakeApi(posts)
    service.thumbnail_cache = _UnusedThumbnailCache()
    service.progress_callback = progress_callback
    service.log_callback = None
    service.cancel_requested = cancel_requested
    service.store_post = lambda post: store_results[int(post["id"])]
    service.get_status = lambda _post_id: "saved"
    service.set_thumbnail_path = lambda _post_id, _path: None
    return service


class FetchControlTests(unittest.TestCase):
    def test_known_streak_stops_only_after_consecutive_known_posts(self) -> None:
        posts = [{"id": post_id} for post_id in range(1, 8)]
        service = build_service(
            posts,
            {
                1: "updated",
                2: "updated",
                3: "inserted",
                4: "updated",
                5: "updated",
                6: "updated",
                7: "inserted",
            },
            known_streak_limit=3,
        )

        result = service.fetch_and_store()

        self.assertFalse(result.cancelled)
        self.assertEqual(result.seen_posts, 6)
        self.assertEqual(result.inserted_posts, 1)
        self.assertEqual(result.updated_posts, 5)
        self.assertEqual(result.known_streak_stopped_queries, ["test_tag"])

    def test_cancel_stops_before_processing_the_next_post(self) -> None:
        cancel_state = {"requested": False}

        def on_progress(progress: FetchProgress) -> None:
            if progress.phase == "post":
                cancel_state["requested"] = True

        posts = [{"id": post_id} for post_id in range(1, 6)]
        service = build_service(
            posts,
            {post_id: "updated" for post_id in range(1, 6)},
            progress_callback=on_progress,
            cancel_requested=lambda: cancel_state["requested"],
        )

        result = service.fetch_and_store()

        self.assertTrue(result.cancelled)
        self.assertEqual(result.seen_posts, 1)
        self.assertEqual(result.updated_posts, 1)

    def test_viewer_query_requests_every_matching_post(self) -> None:
        from app.gui.preview_window import PreviewWindow

        class FakePreview:
            current_limit = 100

            def selected_statuses(self):
                return ["new"]

            def current_search_text(self):
                return "solo"

            def selected_category_filter(self):
                return "__all__"

            def selected_recommendation_minimum(self):
                return None

            def selected_sort_key(self):
                return "id_desc"

            def fetch_preview_navigation_rows(self, **kwargs):
                self.fetch_arguments = kwargs
                return [{"id": 350}, {"id": 349}, {"id": 348}]

            def enrich_preview_rows_with_categories(self, rows):
                return rows

            def category_matches_filter(self, _row, _category):
                return True

            def recommendation_matches_filter(self, _row, _minimum):
                return True

            def sort_preview_rows_in_python(self, rows, _sort_key):
                return rows

            def group_related_preview_rows(self, rows):
                return rows

        preview = FakePreview()

        post_ids = PreviewWindow.all_matching_viewer_post_ids(preview)

        self.assertEqual(post_ids, [350, 349, 348])
        self.assertEqual(preview.fetch_arguments["limit"], -1)
        self.assertEqual(preview.fetch_arguments["offset"], 0)


if __name__ == "__main__":
    unittest.main()
