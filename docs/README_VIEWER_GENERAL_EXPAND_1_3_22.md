# 1.3.22 - Viewer: General-Tagfeld nutzt freie Fläche

## Änderung

- Das General-Tagfeld ist jetzt vertikal expandierend.
- Es nutzt freie Höhe im rechten Viewer-Panel, statt früh zu scrollen.
- Meta bleibt kompakt mit maximal vier Zeilen.
- Artist / Serie-Copyright / Character bleiben als gemeinsames 3-Spalten-Feld unverändert kompakt.

## Geänderte Dateien

- `app/gui/tag_display.py`

## Hinweis

Die General-Liste behält weiterhin eine Scrollbar, falls mehr Tags vorhanden sind als sichtbar in die verfügbare Panelhöhe passen.
