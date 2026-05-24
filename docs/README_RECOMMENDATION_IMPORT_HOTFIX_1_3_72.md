# 1.3.72 Recommendation-Import-Hotfix

Fix für den GUI-Start nach 1.3.71.

## Problem

`PreviewWindow` erzeugte eine Instanz von `RecommendationEngine`, importierte die Klasse aber nicht.
Dadurch konnte die GUI beim Start mit folgendem Fehler abbrechen:

```text
name 'RecommendationEngine' is not defined
```

## Änderung

- `app/gui/preview_window.py` importiert jetzt `RecommendationEngine` aus `app.core.recommendation_engine`.
- Keine Änderung an Datenbank, Scoring-Logik oder UI-Verhalten.

## Prüfung

```bash
python3 -m compileall app/gui/preview_window.py app/core/recommendation_engine.py
```
