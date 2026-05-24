# Patch 1.3.130 - Config tab English cleanup

This patch continues the English UI migration for the Configuration tab.

## Changed

- Translated visible Configuration tab labels, buttons, hints, dialog titles, and dialog messages to English.
- Translated LLM payload debug dialogs and last-fetch payload summaries.
- Translated preview sample post controls and status messages.
- Translated configuration export/import/default-reset dialogs.
- Removed remaining German comments in `config_tab.py` that were likely to show up in repository-wide German-word scans.

## Notes

The tab still uses the existing i18n infrastructure for already migrated shared labels and the language selector. This patch mainly removes the remaining German hard-coded text from the large configuration form and its helper dialogs.

## Validation

```bash
python3 -m compileall -q main.py app
python3 - <<'PY'
import json
for path in ["app/i18n/locales/en.json", "app/i18n/locales/de.json"]:
    json.load(open(path, encoding="utf-8"))
print("locale json ok")
PY
```
