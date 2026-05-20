# Danbooru Manager 1.2.1 - Viewer-Query-Fix

## Problem

`Als Query in Preview suchen` aus dem Viewer-Tag-Kontextmenü konnte eine Fenster-/Signal-Lawine auslösen.

Wahrscheinliche Ursache:

- Aktion wurde direkt aus dem `QMenu`/`QAction`-Kontext heraus ausgeführt
- Preview wurde sofort manipuliert
- ComboBox-Signale feuerten mehrere Reloads
- Qt bekam Eventloop-Schluckauf und öffnete massenhaft Fenster

Qt kann aus einem einfachen Rechtsklick halt auch eine Oper machen. Niemand hat darum gebeten.

## Fix

### Viewer

- Tag-Kontextmenü nutzt jetzt `popup()` statt blockierendem `exec()`
- Menü wird als `self._tag_context_menu` gehalten
- alle Aktionen laufen per `QTimer.singleShot(0, ...)`
- Query-Request wird verzögert emittiert

### PreviewWindow

- `query_requested` wird nicht mehr direkt angewendet
- Query wird als Pending Query gespeichert
- Anwendung per `QTimer.singleShot(0, ...)`
- ComboBox-Signale werden beim Setzen blockiert
- danach genau ein `reload_posts()`

## Geänderte Dateien

- `app/gui/image_viewer.py`
- `app/gui/preview_window.py`

## Test

Im Viewer:

1. Tag rechts anklicken
2. `Als Query in Preview suchen`
3. Es sollte genau die Preview aktualisiert werden
4. Es dürfen keine neuen Viewer-Fenster massenhaft entstehen
