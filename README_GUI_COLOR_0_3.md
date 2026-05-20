# Danbooru Manager 0.3 - konfigurierbare Statusfarben

Dieser Patch ergänzt konfigurierbare GUI-Farben für Thumbnail-Karten.

## Geänderte Dateien

- `config.example.yaml`
- `app/gui/preview_window.py`
- `app/gui/thumbnail_grid.py`

## Neue Config

In `config.yaml` ergänzen:

```yaml
gui:
  thumbnail_size: 180
  card_width_extra: 60

  status_colors:
    new: "#666666"
    potential: "#2e7d32"
    review: "#f9a825"
    auto_rejected: "#546e7a"
    rejected: "#b71c1c"
    accepted: "#1565c0"
    downloaded: "#8e24aa"
    saved: "#00838f"

  status_border_width:
    default: 2
    marked: 3
    downloaded: 4
```

Posts mit `status = downloaded` werden über `gui.status_colors.downloaded` markiert.
