# 1.3.86 - Konfigurationsseite mit Tabs und Thumbnail-Presets

## Ziel

Die Konfigurationsseite wurde in mehrere Reiter aufgeteilt, damit Basiswerte, Fetch, GUI, Filename, Scoring und Expert/Raw nicht mehr in einer einzigen langen Scroll-Wand stehen.

## Neue Reiter

- Basis
  - Pfade
  - Workflow
- Fetch
  - Danbooru-Zugangsdaten
  - Default-Suchwerte
  - Fetch-Limits
- GUI
  - Thumbnail-Größe
  - Viewer-Verhalten
- Filename
  - Dateinamensschema
  - Tag-Anzahl, Hash-Länge, maximale Länge
- Scoring
  - Scoring- und LLM-Tag-Privacy-Optionen
- Custom (Expert)
  - Raw app_settings

## Saved Searches

Der alte globale Schalter `use_saved_searches` wird nicht mehr als Checkbox angeboten.

Saved Searches gehören im neuen Workflow in Fetch-Presets, nicht mehr als globaler Konfig-Schalter in die Basis-Konfiguration. Beim Speichern der Konfiguration wird `use_saved_searches` daher auf `false` gesetzt, damit alte globale Werte keine Presets überschreiben.

Die Default-Felder `search_tags` und `saved_search_extra_tags` bleiben erhalten, dienen aber nur noch als Default-/Legacy-Werte.

## GUI / Thumbnail-Presets

Im GUI-Reiter gibt es jetzt Presets:

- Small
- Medium
- Large
- Huge
- Custom

Nur bei `Custom` wird die direkte Eingabe `thumbnail_size` eingeblendet. Bei den Presets wird der Wert automatisch gesetzt.

Zusätzlich gibt es eine kompakte Vorschau, die ungefähr zeigt, wie groß eine Thumbnail-Karte im Preview-Fenster ausfallen wird. Die Vorschau berücksichtigt `thumbnail_size` und `card_width_extra`.

## Technischer Hinweis

Es wurde nur die Konfigurationsoberfläche geändert. Fetch-Presets, Kategorien, Dateiname-Logik und Scoring-Logik bleiben unverändert.
