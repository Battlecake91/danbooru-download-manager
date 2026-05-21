# Danbooru Manager 1.3.7 - Config-Tab und stilles Umkategorisieren

## Änderung 1: Kein Popup beim Umkategorisieren

Beim Setzen einer Kategorie im Preview erscheint kein Dialogfenster mehr.

Vorher:

```text
Kategorie gesetzt
[OK]
```

Jetzt:

```text
Statusbar: 3 Post(s) → Kategorie Foo
```

Der Review-Workflow wird also nicht mehr von Popup-Fenstern zerhackt. Eine kleine Gnade in dieser klickenden Einöde.

## Änderung 2: Neuer Tab `Konfiguration`

Die GUI hat jetzt einen neuen Tab:

```text
Konfiguration
```

Dort können wichtige Werte bearbeitet werden:

### Pfade / Basis

- `work_dir`
- `database_file`
- `default_output_dir`
- `original_cache_dir`
- `active_thumbnail_dir`
- `saved_thumbnail_dir`
- `rejected_thumbnail_dir`

### Fetch

- `base_url`
- `search_tags`
- `saved_search_extra_tags`
- `use_saved_searches`
- `limit`
- `max_posts_per_query`
- `max_total_posts`

### GUI / Preview

- `gui.thumbnail_size`
- `gui.thumbnail_size_min`
- `gui.thumbnail_size_max`
- `gui.card_width_extra`
- `viewer.default_view`
- `viewer.auto_advance_after_save`
- `viewer.auto_advance_after_reject`

### Workflow

- `workflow.worklist_statuses`
- `workflow.rejected_thumbnail_retention_days`

## Speicherung

Die Werte werden in SQLite gespeichert:

```sql
app_settings(key, value, updated_at)
```

Die Werte werden als JSON gespeichert, damit Listen/Bool/Integer sauber erhalten bleiben.

Beispiel:

```text
gui.thumbnail_size = 340
workflow.worklist_statuses = ["new", "potential", "review", "selected_save"]
```

## Wichtig

`config.yaml` bleibt Import-/Default-Basis.

Der Config-Tab schreibt Runtime-/SQL-Werte in `app_settings`.
Einige Werte wirken sofort, andere erst bei neuem Fetch oder nach Neustart.

## Geänderte Dateien

```text
app/gui/app_window.py
app/gui/preview_window.py
```

## Neue Datei

```text
app/gui/config_tab.py
```
