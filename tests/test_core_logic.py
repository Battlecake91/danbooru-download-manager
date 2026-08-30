from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.archive_paths import migrate_archive_paths, resolve_archive_path, set_archive_root_path
from app.core.category_engine import CategoryEngine, build_category_match_groups, build_category_rule_set
from app.core.db.common import calculate_computed_tag_score, calculate_rejected_percent, parse_preview_search_terms
from app.core.filename_builder import safe_filename, truncate_filename
from tests.helpers import open_temp_database


class CoreLogicTests(unittest.TestCase):
    def test_parse_preview_search_terms_supports_quotes_and_excludes(self) -> None:
        positive, negative = parse_preview_search_terms('blue_eyes "long hair" -red_hair')

        self.assertEqual(positive, ["blue_eyes", "long hair"])
        self.assertEqual(negative, ["red_hair"])

    def test_tag_score_is_damped_for_very_common_split_tags(self) -> None:
        score = calculate_computed_tag_score(
            average_rating=8,
            saved_count=700,
            rejected_count=500,
            scoring_excluded=False,
        )

        self.assertLess(score, 3.0)

    def test_rejected_percent_ignores_scoring_excluded_tags(self) -> None:
        self.assertEqual(
            calculate_rejected_percent(saved_count=3, rejected_count=1),
            25.0,
        )
        self.assertIsNone(
            calculate_rejected_percent(
                saved_count=3,
                rejected_count=1,
                scoring_excluded=True,
            )
        )
        self.assertIsNone(
            calculate_rejected_percent(saved_count=0, rejected_count=0)
        )

    def test_safe_filename_removes_windows_reserved_characters(self) -> None:
        self.assertEqual(safe_filename('a/b<c>d:e"f|g?h*i.jpg'), "a_b_c_d_e_f_g_h_i.jpg")

    def test_truncate_filename_preserves_extension(self) -> None:
        filename = truncate_filename("very_long_artist_and_tag_name.jpg", 16)

        self.assertLessEqual(len(filename), 16)
        self.assertTrue(filename.endswith(".jpg"))

    def test_category_rules_apply_global_conditions_to_each_group(self) -> None:
        rules = [
            {"rule_type": "group_1_include", "tag": "blue_eyes"},
            {"rule_type": "group_2_include", "tag": "green_eyes"},
            {"rule_type": "global_1_include", "tag": "solo"},
            {"rule_type": "global_1_exclude", "tag": "monochrome"},
        ]

        rule_set = build_category_rule_set(rules)
        groups = build_category_match_groups(rules)

        self.assertEqual(rule_set.global_required, {"solo"})
        self.assertEqual(rule_set.global_forbidden, {"monochrome"})
        self.assertIn(({"blue_eyes", "solo"}, {"monochrome"}), groups)
        self.assertIn(({"green_eyes", "solo"}, {"monochrome"}), groups)


class DatabaseBootstrapTests(unittest.TestCase):
    def test_schema_initializes_in_empty_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = open_temp_database(Path(tmp))
            try:
                tables = {
                    str(row["name"])
                    for row in db.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
            finally:
                db.close()

        self.assertIn("posts", tables)
        self.assertIn("post_tags", tables)
        self.assertIn("app_settings", tables)
        self.assertIn("tag_scores", tables)

    def test_legacy_viewer_file_cache_setting_is_normalized_to_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config, db = open_temp_database(Path(tmp))
            try:
                db.set_app_setting("viewer_download_source", '"file"')
                config["viewer_download_source"] = "large"
                db.apply_app_settings_to_config(config)
            finally:
                db.close()

        self.assertEqual(config["viewer_download_source"], "preview")

    def test_rejected_cache_purge_deletes_only_expired_cache_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            config, db = open_temp_database(base)
            try:
                config["workflow"]["rejected_thumbnail_retention_days"] = 7
                original_cache = Path(config["original_cache_dir"])
                rejected_thumbnails = Path(config["rejected_thumbnail_dir"])
                expired_original = original_cache / "10_preview.jpg"
                fresh_original = original_cache / "11_preview.jpg"
                outside_file = base / "outside.jpg"
                expired_thumb = rejected_thumbnails / "10_large.jpg"
                for path in (expired_original, fresh_original, outside_file, expired_thumb):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"cache")

                db.executemany(
                    """
                    INSERT INTO posts (
                        id, status, rejected_at, original_cache_path,
                        rejected_thumbnail_path, thumbnail_path
                    )
                    VALUES (?, 'rejected', datetime('now', ?), ?, ?, ?)
                    """,
                    [
                        (10, "-8 days", str(expired_original), str(expired_thumb), str(expired_thumb)),
                        (11, "-6 days", str(fresh_original), "", ""),
                        (12, "-8 days", str(outside_file), "", ""),
                    ],
                )
                db.commit()

                result = db.purge_rejected_cache_files(config)
                expired_row = db.get_post_detail(10)
                fresh_row = db.get_post_detail(11)
                outside_row = db.get_post_detail(12)

                self.assertFalse(expired_original.exists())
                self.assertFalse(expired_thumb.exists())
                self.assertTrue(fresh_original.exists())
                self.assertTrue(outside_file.exists())
                self.assertEqual(result["deleted_files"], 2)
                self.assertIsNone(expired_row["original_cache_path"])
                self.assertIsNone(expired_row["rejected_thumbnail_path"])
                self.assertEqual(fresh_row["original_cache_path"], str(fresh_original))
                self.assertEqual(outside_row["original_cache_path"], str(outside_file))
            finally:
                db.close()


class CategoryTagHintModeTests(unittest.TestCase):
    def seed_category_hint_fixture(self, db) -> tuple[int, int]:  # noqa: ANN001
        category_a = db.upsert_category("hard_match", "hard_match", None, None, 1)
        category_b = db.upsert_category("hint_match", "hint_match", None, None, 2)
        db.upsert_category("_unmatched", "_unmatched", None, None, 99)

        db.executemany(
            "INSERT INTO posts (id, status) VALUES (?, 'new')",
            [(1,), (2,), (3,), (4,), (5,)],
        )
        db.executemany(
            "INSERT INTO post_tags (post_id, tag, tag_type) VALUES (?, ?, 'general')",
            [
                (1, "hint_tag"),
                (2, "other_hint_category_tag"),
                (3, "hard_category_example"),
                (4, "other_hard_category_tag"),
                (5, "hint_tag"),
                (5, "hard_tag"),
            ],
        )
        db.executemany(
            "INSERT INTO post_categories (post_id, category_id, source) VALUES (?, ?, 'manual')",
            [
                (1, category_b),
                (2, category_b),
                (3, category_a),
                (4, category_a),
            ],
        )
        db.commit()
        return category_a, category_b

    def test_category_tag_hint_mode_defaults_to_never(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config, db = open_temp_database(Path(tmp))
            try:
                self.seed_category_hint_fixture(db)
                category = CategoryEngine(config, db).suggest_category_for_post(5)
            finally:
                db.close()

        self.assertEqual(category.name, "_unmatched")

    def test_category_tag_hint_can_fill_unmatched_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config, db = open_temp_database(Path(tmp))
            try:
                config["viewer"]["tag_hint_category_mode"] = "only_when_unmatched"
                self.seed_category_hint_fixture(db)
                category = CategoryEngine(config, db).suggest_category_for_post(5)
            finally:
                db.close()

        self.assertEqual(category.name, "hint_match")
        self.assertIn("Tag hint selected", category.reason)

    def test_category_tag_hint_does_not_override_rules_in_unmatched_only_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config, db = open_temp_database(Path(tmp))
            try:
                config["viewer"]["tag_hint_category_mode"] = "only_when_unmatched"
                self.seed_category_hint_fixture(db)
                db.add_tag_to_category_rule("hard_match", "hard_tag", "include")
                category = CategoryEngine(config, db).suggest_category_for_post(5)
            finally:
                db.close()

        self.assertEqual(category.name, "hard_match")

    def test_category_tag_hint_can_always_override_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config, db = open_temp_database(Path(tmp))
            try:
                config["viewer"]["tag_hint_category_mode"] = "always"
                self.seed_category_hint_fixture(db)
                db.add_tag_to_category_rule("hard_match", "hard_tag", "include")
                category = CategoryEngine(config, db).suggest_category_for_post(5)
            finally:
                db.close()

        self.assertEqual(category.name, "hint_match")


class ArchivePathStorageTests(unittest.TestCase):
    def test_update_final_file_path_can_store_relative_archive_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            config, db = open_temp_database(base)
            try:
                root = base / "archive"
                final_path = root / "saved" / "100.jpg"
                final_path.parent.mkdir(parents=True)
                final_path.write_bytes(b"image")
                config["archive_paths"] = {
                    "storage_mode": "relative",
                    "local_settings_file": str(base / "local_settings.db"),
                }
                set_archive_root_path(config, root)

                db.execute("INSERT INTO posts (id, status) VALUES (?, 'new')", (100,))
                db.commit()
                db.update_post_final_file_path(100, str(final_path), config=config)
                row = db.get_post_detail(100)
            finally:
                db.close()

        self.assertEqual(row["final_file_path"], str(Path("saved") / "100.jpg"))
        self.assertEqual(resolve_archive_path(config, row["final_file_path"]), final_path)

    def test_migrate_archive_paths_to_relative_with_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            config, db = open_temp_database(base)
            try:
                root = base / "archive"
                final_path = root / "category" / "101.jpg"
                final_path.parent.mkdir(parents=True)
                final_path.write_bytes(b"image")
                config["archive_paths"] = {
                    "storage_mode": "absolute",
                    "local_settings_file": str(base / "local_settings.db"),
                }

                db.execute(
                    """
                    INSERT INTO posts (id, status, final_file_path, final_directory, original_path)
                    VALUES (?, 'saved', ?, ?, ?)
                    """,
                    (101, str(final_path), str(final_path.parent), str(final_path)),
                )
                db.commit()

                report = migrate_archive_paths(
                    db,
                    config,
                    target_mode="relative",
                    archive_root=root,
                    verify_before=True,
                    verify_after=True,
                )
                row = db.get_post_detail(101)
            finally:
                db.close()

        self.assertEqual(report.converted, 1)
        self.assertEqual(report.missing_before, 0)
        self.assertEqual(report.missing_after, 0)
        self.assertEqual(row["final_file_path"], str(Path("category") / "101.jpg"))
        self.assertEqual(row["final_directory"], "category")
        self.assertEqual(row["original_path"], str(Path("category") / "101.jpg"))


if __name__ == "__main__":
    unittest.main()
