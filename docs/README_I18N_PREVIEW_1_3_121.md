# 1.3.121 - i18n: Preview / Reviewer

This patch continues the English UI migration for the Preview / Reviewer area.

## Changed

- Migrated `app/gui/preview_window.py` visible UI strings to i18n keys.
- Migrated `app/gui/thumbnail_grid.py` visible card and context-menu strings to i18n keys.
- Added Preview / Reviewer translation keys to:
  - `app/i18n/locales/en.json`
  - `app/i18n/locales/de.json`
- Updated the configuration info text to the current SQLite-only setup.

## Notes

The Preview / Reviewer tab should now be mostly English when `ui.language` is set to `en`.
German fallback strings remain available in `de.json` for later language switching.

Remaining larger UI areas still needing migration include Viewer, Importer, Maintenance, Category and Tag tabs.
