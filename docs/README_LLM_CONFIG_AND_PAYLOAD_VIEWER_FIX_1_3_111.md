# Patch 1.3.111 - LLM Config und Payload-Viewer Fix

## Problem

Nach Patch 1.3.110 konnte der Konfigurations-Tab beim Lazy-Laden bei `Lade Konfiguration...` hängen beziehungsweise abbrechen.
Grund: Die UI verwendete `llm_run_after_fetch_checkbox` und `llm_skip_scored_checkbox`, diese Widgets wurden aber im finalen Stand nicht zuverlässig angelegt.

Außerdem konnte `Letzte LLM-Payloads` ohne verwertbaren Inhalt erscheinen, wenn nach einem Fetch keine Payload erzeugt wurde oder die LLM-Batch-Vorbereitung deaktiviert war.

## Änderungen

### `app/gui/config_tab.py`

- `llm_run_after_fetch_checkbox` wird wieder korrekt erstellt.
- `llm_skip_scored_checkbox` wird wieder korrekt erstellt.
- Beide Checkboxen werden vor dem Einfügen ins FormLayout angelegt.
- Tooltips ergänzt.

### `app/services/llm_batch_service.py`

- `llm.last_fetch_payloads` und `llm.last_fetch_payload_summary` werden jetzt immer gemeinsam geschrieben.
- Auch bei deaktivierter LLM-Batch-Vorbereitung oder leerer Kandidatenliste wird `last_fetch_payloads` sauber auf `[]` gesetzt.
- Dadurch zeigt der Viewer keine veralteten Payloads mehr an.

### `app/gui/preview_window.py`

- Wenn keine Payloads gespeichert sind, aber eine Summary existiert, zeigt `Letzte LLM-Payloads` jetzt die Summary an:
  - Eingangsposts
  - Kandidaten
  - übersprungene Posts
  - Batches
  - Payloads
  - Hinweis/Grund

## Test

```bash
python -m compileall app
```

Der Compile-Test läuft ohne Syntaxfehler durch.
