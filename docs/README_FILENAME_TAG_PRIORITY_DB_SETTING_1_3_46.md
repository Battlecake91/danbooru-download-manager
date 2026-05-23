# 1.3.46 - Dateinamen-Tag-Priorisierung liest DB-Option

## Problem

Die Option `filename.sort_tags_by_average_rating` war im Config-Tab sichtbar,
wurde aber beim Dateinamenbau nicht zuverlässig berücksichtigt. Ursache: Der
`FilenameBuilder` bekam beim Start eine verschachtelte Runtime-Konfiguration und
las daraus weiter, auch wenn die Option später in SQLite `app_settings` geändert
wurde.

Dadurch sah die UI korrekt aus, aber `%general%` blieb in der Praxis oft bei der
alten alphabetischen Reihenfolge.

## Änderung

`FilenameBuilder.prioritize_filename_tags()` liest jetzt zuerst direkt aus
SQLite:

```text
filename.sort_tags_by_average_rating
```

Nur wenn kein DB-Wert vorhanden ist, wird auf die alte verschachtelte Config
zurückgefallen.

## Ergebnis

Nach Aktivierung unter:

```text
Konfiguration -> Dateiname -> Tag-Reihenfolge -> Nach Tag-Scoring priorisieren
```

werden Dateinamen-Tags nach Score/Durchschnitt priorisiert, ohne App-Neustart
und ohne einen neu erzeugten Service zu brauchen.
