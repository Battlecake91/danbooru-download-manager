# 1_3_50 Kategorie-Regeln: Treffer-Gruppen + globale Bedingungen

Dieses Patch überarbeitet die Kategorie-Regeln so, dass sie verständlicher und näher an der gewünschten Logik sind.

## Kategorien-Reihenfolge

Die Reihenfolge links ist die Kategorie-Reihenfolge. Oben gewinnt.

Die Buttons heißen jetzt:

- `↑ Kategorie hoch`
- `↓ Kategorie runter`

Das sichtbare Wort „Priorität“ wurde aus der Bedienoberfläche entfernt. Die Reihenfolge ergibt sich aus der Position in der Liste, weil Menschen Listen lesen können. Manchmal sogar Software.

## Treffer-Gruppen

Eine Treffer-Gruppe ist ein ODER-Zweig.

Beispiel:

```text
tag1 tag2 -tag3
tag4 tag5
```

Bedeutet:

```text
(tag1 UND tag2 UND NICHT tag3) ODER (tag4 UND tag5)
```

## Globale Bedingungen

Globale Bedingungen werden zusätzlich auf jede Treffer-Gruppe angewendet.

Beispiel:

```text
Treffer-Gruppe 1: tag1 tag2 -tag3
Treffer-Gruppe 2: tag4 tag5
Globale Bedingung 1: tag6
Globale Bedingung 2: -tag7
```

Bedeutet:

```text
(tag1 UND tag2 UND NICHT tag3 UND tag6 UND NICHT tag7)
ODER
(tag4 UND tag5 UND tag6 UND NICHT tag7)
```

## Datenmodell

Neue Rule-Typen:

```text
group_0_include
group_0_exclude
global_0_include
global_0_exclude
```

Alte Regeln bleiben kompatibel:

- `include` wird als eigene Treffer-Gruppe interpretiert
- `include_group_N` wird als alte UND-Gruppe interpretiert
- `exclude` wird als globale Ausschluss-Bedingung interpretiert

Beim Speichern werden die Regeln im neuen Format geschrieben.
