# Danbooru Manager 0.7 - Bildbetrachter und Viewer-Download

## Neu

- Doppelklick auf Thumbnail öffnet den Bildbetrachter
- `Enter` im Grid öffnet ebenfalls den Bildbetrachter
- `O` im Grid öffnet den Danbooru-Originalpost
- Bildbetrachter lädt bei Bedarf die große Datei in den lokalen Cache
- Tags werden im Viewer angezeigt
- Status kann im Viewer gesetzt werden
- Sternebewertung 1-5 wird gespeichert
- Pfeiltasten blättern durch die aktuell sichtbare Grid-Liste

## Neue Datei

- `app/services/download_service.py`
- `app/gui/image_viewer.py`

## Geänderte Dateien

- `config.example.yaml`
- `app/core/config.py`
- `app/core/database.py`
- `app/gui/preview_window.py`
- `app/gui/thumbnail_grid.py`

## Config-Ergänzung

```yaml
viewer_download_source: "file"

viewer:
  fit_to_window: true
```

Mögliche Werte für `viewer_download_source`:

- `file`: Originaldatei bevorzugen
- `large`: `large_file_url` bevorzugen
- `best`: `file -> large`

## Hotkeys im Viewer

- `←` / `→`: vorheriges/nächstes Bild
- `1` bis `5`: Sternebewertung
- `H`: hohes Potential
- `P`: prüfen
- `S`: zum Speichern vormerken
- `Entf`: ablehnen
- `A`: automatisch aussortieren
- `N`: neu zurücksetzen
- `O`: Originalpost öffnen

## Hinweise

Der Viewer ist noch kein finaler Speicherworkflow. Er lädt nur die große Datei in den lokalen Cache und ermöglicht Review/Bewertung.
Finales Speichern in Kategorieordner kommt im nächsten Schritt.
