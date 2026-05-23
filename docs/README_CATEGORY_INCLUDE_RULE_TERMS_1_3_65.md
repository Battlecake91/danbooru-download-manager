# 1.3.65 – Kategorie-Tab: ODER-Gruppe zu Include-Regel umbenannt

## Änderung

Im Kategorie-Tab wurde der Begriff **ODER-Gruppe** in **Include-Regel** umbenannt.

**Globale Bedingung** bleibt unverändert.

## Hintergrund

Die frühere Bezeichnung war grundsätzlich verständlich, aber **Include-Regel** beschreibt besser, dass diese Zeile eine positive Regel mit optionalen Ausschlüssen enthält.

Mehrere Include-Regeln bleiben weiterhin Alternativen zueinander:

```text
Include-Regel 1: maid apron -comic
Include-Regel 2: school_uniform necktie
```

entspricht weiterhin:

```text
(maid AND apron AND NOT comic) OR (school_uniform AND necktie)
```

Globale Bedingungen werden weiterhin zusätzlich auf jede Include-Regel angewendet.

## Technisch

- Keine Änderung am Datenbankschema.
- Keine Änderung an der Kategorieentscheidung.
- Nur UI-Texte, Tooltips und Platzhalter angepasst.
- Hoch/Runter-Schieben aus 1.3.64 bleibt erhalten.
