# 1.3.63 - Kategorie-Tab: Regelbedienung geglättet

Dieser Patch macht den Kategorie-Tab verständlicher, ohne das Datenmodell oder die vorhandene Regellogik zu ändern.

## Änderungen

- Aus `ODER-Gruppe` wird in der Oberfläche `Regel-Zeile` bzw. `Regel`.
- Aus `Globale Bedingung` wird `Immer-Bedingung`.
- Hilfetexte und Platzhalter wurden auf die tatsächliche Bedienung ausgerichtet:
  - Tags ohne `-` müssen vorhanden sein.
  - Tags mit `-` schließen aus.
  - Mehrere Regel-Zeilen sind Alternativen.
  - Immer-Bedingungen gelten zusätzlich für jede Regel-Zeile.
- Regel-Zeilen können jetzt innerhalb der Kategorie hoch/runter geschoben werden.
- Immer-Bedingungen können ebenfalls hoch/runter geschoben werden.
- Speichern erfolgt weiterhin automatisch nach Änderungen an Regel-/Bedingungszeilen.

## Nicht geändert

- Keine Änderung am Datenbankschema.
- Keine Änderung an der eigentlichen Kategorieentscheidung.
- Keine Änderung an der Bedeutung bestehender Regeln.

## Beispiel

Regel-Zeilen:

```text
maid apron -comic
school_uniform ribbon
```

bedeutet:

```text
(maid UND apron UND NICHT comic) ODER (school_uniform UND ribbon)
```

Immer-Bedingung:

```text
solo -multiple_girls
```

wird zusätzlich auf jede Regel-Zeile angewendet.
