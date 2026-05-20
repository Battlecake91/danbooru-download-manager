# Danbooru Manager 1.0.1 - Kein Grid-Rebuild nach Entscheidung

## Problem

Bei großen Arbeitslisten, z. B. 465 neuen Bildern, hing die GUI kurz nach jeder Entscheidung im Viewer.
Ursache: `PreviewWindow` hat nach jedem `status_changed` ein vollständiges `reload_posts()` ausgeführt.
Dadurch wurden hunderte Thumbnail-Karten neu gebaut.

## Lösung

- Viewer-Statusänderungen lösen keinen kompletten Preview-Reload mehr aus.
- Die betroffene Karte wird im Grid nur lokal aktualisiert.
- Terminale Status werden ausgegraut:
  - `rejected`
  - `auto_rejected`
  - `already_known`
  - `saved`
- Beim nächsten manuellen Reload oder Filterwechsel verschwinden diese Posts aus der Arbeitsliste.

## Geänderte Dateien

- `app/gui/preview_window.py`
- `app/gui/thumbnail_grid.py`

## Verhalten

Während einer Review-Session bleibt die Liste stabil.
Das ist schneller und verhindert, dass die UI ständig springt.

Manuell auf `Neu laden` klicken entfernt erledigte Posts aus der Arbeitsliste.
