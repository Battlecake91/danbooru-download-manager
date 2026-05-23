# 1_3_49 - Kategorie-Priorität statt Gruppen-Priorität

Dieses Patch korrigiert die Bedienlogik im Kategorie-Tab.

## Änderungen

- Die Kategorie-Reihenfolge links ist jetzt eindeutig die Priorität.
- Buttons heißen jetzt:
  - `↑ Priorität erhöhen`
  - `↓ Priorität senken`
- Kategorie-Sortierung wird beim Verschieben robust als dichte Reihenfolge `1..N` gespeichert.
- Das Feld `Priorität` in den Kategorie-Details ist nur noch Anzeige und wird über die Liste links gesteuert.
- Die Gruppen-Hoch/Runter-Buttons wurden entfernt, weil Gruppen innerhalb einer Kategorie OR-Zweige sind und ihre Reihenfolge für die Entscheidung nicht relevant ist.
- Hinweise im Tab wurden angepasst:
  - Kategorien: oben gewinnt.
  - Gruppen: OR-Zweige, Reihenfolge egal.

## Logik

Eine Kategorie passt, wenn mindestens eine Regelgruppe passt.

Eine Regelgruppe passt, wenn:

- alle positiven Tags vorhanden sind
- keine negativen Tags vorhanden sind

Mehrere Kategorien können passen. Dann entscheidet die Reihenfolge der Kategorienliste links.
