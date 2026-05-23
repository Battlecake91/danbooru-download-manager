# 1.3.34 - Preview-Tab Ladeanzeige/Repaint robuster

## Problem
Beim Wechsel vom Fetch-Tab auf den Preview-Tab konnte weiterhin der alte Fetch-Inhalt sichtbar bleiben. Gleichzeitig meldete die Statuszeile bereits geladene Thumbnails, obwohl die Preview-Fläche noch nicht korrekt neu gezeichnet war.

## Änderung
- Preview verwendet jetzt einen `QStackedWidget` zwischen Ladefläche und Thumbnail-Grid.
- Beim Aktivieren des Preview-Tabs wird immer sofort die zentrale Ladefläche angezeigt.
- Der eigentliche Reload wird danach per `QTimer.singleShot(0, ...)` gestartet, damit Qt zuerst die Ladefläche zeichnen kann.
- Nach Abschluss des Thumbnail-Aufbaus wird explizit auf das Grid zurückgeschaltet und ein Repaint erzwungen.

## Enthaltene Dateien
- `app/gui/preview_window.py`
