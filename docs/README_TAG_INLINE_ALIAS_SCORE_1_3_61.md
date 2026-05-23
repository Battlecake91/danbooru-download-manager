# 1.3.61 – Tag-Tabelle: Alias und manueller Score direkt editieren

Diese Änderung macht die Tag-Pflege im Tag-Tab direkter und räumt das Kontextmenü weiter auf.

## Neu

- Die Spalte `Alias` ist direkt in der Tabelle editierbar.
- Die Spalte `Manueller Score` ist direkt in der Tabelle editierbar.
- Leerer manueller Score entfernt den manuellen Override und schreibt `NULL` in die Datenbank.
- Komma und Punkt werden bei manuellen Scores akzeptiert.
- Gültiger Score-Bereich bleibt `-10` bis `+10`.
- Nach dem Editieren wird lokal aktualisiert, ohne vollständiges `reload_tags()`.

## Weiterhin direkt klickbar

- `Filename-Exclude`
- `Kat.-Scoring ignoriert`
- `Vorauswahl ignoriert`
- `LLM ignoriert`

## Kontextmenü im Tag-Tab

Das Tag-Tab-Kontextmenü wurde weiter entschlackt:

- Einzelnes `Alias bearbeiten` wurde entfernt, weil die Alias-Spalte direkt editierbar ist.
- `Manuellen Score bearbeiten` wurde entfernt, weil die Score-Spalte direkt editierbar ist.
- Bulk-Alias-Aktionen für mehrere markierte Tags bleiben erhalten.
- `Ähnliche Tags suchen/bearbeiten…` bleibt erhalten.

## Hinweis

Die Viewer-Kontextmenüs bleiben für schnelle Tag-Aktionen erhalten. Die direkte Tabellenbearbeitung betrifft nur den Tag-Tab.
