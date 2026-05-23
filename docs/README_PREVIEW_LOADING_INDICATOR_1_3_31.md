# 1.3.31 - Preview-Ladeanzeige beim Tabwechsel

## Geändert

- Das Patch-ZIP enthält ab jetzt nur noch die geänderten Dateien.
- Der Preview-Tab zeigt beim Laden einen zentralen Ladehinweis mit endlosem Fortschrittsbalken.
- Beim Wechsel von Fetch zu Preview wird sofort ein deckendes Ladefeld angezeigt, damit nicht mehr der Fetch-Tab optisch stehen bleibt.
- Während `reload_posts()` läuft, wird `Lädt Preview…` angezeigt.
- Der leere Preview-Zustand bleibt erhalten, wenn nach dem Laden keine Posts zur aktuellen Ansicht passen.

## Betroffene Dateien

- `app/gui/preview_window.py`
- `app/gui/thumbnail_grid.py`
