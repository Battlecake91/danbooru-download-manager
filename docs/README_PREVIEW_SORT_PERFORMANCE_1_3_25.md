# 1.3.25 - Previewer: Sortierung und Performance

## Sortierung

Der Previewer hat jetzt eine eigene Sortierauswahl in der Toolbar.

Verfügbare Sortierungen:

- Post-ID: neueste zuerst
- Post-ID: älteste zuerst
- Danbooru-Score: hoch → niedrig
- Danbooru-Score: niedrig → hoch
- Persönliches Rating: hoch → niedrig
- Persönliches Rating: niedrig → hoch
- Danbooru-Rating: safe → explicit
- Status
- Kategorie
- Zuletzt gespeichert
- Zuletzt gesehen
- Auflösung: groß → klein
- Dateigröße: groß → klein

Die meisten Sortierungen laufen direkt in SQLite. Kategorie-Sortierung läuft nach der Kategorie-Vorschlagslogik in Python, weil automatische Kategorie-Vorschläge nicht direkt als Datenbankfeld existieren.

## Previewer-Performance

Der Thumbnail-Grid rendert nicht mehr alle Karten in einem einzigen UI-Block.

Neu:

- Karten werden in Batches aufgebaut.
- Default: 40 Karten pro Batch.
- Einstellbar über `gui.preview_render_batch_size`.
- Thumbnail-Pixmaps werden gecacht.
- Der Cache berücksichtigt Pfad, Thumbnail-Größe und Änderungszeit der Datei.
- Beim Relayout werden Repaints reduziert.
- Datenbank-Indizes für häufige Sortierfelder wurden ergänzt.

Das löst keine perfekte Virtualisierung wie ein echtes Model/View-Grid, reduziert aber die schlimmsten Hänger bei >100 Einträgen deutlich. Ein kompletter Umbau auf echtes `QAbstractItemModel` / `QListView` wäre später möglich, aber das hier ist der pragmatische Schritt, bevor Qt wieder mit dem Gesicht zuerst in den Teppich fällt.

## Geänderte Dateien

- `app/gui/preview_window.py`
- `app/gui/thumbnail_grid.py`
- `app/core/config.py`
- `app/core/database.py`
