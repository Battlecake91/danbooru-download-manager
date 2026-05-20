# Danbooru Manager 0.7.1 - Viewer-Hotkey-Fix

## Problem

Im Bildbetrachter wurden Pfeiltasten teilweise von `QTextEdit`, Buttons oder ScrollArea abgefangen.
Dadurch kam `ImageViewerWindow.keyPressEvent()` nicht zuverlässig an.

## Lösung

Der Viewer nutzt jetzt `QShortcut` mit `Qt.WindowShortcut`.

Dadurch funktionieren diese Hotkeys unabhängig vom aktuell fokussierten Widget:

- `←` vorheriges Bild
- `→` nächstes Bild
- `1` bis `5` Sterne
- `H` hohes Potential
- `P` prüfen
- `S` zum Speichern vormerken
- `A` automatisch aussortieren
- `Entf` ablehnen
- `N` neu zurücksetzen
- `O` Originalpost öffnen

## Geänderte Datei

- `app/gui/image_viewer.py`
