# 1_3_48 Kategorie-Regelgruppen

Dieses Patch-ZIP enthält nur die geänderten Dateien.

## Kategorie-Tab

- Kategorien haben links eine sichtbare Priorität.
- Mit `↑ Kategorie` und `↓ Kategorie` kann die Reihenfolge verändert werden.
- Bei `first` gewinnt weiterhin die erste passende Kategorie.

## Neue Regelgruppen-Logik

Eine Zeile in der Tabelle ist eine Gruppe.

- Innerhalb einer Gruppe gilt `UND`.
- Tags mit `-` sind Ausschlüsse.
- Mehrere Gruppen sind `ODER`.

Beispiel:

```text
tag1 tag2 -tag3
tag4 tag5
```

Bedeutet:

```text
(tag1 UND tag2 UND NICHT tag3) ODER (tag4 UND tag5)
```

## Bedienung

- Gruppen können direkt in der Tabelle bearbeitet werden.
- Doppelklick auf den Ausdruck, bearbeiten, Enter.
- Neue Gruppen können unten per Ausdruck hinzugefügt werden.
- Gruppen können gelöscht oder per Pfeil verschoben werden.

## Kompatibilität

Vorhandene alte Regeln werden beim Anzeigen in Regelgruppen übersetzt:

- alte `include`-Regeln werden als einzelne ODER-Gruppen angezeigt.
- alte `include_group_N`-Regeln werden als UND-Gruppen angezeigt.
- alte globale `exclude`-Regeln werden in die betroffenen Gruppen übernommen.

Nach dem Speichern schreibt die App die neuen Regeltypen:

```text
group_0_include
group_0_exclude
group_1_include
group_1_exclude
```

## Matching

Kategorie-Vorschlag und Preview-Kategorisierung unterstützen die neue Regelgruppen-Logik.
