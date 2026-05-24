# Patch 1.3.120 - Fetch tab i18n continuation

This patch continues the English UI migration after the SQLite-only configuration cleanup.

## Changed

- Migrated the visible Fetch tab UI strings to the i18n catalog.
- Added English and German translation keys for:
  - Fetch tab description
  - preset controls
  - source selection
  - manual query controls
  - saved-search controls
  - rating filter hint
  - fetch limits and tooltips
  - progress labels
  - preset dialogs
  - fetch validation and error dialogs
  - fetch summary labels
  - worker log messages
- Kept the translated German fallback in `de.json` so switching the UI language back to German still works.

## Notes

The Fetch tab is now mostly detached from hard-coded German UI text. Some internal comments remain German and do not affect the user interface.

The next useful targets are the Preview/Reviewer and thumbnail card UI, because they still contain the largest amount of visible German text.
