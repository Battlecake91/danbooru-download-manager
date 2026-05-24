# Patch 1.3.98 - Preview wieder direkt nutzbar, Fetch-Fix

## Problem

Patch 1.3.95 hat den Preview/Reviewer zu aggressiv lazy geladen. Dadurch war der Tab
zwar startzeitfreundlich, aber beim normalen Arbeiten nervig, weil gespeicherte Posts
nicht direkt ohne Fetch gesucht werden konnten.

Außerdem fehlte in `database.py` die Hilfsfunktion `normalize_categories()`. Dadurch
scheiterte der Fetch-Worker beim Synchronisieren der statischen Konfiguration mit:

```text
NameError: name 'normalize_categories' is not defined
```

## Änderung

- `Preview / Review` wird wieder beim Programmstart erzeugt.
- Die schweren Admin-Tabs bleiben lazy: Importer, Tags, Kategorien, Konfiguration.
- Die Preview-Suche nutzt jetzt dieselbe asynchrone Tag-Completion wie der Fetch-Tab.
- Die alte synchrone Preview-Abfrage `db.suggest_tags(limit=2500)` beim Start wurde entfernt.
- `normalize_categories()` ist wieder in `app/core/database.py` vorhanden.

## Erwartung

Der Start sollte weiterhin schnell bleiben, weil die Preview keine große Tagliste mehr
beim Erzeugen lädt. Gleichzeitig ist der Preview/Reviewer sofort verfügbar, um gespeicherte
oder bekannte Posts zu suchen, ohne vorher einen Fetch auszuführen.

## Test

```bash
python main.py --gui --debug-startup
```

Erwartete Startup-Marker:

```text
AppWindow: begin
FetchTab: begin
FetchTab: end
PreviewTab: begin
PreviewTab: end
AppWindow: shown-ready
```

Danach:

1. Programm starten.
2. Direkt `Preview / Review` öffnen.
3. Ansicht z. B. auf `Gespeichert` oder `Alle bekannten Posts` stellen.
4. Suchen ohne vorherigen Fetch testen.
5. Fetch starten und prüfen, dass kein `normalize_categories`-Fehler mehr kommt.
