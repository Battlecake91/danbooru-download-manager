# Danbooru Manager 0.9 - Manuelle Kategorieauswahl im Viewer

## Neu

- Kategorie-Dropdown im Viewer
- vorgeschlagene Kategorie wird vorausgewählt
- manuelle Kategorieauswahl möglich
- Zielpfad-Vorschau aktualisiert sich beim Wechsel
- final speichern nutzt die gewählte Kategorie
- `post_categories.source` wird gesetzt:
  - `auto`, wenn Vorschlag genutzt wurde
  - `manual`, wenn manuell abweichend gewählt wurde
- Button `Zielordner öffnen`
- optionales automatisches Weiterspringen nach Speichern/Ablehnen

## Geänderte Dateien

- `config.example.yaml`
- `app/core/config.py`
- `app/core/category_engine.py`
- `app/services/final_save_service.py`
- `app/gui/image_viewer.py`

## Config-Ergänzung

```yaml
viewer:
  auto_advance_after_save: true
  auto_advance_after_reject: true
```

## Nutzung

Im Viewer:

1. Kategorie im Dropdown prüfen oder ändern
2. Zielpfad-Vorschau ansehen
3. `F` drücken oder `Final speichern (F)` klicken

Wenn `auto_advance_after_save: true`, springt der Viewer danach direkt zum nächsten Bild.
