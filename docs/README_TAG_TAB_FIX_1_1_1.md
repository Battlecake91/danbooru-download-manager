# Danbooru Manager 1.1.1 - Tag-Tab-Fix

## Problem

Der Tag-Tab konnte weiterhin abstürzen oder falsch arbeiten, besonders bei:

- Alias bearbeiten
- Tag zu Kategorie hinzufügen
- Filename-Exclude setzen

Hauptursache:

Die Rechtsklick-Aktion hat den angeklickten Tag erkannt, aber spätere Aktionen haben wieder `selected_tags()` gelesen.
Wenn die Zeile nicht vorher sauber selektiert war, war die Auswahl leer oder falsch.

Ja, GUI-Zustand als Wahrheit zu benutzen war natürlich wieder eine kleine Falle aus der Hölle.

## Fix

- Kontextmenü friert die Tag-Liste beim Öffnen ein
- Aktionen benutzen diese eingefrorene Liste
- Rechtsklick auf eine nicht selektierte Zeile selektiert diese Zeile
- `QInputDialog.getText()` nutzt jetzt die robuste Positionssignatur
- Fehler werden nach `tag_tab_error.log` geschrieben
- vorhandene doppelte Kategorie-Regeln werden vor dem Unique-Index bereinigt

## Geänderte Dateien

- `app/core/database.py`
- `app/gui/tag_tab.py`

## Wenn es trotzdem kracht

Bitte die Datei senden:

```text
tag_tab_error.log
```

Die liegt im Arbeitsverzeichnis, aus dem du die App startest.
