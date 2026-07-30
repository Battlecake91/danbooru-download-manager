from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts.make_release import (
    APP_NAME,
    create_release_zip,
    executable_name,
    platform_release_suffix,
    pyinstaller_data_args,
    pyinstaller_data_separator,
)


class ReleasePackagingTests(unittest.TestCase):
    def test_platform_release_suffixes_are_asset_search_friendly(self) -> None:
        self.assertEqual(platform_release_suffix("win32"), "win64")
        self.assertTrue(platform_release_suffix("linux").startswith("linux_"))
        self.assertIn(platform_release_suffix("darwin").split("_")[0], {"macos"})

    def test_executable_name_uses_exe_only_on_windows(self) -> None:
        self.assertEqual(executable_name("DanbooruManager", "win32"), "DanbooruManager.exe")
        self.assertEqual(executable_name("DanbooruManager", "linux"), "DanbooruManager")

    def test_pyinstaller_data_separator_is_platform_specific(self) -> None:
        self.assertEqual(pyinstaller_data_separator("win32"), ";")
        self.assertEqual(pyinstaller_data_separator("linux"), ":")

    def test_pyinstaller_data_args_include_locales_and_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app" / "i18n" / "locales").mkdir(parents=True)
            (root / "assets").mkdir()

            args = pyinstaller_data_args(root, platform="linux")

        joined = "\n".join(args)
        self.assertIn("app/i18n/locales", joined)
        self.assertIn("assets", joined)
        self.assertIn(":", joined)

    def test_release_zip_name_contains_platform_and_bundle_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = root / "build" / "release_payload" / APP_NAME
            payload.mkdir(parents=True)
            (payload / executable_name(APP_NAME, "linux")).write_text("binary", encoding="utf-8")

            with redirect_stdout(StringIO()):
                zip_path = create_release_zip(
                    root,
                    payload,
                    "9.9.9",
                    onefile=True,
                    platform="linux",
                )

        self.assertEqual(zip_path.name, f"{APP_NAME}_9.9.9_linux_x86_64_onefile.zip")


if __name__ == "__main__":
    unittest.main()
