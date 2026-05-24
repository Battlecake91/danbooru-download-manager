# 1.3.73 - Preview-Status-Bulk und Fetch-Fortschritt

## Ziel

Diese Version reduziert Wartezeiten im Previewer bei Statusänderungen vieler markierter Thumbnails und macht den Fetch-Fortschritt sichtbar.

## Previewer

Statusänderungen über Mehrfachauswahl werden jetzt gebündelt verarbeitet:

- eine DB-Bulk-Operation für alle ausgewählten Posts
- ein Commit statt ein Commit pro Karte
- UI-Aktualisierung der betroffenen Karten in einem eingefrorenen Update-Block
- nur noch eine Sammelmeldung in der Statusleiste bei mehreren Posts

Das betrifft besonders Aktionen wie:

- High Potential
- Ablehnen
- Als gespeichert markieren
- Bereits bekannt
- Neu zurücksetzen

Einzelne Karten funktionieren weiterhin wie vorher.

## Fetcher

Der Fetcher zeigt jetzt während des Laufs konkrete Fortschrittsdaten:

- Query X / X
- Post X / X
- Bekannt: X
- Neu: X
- Thumbnails: X
- aktuelle Query im Tooltip

Der Ladebalken ist nach der Query-Vorbereitung determiniert und läuft anhand der geplanten maximalen Post-Anzahl.

## Technische Änderung

`PostImportService` kann jetzt einen Progress-Callback bekommen und sendet `FetchProgress`-Objekte an die GUI.

`Database.set_post_statuses(...)` erlaubt gebündelte Statusänderungen mit einem gemeinsamen Commit.

