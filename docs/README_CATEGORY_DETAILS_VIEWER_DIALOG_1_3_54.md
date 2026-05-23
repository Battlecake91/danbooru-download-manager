# 1_3_54 Kategorie-Details im Viewer

Dieses Patch räumt den bisherigen Kategorie-Dialog im Viewer auf.

## Viewer

Der Button neben der Kategorieauswahl heißt jetzt:

```text
Details
```

Der alte Text `Warum?` war funktional, aber klang wie ein trotziges Kleinkind neben einer ComboBox. Der neue Name beschreibt nüchtern, was der Button macht.

## Dialog

Der Dialog heißt jetzt `Kategorie-Details` und zeigt eine kompaktere Diagnose:

- automatische Gewinner-Kategorie
- aktuell gewählte Kategorie
- Hinweis bei manueller Abweichung
- Kurzübersicht der passenden Kategorien
- relevante Details für Gewinner, manuelle Auswahl und weitere passende Kategorien
- nicht passende Kategorien nur noch als Kurzfassung

Die Textanzeige nutzt jetzt Zeilenumbruch statt horizontaler Scroll-Orgie.

## Technik

Geändert wurden:

```text
app/gui/image_viewer.py
app/core/category_engine.py
```

Die Kategorie-Diagnose liefert intern jetzt pro Kategorie neben dem Detailblock auch eine Kurzfassung. Dadurch kann der Viewer den Dialog deutlich lesbarer aufbauen, ohne die Regelprüfung doppelt zu implementieren.
