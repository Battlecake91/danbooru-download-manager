# 1.3.60 - Tag-Optionen direkt in der Tabelle umschalten

Diese Änderung räumt das Kontextmenü im Tag-Tab auf und macht die häufig genutzten Tag-Optionen direkt in der Tag-Liste bedienbar.

## Tag-Tab

Die folgenden Spalten können direkt angeklickt werden:

- `Filename-Exclude`
- `Kat.-Scoring ignoriert`
- `Vorauswahl ignoriert`
- `LLM ignoriert`

Ein Klick toggelt die jeweilige Option für den angeklickten Tag. Sind mehrere Zeilen markiert und der angeklickte Tag gehört zur Auswahl, wird die Option für alle ausgewählten Tags übernommen.

Der Alias-Dialog öffnet sich nur noch per Doppelklick in der Spalte `Alias`. Ein Doppelklick auf andere Spalten öffnet nicht mehr versehentlich die Alias-Eingabe.

Das Kontextmenü im Tag-Tab wurde entschlackt: Die Scoring-/Nutzungsflags werden dort nicht mehr als langer Menüblock angeboten, weil sie jetzt direkt in den Tabellenspalten umgeschaltet werden.

## Viewer

Im Viewer bleiben die schnellen Kontextmenü-Aktionen für Tags erhalten. Zusätzlich gibt es dort ein Menü `Scoring / Nutzung` mit getrennten Aktionen für:

- Kategorie-Hinweis ignorieren / wieder nutzen
- Vorauswahl ignorieren / wieder nutzen
- LLM-Eingabe ignorieren / wieder nutzen
- alle automatischen Bewertungen ignorieren / wieder nutzen

Damit kann man direkt aus dem Review-Flow heraus Tags pflegen, ohne in den Tag-Tab wechseln zu müssen.

## Verhalten

Nach Änderungen wird weiterhin kein vollständiger Tag-Reload ausgelöst. Sichtbare Tabellenzellen werden lokal aktualisiert, damit der Tag-Tab bei großen Datenbanken nicht wieder blockiert.
