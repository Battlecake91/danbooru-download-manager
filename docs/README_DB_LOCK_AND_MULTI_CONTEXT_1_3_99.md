# Patch 1.3.99 - SQLite-Lock-Wartezeit und Mehrfachauswahl im Preview-Kontextmenü

## Problem

Nach einem Fetch konnte ein direkt gestarteter weiterer Fetch mit `sqlite3.OperationalError: database is locked` abbrechen, besonders wenn der Previewer bereits offen war und parallel Daten las oder Karten aktualisierte.

Außerdem wirkte das Kontextmenü im Preview bei Mehrfachauswahl nicht konsistent: einige Aktionen liefen nur auf dem per Rechtsklick angeklickten Post statt auf der gesamten markierten Auswahl.

## Änderung

- SQLite-Verbindungen verwenden jetzt `timeout=30.0` und `PRAGMA busy_timeout = 30000`.
- `Database.execute()`, `executemany()` und `commit()` wiederholen kurze Lock-Situationen mit gestaffelten Wartezeiten.
- Der Previewer zeigt bei einem verbleibenden SQLite-Lock eine verständliche Meldung statt nur hart zu scheitern.
- Rechtsklick auf einen bereits ausgewählten Preview-Post erhält die Mehrfachauswahl.
- Rechtsklick auf einen nicht ausgewählten Preview-Post wählt diesen Post einzeln aus.
- Kontextmenü-Aktionen für Status, Kategorie, Thumbnail neu laden und Final speichern verwenden jetzt die gesamte Auswahl, wenn der angeklickte Post Teil der Mehrfachauswahl ist.

## Erwartetes Verhalten

Ein direkt aufeinanderfolgender Fetch sollte nicht mehr wegen kurzer Preview-/Worker-DB-Zugriffe abbrechen. Falls die DB wirklich länger blockiert ist, zeigt der Previewer eine Busy-Meldung und plant einen Reload nach.

Im Preview-Kontextmenü gelten Aktionen jetzt wie erwartet für alle markierten Posts, solange der Rechtsklick auf einen der markierten Posts erfolgt.
