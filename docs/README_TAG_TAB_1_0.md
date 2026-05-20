# Danbooru Manager 1.0 - Tag-Tab

## Neu

Die GUI hat jetzt zwei Tabs:

- Preview / Review
- Tags

## Tag-Tab Funktionen

- alle bekannten Tags anzeigen
- nach Tag suchen
- nach Tag-Typ filtern
- Statistiken:
  - Anzahl Posts
  - offene Posts
  - gespeicherte Posts
  - abgelehnte Posts
  - Alias
  - Filename-Exclude
  - manueller Score
  - berechneter Score
  - Durchschnittsbewertung

## Rechtsklick auf Tags

- zu Kategorie hinzufügen:
  - include
  - exclude
- vom Dateinamen ausschließen
- Filename-Ausschluss entfernen
- Alias bearbeiten
- manuellen Score bearbeiten
- Tag kopieren
- als Suchtext übernehmen

## Geänderte Dateien

- `app/core/database.py`
- `app/gui/main_window.py`

## Neue Dateien

- `app/gui/app_window.py`
- `app/gui/tag_tab.py`

## Hinweis

Der Tag-Tab schreibt Änderungen direkt in die SQLite-Datenbank.

Achtung: Kategorie-Regeln werden aktuell in der DB geändert. Wenn du später die YAML-Config als führend behalten willst,
brauchen wir noch einen Export oder einen Config-Editor. Ja, natürlich gibt es jetzt zwei Wahrheiten, weil Software gerne Drama erzeugt.
