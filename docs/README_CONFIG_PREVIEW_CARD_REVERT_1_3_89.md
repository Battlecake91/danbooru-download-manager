# 1.3.89 - Previewer-Layout wiederhergestellt

Dieser Patch repariert den Fehler aus 1.3.88.

## Problem

1.3.88 hat die gemeinsame `ThumbnailCard` geändert, um die Konfig-Vorschau anzupassen. Dadurch wurde aber auch das echte Preview-Fenster verändert.

## Fix

- `ThumbnailCard` ist wieder auf das vorherige Previewer-Layout zurückgesetzt.
- Das echte Preview-Fenster sieht damit wieder aus wie vor 1.3.88.
- Die Konfig-Vorschau nutzt weiterhin die echte `ThumbnailCard`, verändert sie aber nicht mehr global.
- Keine Datenbankänderung.
- Keine Änderung an Fetch, Import oder Scoring.

## Hinweis

Falls die Konfig-Vorschau später noch genauer angepasst werden soll, muss das über eine separate Vorschau-Komponente passieren. Die globale `ThumbnailCard` darf dafür nicht mehr umgebaut werden.
