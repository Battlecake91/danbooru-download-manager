from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.gui.preview_window import PreviewWindow
from app.core.recommendation_engine import RecommendationEngine
from tests.helpers import assert_plan_uses_index, explain_plan, open_temp_database, seed_posts_with_tags, timed


class DatabasePerformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        _, self.db = open_temp_database(Path(self.tmp.name))
        seed_posts_with_tags(self.db, count=3000, tags_per_post=5)

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_worklist_preview_uses_status_index_and_stays_fast(self) -> None:
        where_sql, parameters = self.db._build_preview_where(  # noqa: SLF001
            view_mode="worklist",
            status_filter=None,
            text_filter=None,
            worklist_statuses=["new", "potential"],
        )
        plan = explain_plan(
            self.db,
            f"""
            SELECT p.id
            FROM posts p
            {where_sql}
            ORDER BY p.id DESC
            LIMIT ?
            OFFSET ?
            """,
            [*parameters, 100, 0],
        )

        assert_plan_uses_index(self, plan, "idx_posts_status")
        rows, elapsed = timed(
            lambda: self.db.fetch_preview_posts(
                view_mode="worklist",
                worklist_statuses=["new", "potential"],
                limit=100,
            )
        )
        self.assertEqual(len(rows), 100)
        self.assertLess(elapsed, 0.75, msg=f"fetch_preview_posts took {elapsed:.3f}s")

    def test_viewer_navigation_does_not_load_preview_details(self) -> None:
        class PreviewQueryHarness:
            build_preview_where = PreviewWindow.build_preview_where
            is_path_like_search_term = staticmethod(PreviewWindow.is_path_like_search_term)
            fetch_preview_navigation_rows = PreviewWindow.fetch_preview_navigation_rows

            def __init__(self, db) -> None:
                self.db = db

        preview = PreviewQueryHarness(self.db)
        rows, elapsed = timed(
            lambda: preview.fetch_preview_navigation_rows(
                statuses=["new", "potential", "saved", "rejected", "already_known"],
                text_filter=None,
                limit=-1,
                offset=0,
                sort_key="id_desc",
            )
        )

        self.assertEqual(len(rows), 3000)
        self.assertEqual(set(rows[0].keys()), {"id", "parent_id"})
        self.assertLess(elapsed, 0.25, msg=f"viewer navigation took {elapsed:.3f}s")

    def test_preview_details_aggregate_tags_only_for_selected_posts(self) -> None:
        class PreviewQueryHarness:
            fetch_preview_detail_rows = PreviewWindow.fetch_preview_detail_rows

            def __init__(self, db) -> None:
                self.db = db

        preview = PreviewQueryHarness(self.db)
        rows, elapsed = timed(
            lambda: preview.fetch_preview_detail_rows(list(range(3000, 2900, -1)))
        )

        self.assertEqual(len(rows), 100)
        self.assertTrue(rows[0]["tags"])
        self.assertTrue(rows[0]["tags_general"])
        self.assertLess(elapsed, 0.25, msg=f"100 preview details took {elapsed:.3f}s")

    def test_bulk_recommendation_scoring_stays_bounded(self) -> None:
        engine = RecommendationEngine(self.db)
        tag_sets = [
            {f"tag_{(post_id + index) % 500:03d}" for index in range(5)}
            for post_id in range(1, 3001)
        ]

        scores, elapsed = timed(lambda: engine.score_tag_sets(tag_sets))

        self.assertEqual(len(scores), 3000)
        self.assertLess(elapsed, 0.35, msg=f"bulk recommendation scoring took {elapsed:.3f}s")

    def test_exact_tag_preview_search_uses_post_tag_index(self) -> None:
        where_sql, parameters = self.db._build_preview_where(  # noqa: SLF001
            view_mode="all",
            status_filter=None,
            text_filter="tag_042 -shared_cold_tag",
            worklist_statuses=None,
        )
        plan = explain_plan(
            self.db,
            f"""
            SELECT p.id
            FROM posts p
            {where_sql}
            ORDER BY p.id DESC
            LIMIT ?
            OFFSET ?
            """,
            [*parameters, 100, 0],
        )
        joined = "\n".join(plan)

        self.assertIn("idx_post_tags_post_tag", joined)
        rows, elapsed = timed(
            lambda: self.db.fetch_preview_posts(
                view_mode="all",
                text_filter="tag_042 -shared_cold_tag",
                limit=100,
            )
        )
        self.assertTrue(all("shared_cold_tag" not in str(row["tags"] or "") for row in rows))
        self.assertLess(elapsed, 0.75, msg=f"tag-filtered preview took {elapsed:.3f}s\n{joined}")

    def test_tag_completion_uses_type_tag_index(self) -> None:
        plan = explain_plan(
            self.db,
            """
            SELECT DISTINCT tag
            FROM post_tags
            WHERE tag_type = ? AND tag LIKE ?
            ORDER BY tag COLLATE NOCASE ASC
            LIMIT ?
            """,
            ("general", "tag_0%", 50),
        )

        assert_plan_uses_index(self, plan, "idx_post_tags_type_tag")
        suggestions, elapsed = timed(lambda: self.db.suggest_tags("tag_0", limit=100))
        self.assertTrue(suggestions)
        self.assertLess(elapsed, 0.5, msg=f"suggest_tags took {elapsed:.3f}s")

    def test_category_influence_query_uses_join_indexes(self) -> None:
        category_id = self.db.upsert_category("samples", "samples", None, None, 1)
        post_ids = list(range(2, 1000, 2))
        self.db.executemany(
            """
            INSERT INTO post_categories (post_id, category_id, source)
            VALUES (?, ?, 'test')
            ON CONFLICT(post_id, category_id) DO NOTHING
            """,
            [(post_id, category_id) for post_id in post_ids],
        )
        self.db.commit()

        plan = explain_plan(
            self.db,
            """
            SELECT pc.post_id
            FROM post_categories pc
            JOIN post_tags pt ON pt.post_id = pc.post_id
            WHERE pt.tag IN (?, ?)
            """,
            ("shared_hot_tag", "tag_042"),
        )

        assert_plan_uses_index(self, plan, "idx_post_tags_tag_post")
        rows, elapsed = timed(lambda: self.db.fetch_category_tag_hits(["shared_hot_tag", "tag_042"]))
        self.assertTrue(rows)
        self.assertLess(elapsed, 1.0, msg=f"fetch_category_tag_hits took {elapsed:.3f}s")

    def test_refresh_all_tag_statistics_stays_bounded_on_medium_dataset(self) -> None:
        _, elapsed = timed(self.db.refresh_all_tag_statistics)

        self.assertLess(
            elapsed,
            1.5,
            msg=(
                f"refresh_all_tag_statistics took {elapsed:.3f}s on 3000 posts. "
                "Run this test with --verbose locally and inspect EXPLAIN plans for "
                "post_tags/posts family joins if it regresses."
            ),
        )


if __name__ == "__main__":
    unittest.main()
