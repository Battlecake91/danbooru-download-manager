# Danbooru Manager 0.8 - Finaler Speicherworkflow

## Neu

- Kategorie-Vorschlag anhand der Config-Regeln
- Dateiname wird aus Post-ID, Tags, Hash und Extension gebaut
- finaler Zielpfad wird im Viewer angezeigt
- `F` im Viewer speichert final
- Button `Final speichern (F)` im Viewer
- Datei wird nach Kategorie-Zielpfad kopiert
- DB-Felder werden gesetzt:
  - `final_file_path`
  - `final_directory`
  - `saved_at`
  - `status = saved`
- `post_categories` wird gepflegt

## Neue Dateien

- `app/core/category_engine.py`
- `app/core/filename_builder.py`
- `app/services/final_save_service.py`

## Geänderte Dateien

- `config.example.yaml`
- `app/core/config.py`
- `app/gui/image_viewer.py`

## Config-Ergänzung

```yaml
default_output_dir: "./danbooru_saved"

filename:
  pattern: "{id}_{tags}_{hash}{ext}"
  max_length: 180
  tags_count: 8
  hash_length: 8
  excluded_tags:
    - highres
    - absurdres
    - commentary_request
```

Kategorien können eigene Zielpfade haben:

```yaml
categories:
  - name: "example"
    folder_name: "example"
    output_path: "D:/Bilder/Danbooru/example"
    hotkey: "E"
    include:
      - some_tag
    exclude:
      - unwanted_tag
```

Wenn `output_path` leer ist, wird gespeichert nach:

```text
default_output_dir / folder_name
```

## Viewer-Hotkey

```text
F = final speichern
```

## Hinweis

Dieser Patch nutzt automatisch die erste passende Kategorie.
Manuelle Kategorieauswahl im Viewer kommt im nächsten Schritt.
