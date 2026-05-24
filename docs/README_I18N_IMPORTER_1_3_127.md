# Patch 1.3.127 - Importer i18n

This patch migrates the Importer tab and the existing-file import service messages to the i18n system.

## Changed

- `app/gui/import_tab.py`
  - Visible Importer labels, buttons, warnings, dialogs, progress text and summary text now use `tr(...)`.
  - Worker log/error messages now use translation keys.

- `app/services/existing_file_import_service.py`
  - Progress messages and user-visible runtime errors are now translated.
  - Import, repair and rename status lines are now emitted in English by default.

- `app/i18n/locales/en.json`
  - Added Importer keys.

- `app/i18n/locales/de.json`
  - Added matching fallback keys, currently English to keep the application English-first.

## Verification

```bash
python3 -m compileall -q main.py app
```

Both locale JSON files were parsed successfully.
