from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.category_engine import build_category_match_groups, build_category_rule_set
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


if __name__ == "__main__":
    unittest.main()
