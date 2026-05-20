# Danbooru Manager 1.1 - SQL-Konfiguration als führende Quelle

## Ziel

`config.yaml` ist ab jetzt Import-/Default-Basis.

Die laufende Konfiguration liegt in SQLite:

- Kategorien
- Kategorie-Regeln
- Filename-Excludes
- LLM-Aliase
- Tag-Scores

Ja, endlich weniger YAML-Voodoo. Fast schade, es war so schön chaotisch.

## Wichtige Änderung

`sync_static_config()` ist jetzt nicht-destruktiv:

Vorher:

```text
YAML importieren → category_rules löschen → Regeln neu aus YAML schreiben
```

Jetzt:

```text
YAML importieren → fehlende/aktualisierte Kategorien übernehmen → fehlende Regeln ergänzen
```

GUI-Änderungen bleiben also erhalten.

## Kategorie-Engine

`CategoryEngine` liest Kategorien und Regeln jetzt aus SQLite, nicht mehr aus `config.yaml`.

## Dateinamen

`FilenameBuilder` nutzt `filename_excluded_tags` aus SQLite.

Die YAML-Liste bleibt nur als Default/Import-Fallback.

## Neuer Tab

Die GUI hat jetzt:

```text
Kategorien
```

Dort können Kategorien und Regeln bearbeitet werden:

- Kategorie hinzufügen
- Kategorie löschen
- Name ändern
- Folder Name ändern
- Output Path ändern
- Hotkey ändern
- Sort Order ändern
- Include-Regel hinzufügen
- Exclude-Regel hinzufügen
- Regel löschen

## Tag-Tab Crash-Fix

Der Tag-Tab wurde robuster gemacht:

- Aktionen sind mit Fehlerdialog abgesichert
- Alias bearbeiten zeigt Fehler statt Absturz
- Kategorie hinzufügen zeigt Fehler statt Absturz
- Score bearbeiten nutzt `QInputDialog.getDouble()`
- Auswahl wird sauber zeilenbasiert gelesen

## Geänderte Dateien

- `app/core/database.py`
- `app/core/category_engine.py`
- `app/core/filename_builder.py`
- `app/gui/app_window.py`
- `app/gui/tag_tab.py`

## Neue Datei

- `app/gui/category_tab.py`

## Hinweis

Wenn du Kategorien bisher nur in YAML gepflegt hast:

1. App starten
2. `sync_static_config()` importiert sie in SQL
3. Danach besser über GUI/SQL weiterpflegen

YAML bleibt für technische Startwerte sinnvoll, aber nicht mehr als einzige Wahrheit.
