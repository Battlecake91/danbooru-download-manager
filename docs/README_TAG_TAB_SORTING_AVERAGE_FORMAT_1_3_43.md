# 1.3.43 - Tag-Tab: Sortierung und Ø-Sterne-Format

## Geändert

### Ø Sterne

Im Tag-Tab werden die durchschnittlichen Sterne jetzt auf eine Nachkommastelle gerundet.

Beispiel:

```text
7.333333333333 -> 7.3
8.0             -> 8
```

Damit bleibt die Übersicht lesbar. Die interne Datenbankgenauigkeit bleibt unverändert.

### Sortierung per Spaltenkopf

Im Tag-Tab kann jetzt per Klick auf die Tabellenüberschrift sortiert werden, zum Beispiel:

- Tag
- Typ
- Posts
- Offen
- Gespeichert
- Abgelehnt
- Alias
- Filename-Exclude
- Manueller Score
- Berechneter Score
- Ø Sterne

Ein zweiter Klick auf dieselbe Spalte dreht die Sortierrichtung um.

### Numerische Sortierung

Zahlen werden jetzt als Zahlen sortiert und nicht als Text.

Also:

```text
9 < 100
```

und nicht dieser übliche GUI-Unfug:

```text
100 < 9
```

