# Patch 1.3.129 - i18n Category Tab

This patch migrates the Category tab UI to the i18n system.

## Changed

- `app/gui/category_tab.py`
  - Replaced visible German labels, buttons, table headers, hints and dialogs with `tr(...)` lookups.
  - Added a small local `t(...)` helper for the tab.
  - Translated include-rule and global-condition labels/tooltips.
  - Translated error dialogs and selection warnings.

- `app/i18n/locales/en.json`
  - Added Category tab translation keys.

- `app/i18n/locales/de.json`
  - Added the same keys as English fallback text so the UI stays English-first during the migration.

## Validation

- `python3 -m compileall -q main.py app`
- Patch applied cleanly on top of 1.3.128 and compiled successfully.
