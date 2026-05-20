# Danbooru Manager 0.5 - Thumbnail-Größe in der GUI

Dieser Patch ergänzt einen Thumbnail-Größenregler in der Toolbar.

## Neu

- Toolbar-Feld `Thumbnail: ... px`
- Größe live änderbar
- Startwert aus `config.yaml`
- Min/Max/Schrittweite aus `config.yaml`
- Kartenlayout passt sich automatisch an die Fensterbreite an

## Geänderte Dateien

- `config.example.yaml`
- `app/core/config.py`
- `app/gui/preview_window.py`
- `app/gui/thumbnail_grid.py`

## Config-Ergänzung

```yaml
gui:
  thumbnail_size: 280
  thumbnail_size_min: 120
  thumbnail_size_max: 600
  thumbnail_size_step: 20
  card_width_extra: 80
```

Für 4K sind meistens Werte zwischen 280 und 420 angenehm.
