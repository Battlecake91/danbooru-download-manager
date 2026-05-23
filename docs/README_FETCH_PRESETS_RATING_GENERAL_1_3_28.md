# 1.3.28 - Fetch-Presets, Rating-Filter und General-Rating

## Viewer / Preview

- Danbooru-Rating `g` / `general` wird jetzt als `general` angezeigt.
- Sortierung nach Danbooru-Rating berücksichtigt jetzt `general -> safe -> questionable -> explicit`.

## Fetch-Tab

- Die letzten Fetch-Eingaben bleiben erhalten.
- Manuelle Tag-Eingabe bekommt Autovervollständigung aus lokal bekannten Tags.
- Rating-Filter sind dreistufig:
  - leer = ignorieren
  - Haken = einschließen
  - Minus = ausschließen
- Unterstützte Ratings: General, Safe, Questionable, Explicit.
- Die Rating-Filter werden bei manueller Suche direkt an die Query angehängt.
- Bei Saved Searches werden die Rating-Filter als `saved_search_extra_tags` angehängt.
- Fetch-Presets können im Fetch-Tab geladen, bearbeitet, gespeichert und gelöscht werden.
- Presets speichern Quelle, Eingaben, Rating-Filter und Limits.
- Während Fetch läuft, erscheint ein endloser Fortschrittsbalken.
- Der Wechsel zur Preview passiert automatisch erst nach erfolgreichem Fetch.

## Datenbank

Neue Tabelle:

```sql
fetch_presets(name TEXT PRIMARY KEY, payload TEXT, updated_at TEXT)
```

Neue Hilfsfunktionen:

- `get_app_setting()` / `set_app_setting()`
- `save_fetch_preset()` / `list_fetch_presets()` / `get_fetch_preset()` / `delete_fetch_preset()`
- `suggest_tags()`

## Export/Import

- Fetch-Presets werden jetzt in den Konfigurations-Export aufgenommen.
- Fetch-Presets werden beim Import wiederhergestellt.
