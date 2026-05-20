# Danbooru Manager 1.2 - Interaktive Tags im Viewer

## Neu

Die Tags im Bildbetrachter sind jetzt nicht mehr nur Text, sondern eine auswählbare Liste.

## Bedienung

Im Viewer:

1. Einen oder mehrere Tags markieren
2. Rechtsklick
3. Aktion wählen

## Aktionen

- zu Kategorie hinzufügen
  - include
  - exclude
- vom Dateinamen ausschließen
- Filename-Ausschluss entfernen
- Alias bearbeiten
- manuellen Score bearbeiten
- Tags kopieren
- als Query in Zwischenablage
- als Query in Preview suchen

## Query aus Viewer

Die Aktion `Als Query in Preview suchen` setzt im Preview-Fenster:

- Ansicht: `Alle bekannten Posts`
- Status: `Alle`
- Suchfeld: ausgewählte Tags
- lädt die Preview neu

## Wichtig

Die Viewer-Tag-Aktionen lösen keinen vollständigen Tag-Tab-Reload aus.
Filename-Exclude-Änderungen aktualisieren nur den Zielpfad im Viewer.

## Geänderte Dateien

- `app/gui/image_viewer.py`
- `app/gui/preview_window.py`

## Hinweis

Damit ist die Tag-Pflege direkt im Review-Workflow möglich.
Der nächste saubere Schritt wäre, die gleiche Aktionslogik als gemeinsame Komponente für Viewer und Tag-Tab zu extrahieren.
