from __future__ import annotations

import unittest
from importlib.util import find_spec

from app.services.update_service import (
    app_executable_names,
    compare_versions,
    find_release_asset,
    packaged_update_requirement_message,
    updater_executable_names,
)


class ImportAndPackagingGuardTests(unittest.TestCase):
    @unittest.skipIf(find_spec("requests") is None, "requests is not installed in this Python runtime")
    def test_gui_import_is_not_required_for_core_service_imports(self) -> None:
        from app.services.post_import_service import split_tags

        self.assertEqual(split_tags("alpha  beta\tgamma"), ["alpha", "beta", "gamma"])

    @unittest.skipIf(find_spec("requests") is None, "requests is not installed in this Python runtime")
    def test_fetch_exclude_checks_all_tag_fields(self) -> None:
        from app.services.post_import_service import PostImportService

        post = {
            "tag_string_general": "blue_eyes solo",
            "tag_string_character": "character_name",
            "tag_string_copyright": "series_name",
        }

        self.assertTrue(PostImportService.post_matches_fetch_exclude(post, {"solo"}))
        self.assertFalse(PostImportService.post_matches_fetch_exclude(post, {"missing"}))

    @unittest.skipIf(find_spec("requests") is None, "requests is not installed in this Python runtime")
    def test_resolution_filter_treats_unknown_dimensions_as_reject_when_limit_is_active(self) -> None:
        from app.services.post_import_service import PostImportService

        service = object.__new__(PostImportService)
        service.config = {"resolution_filters": {"min_width": 1000}}

        self.assertFalse(service.post_matches_resolution_filter({"image_width": 0, "image_height": 800}))
        self.assertTrue(service.post_matches_resolution_filter({"image_width": 1200, "image_height": 800}))

    @unittest.skipIf(find_spec("requests") is None, "requests is not installed in this Python runtime")
    def test_stable_order_is_added_only_when_missing(self) -> None:
        from app.danbooru.api import ensure_stable_order

        self.assertEqual(ensure_stable_order("rating:g"), "rating:g order:id_desc")
        self.assertEqual(ensure_stable_order("rating:g order:score"), "rating:g order:score")

    @unittest.skipIf(find_spec("requests") is None, "requests is not installed in this Python runtime")
    def test_saved_search_query_builder_filters_labels_and_adds_extra_tags(self) -> None:
        from app.danbooru.api import build_search_queries

        class FakeApi:
            def get_saved_searches(self):
                return [
                    {"query": "tag_a", "labels": ["wanted"]},
                    {"query": "tag_b", "labels": ["other"]},
                ]

        queries = build_search_queries(
            {
                "use_saved_searches": True,
                "saved_search_labels": ["wanted"],
                "saved_search_queries": [],
                "saved_search_extra_tags": "rating:g",
            },
            FakeApi(),
        )

        self.assertEqual(queries, ["tag_a rating:g"])

    def test_release_asset_selection_prefers_windows_zip_for_windows(self) -> None:
        asset = find_release_asset(
            {
                "assets": [
                    {
                        "name": "DanbooruManager_1.0_linux.zip",
                        "browser_download_url": "https://example.invalid/linux.zip",
                        "size": 1,
                    },
                    {
                        "name": "DanbooruManager_1.0_win64.zip",
                        "browser_download_url": "https://example.invalid/win.zip",
                        "size": 1,
                    },
                ]
            },
            platform="win32",
        )

        self.assertEqual(asset.name, "DanbooruManager_1.0_win64.zip")

    def test_release_asset_selection_prefers_linux_zip_for_linux(self) -> None:
        asset = find_release_asset(
            {
                "assets": [
                    {
                        "name": "DanbooruManager_1.0_win64.zip",
                        "browser_download_url": "https://example.invalid/win.zip",
                        "size": 1,
                    },
                    {
                        "name": "DanbooruManager_1.0_linux_x86_64.zip",
                        "browser_download_url": "https://example.invalid/linux.zip",
                        "size": 1,
                    },
                ]
            },
            platform="linux",
        )

        self.assertEqual(asset.name, "DanbooruManager_1.0_linux_x86_64.zip")

    def test_packaged_update_names_are_platform_specific(self) -> None:
        self.assertEqual(app_executable_names("win32"), ["DanbooruManager.exe"])
        self.assertIn("DanbooruManager", app_executable_names("linux"))
        self.assertEqual(updater_executable_names("win32")[0], "DanbooruManagerUpdater.exe")
        self.assertEqual(updater_executable_names("linux")[0], "DanbooruManagerUpdater")

    def test_packaged_update_message_uses_platform_names(self) -> None:
        linux_message = packaged_update_requirement_message("linux")
        windows_message = packaged_update_requirement_message("win32")

        self.assertIn("DanbooruManagerUpdater", linux_message)
        self.assertNotIn(".exe", linux_message)
        self.assertIn("DanbooruManagerUpdater.exe", windows_message)

    def test_version_comparison_handles_v_prefix(self) -> None:
        self.assertGreater(compare_versions("v1.3.194", "1.3.193"), 0)
        self.assertEqual(compare_versions("1.3.193", "v1.3.193"), 0)


if __name__ == "__main__":
    unittest.main()
