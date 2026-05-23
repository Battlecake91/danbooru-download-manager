# 1.3.30 - Preview-Suche: Autovervollständigung und exakte Tag-Suche

## Änderungen

- Die Suche im Previewer verwendet jetzt dasselbe Token-basierte Autocomplete wie der Fetch-Tab.
- Autovervollständigung funktioniert für mehrere Tags innerhalb derselben Suchzeile.
- Tags werden per Leerzeichen getrennt.
- Ein führendes `-` bleibt beim Einfügen einer Vervollständigung erhalten.

Beispiele:

```text
brown_eyes red_
```

kann zu:

```text
brown_eyes red_hair
```

werden.

```text
brown_eyes -red_
```

kann zu:

```text
brown_eyes -red_hair
```

werden.

## Exakte Tag-Suche

Die Preview-Suche sucht Tags jetzt exakt.

```text
eyes
```

findet nur Posts mit dem Tag `eyes`.

Es findet nicht mehr automatisch Posts mit Tags wie:

```text
red_eyes
blue_eyes
closed_eyes
```

Ausschlüsse sind ebenfalls exakt:

```text
brown_eyes -red_hair
```

bedeutet:

- `brown_eyes` muss als Tag vorhanden sein
- `red_hair` darf als Tag nicht vorhanden sein

## Pfadsuche

Pfadsuche bleibt möglich, wenn der Suchbegriff wie ein Pfad oder Dateiname aussieht, also z. B. `/`, `\` oder `.` enthält.
