# 1.3.79 Viewer: Dateiname-/Zielpfad-Preview in Fußzeile

## Problem

Der Viewer konnte durch lange Zielpfad- oder Dateiname-Vorschauen eine sehr große minimale Breite bekommen. Auf breiten Monitoren führte das dazu, dass das Fenster unnötig über große Teile der Bildschirmbreite gezogen wurde.

## Änderung

Die Zielpfad- und Dateiname-Vorschau wurde aus der rechten Seitenleiste entfernt und in eine Fußzeile unter den gesamten Viewer verschoben.

Dadurch beeinflussen lange Dateinamen nicht mehr die Mindestbreite der rechten Seitenleiste.

## Details

- `Zielpfad` steht nun unten unter Bildbereich und Seitenleiste.
- Die Dateiname-Vorschau bleibt über den bestehenden Button ein-/ausklappbar.
- Zielpfad und Dateiname-Vorschau bleiben markierbar/kopierbar.
- Beide Labels sind umbrechbar und erzwingen keine große minimale Fensterbreite mehr.
- Keine Änderung an Dateiname-Logik oder finalem Speichern.

## Geänderte Dateien

- `app/gui/image_viewer.py`
