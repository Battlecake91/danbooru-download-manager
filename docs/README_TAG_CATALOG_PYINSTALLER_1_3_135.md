# 1.3.135 Tag catalog, first-run setup and PyInstaller hardening

- Adds a local Danbooru tag catalog table separate from locally used post tags.
- Adds first-run setup for credentials, popular tag import and preview sample post import.
- Sets preview sample post default to `11199825`.
- Adds frozen/path handling so runtime data stays next to the executable in PyInstaller builds.
- Adds a repeatable `DanbooruManager.spec` and `scripts/build_windows.ps1`.
