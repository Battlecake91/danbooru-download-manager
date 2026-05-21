# Danbooru Manager 1.3.3 - Preview-Statusfilter als Checkboxen

## Problem

Der Preview-Statusfilter war ein Dropdown. Damit konnte immer nur ein Status gleichzeitig angezeigt werden.

Das war unpraktisch für echte Review-Workflows, z. B.:

```text
Ungeprüft + Prüfen + Zum Speichern anzeigen
Abgelehnte ausblenden
```

## Neu

Der Preview-Filter nutzt jetzt Checkboxen:

```text
[Alle]
[Ungeprüft]
[Hohes Potential]
[Prüfen]
[Zum Speichern]
[Automatisch aussortiert]
[Abgelehnt]
[Akzeptiert]
[Bereits bekannt]
[Heruntergeladen/alt]
[Gespeichert]
```

## Standardauswahl

Beim Start sind aktiv:

```text
Ungeprüft
Hohes Potential
Prüfen
Zum Speichern
```

Also genau die normale Arbeitsliste, ohne abgelehnte oder gespeicherte Posts.

## Beispiele

### Normale Review-Liste

```text
Ungeprüft
Hohes Potential
Prüfen
Zum Speichern
```

### Nur finale Kandidaten

```text
Zum Speichern
Hohes Potential
```

### Fehlerkontrolle

```text
Abgelehnt
Automatisch aussortiert
```

### Alles durchsuchen

```text
Alle
```

## Ansicht-Dropdown

Das Ansicht-Dropdown bleibt als Schnellpreset erhalten:

```text
Status-Filter
Arbeitsliste
Gespeichert
Aussortiert
Bekannte/importierte
Alle bekannten Posts
```

Wenn du manuell eine Checkbox änderst, springt die Ansicht automatisch auf:

```text
Status-Filter
```

## Geänderte Datei

```text
app/gui/preview_window.py
```

## Technisch

Die Preview-Abfrage wird jetzt direkt anhand der ausgewählten Statusliste gebaut:

```sql
p.status IN (...)
```

Wenn keine Checkbox aktiv ist:

```sql
1 = 0
```

Also keine Treffer, statt heimlich alles anzuzeigen. Heimliche Magie hatten wir genug, danke.
