# Danbooru Manager 0.4 - Arbeitsliste und Gesamtviewer

Dieser Patch ändert die Preview-Logik grundlegend.

## Neu

- Standardansicht ist eine Arbeitsliste.
- Die Arbeitsliste zeigt nur offene Posts:
  - `new`
  - `potential`
  - `review`
  - `selected_save`
- Erledigte Posts verschwinden aus der Arbeitsliste:
  - `auto_rejected`
  - `rejected`
  - `already_known`
  - `saved`
- Es gibt zusätzlich Ansichten:
  - Arbeitsliste
  - Gespeichert
  - Aussortiert
  - Bekannte/importierte
  - Alle bekannten Posts
- Kontextmenü wurde erweitert:
  - Originalpost öffnen
  - Originalpost-Link kopieren
  - Post-ID kopieren
  - Tags kopieren
  - Zum Speichern vormerken
  - Als gespeichert markieren
  - Bereits bekannt
- Originalpost-Link wird dynamisch erzeugt:
  - `base_url.rstrip("/") + "/posts/" + post_id`
- DB-Migration ergänzt:
  - `original_cache_path`
  - `final_file_path`
  - `final_directory`
  - `rejected_thumbnail_path`
  - `selected_at`
  - `rejected_at`
  - `already_known_at`

## Geänderte Dateien

- `config.example.yaml`
- `app/core/config.py`
- `app/core/paths.py`
- `app/core/database.py`
- `app/services/history_import.py`
- `app/services/post_import_service.py`
- `app/gui/preview_window.py`
- `app/gui/thumbnail_grid.py`

## Config-Ergänzung

In `config.yaml` ergänzen oder aus `config.example.yaml` übernehmen:

```yaml
active_thumbnail_dir: "./danbooru_manager_data/thumbnails/active"
saved_thumbnail_dir: "./danbooru_manager_data/thumbnails/saved"
rejected_thumbnail_dir: "./danbooru_manager_data/thumbnails/rejected"

workflow:
  worklist_statuses:
    - new
    - potential
    - review
    - selected_save

  rejected_thumbnail_retention_days: 7

viewer:
  default_view: "worklist"
  allow_all_status_view: true
  open_original_post_in_browser: true
```

## Wichtig

Beim Start führt `initialize_schema()` automatisch die Migration aus.

Alte History-Einträge mit `status = downloaded` werden auf `already_known` umgestellt,
wenn sie aus `downloaded_history_import` stammen und keinen finalen Pfad haben.
