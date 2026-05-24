# Patch 1.3.125 - Maintenance / DB i18n

This patch migrates the Maintenance / DB tab to the i18n system.

## Changed

- `app/gui/maintenance_tab.py`
  - translated database maintenance labels, buttons and dialogs
  - translated quality audit controls, result labels and table headers
  - translated audit notes and repair messages
  - translated the database size report
  - switched internal audit status labels from German to English
- `app/i18n/locales/en.json`
  - added Maintenance / DB keys
- `app/i18n/locales/de.json`
  - added the same keys as English fallbacks to keep the UI English-first during migration

## Validation

- `python3 -m compileall -q main.py app`
- JSON locale files load successfully
- Patch applies cleanly on top of 1.3.124
