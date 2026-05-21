# Danbooru Manager 1.3.6 - Kategorie im Preview anzeigen, filtern und setzen

## Neu im Preview

Jede Thumbnail-Karte zeigt jetzt eine Kategorie:

```text
Kategorie: <name> (auto)
Kategorie: <name> (manuell)
```

## Kategoriequellen

### Manuell

Wenn ein Post in `post_categories` eingetragen ist, wird diese Kategorie angezeigt:

```text
Kategorie: Foo (manuell)
```

Manuell hat Vorrang vor automatischen Regeln.

### Auto

Wenn keine manuelle Kategorie gesetzt ist, wird anhand der SQL-Kategorie-Regeln ein Vorschlag berechnet:

```text
Kategorie: Foo (auto)
```

Wenn nichts passt:

```text
Kategorie: _unmatched (auto)
```

## Kategorie-Filter

In der Preview-Toolbar gibt es jetzt:

```text
Kategorie: [Alle Kategorien]
```

Auswählbar sind:

- Alle Kategorien
- `_unmatched / keine Kategorie`
- alle Kategorien aus SQL

## Rechtsklick auf Thumbnail

Neu:

```text
Kategorie setzen
  <Kategorie 1>
  <Kategorie 2>
  ...
```

## Mehrfachauswahl

Wenn mehrere Karten markiert sind und du auf eine davon rechtsklickst:

```text
Kategorie setzen → Kategorie
```

Dann wird die Kategorie für alle ausgewählten Posts gesetzt.

Die Zuweisung wird gespeichert in:

```sql
post_categories.source = 'manual'
```

## Final speichern

Wenn aus dem Preview final gespeichert wird, wird die Karte danach lokal aktualisiert:

- Status: saved
- Kategorie: gespeicherte Kategorie

## Geänderte Dateien

```text
app/gui/preview_window.py
app/gui/thumbnail_grid.py
```

## Hinweis

Der Kategorie-Filter berechnet Auto-Kategorien im geladenen Kandidatenbereich.
Bei aktivem Kategorie-Filter wird intern ein größerer Kandidatenpool geladen und danach lokal gefiltert.

Das ist erstmal pragmatisch. Eine vollständig SQL-native Umsetzung der Kategorie-Regeln wäre möglich, aber deutlich sperriger.
