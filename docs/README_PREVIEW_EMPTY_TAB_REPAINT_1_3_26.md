# 1.3.26 - Preview-Tab zeichnet leeren Zustand sauber

## Problem
Wenn vom Tab **Fetch / Suche** zu **Preview / Review** gewechselt wurde, bevor jemals Posts gefetcht wurden, konnte der Preview-Tab optisch noch den Inhalt des Fetch-Tabs anzeigen.

Ursache war ein leerer Preview-Bereich ohne sichtbares, deckendes Widget. Je nach Qt-Style/Plattform wurde dadurch der zuletzt gezeichnete Tab-Inhalt nicht sauber übermalt.

## Änderung
- `ThumbnailGrid` zeichnet jetzt bei leerer Post-Liste einen expliziten Hinweis-Kasten.
- ScrollArea, Viewport und Container werden deckend/opaque gesetzt.
- Beim Aktivieren des Preview-Tabs wird der leere Zustand aktiv gezeichnet.
- Bei echten Posts verschwindet der Hinweis automatisch.

## Geänderte Dateien
- `app/gui/app_window.py`
- `app/gui/preview_window.py`
- `app/gui/thumbnail_grid.py`
