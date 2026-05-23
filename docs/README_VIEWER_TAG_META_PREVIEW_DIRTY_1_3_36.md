# 1_3_36 - Viewer-Tagmetadaten und Preview-Reload nur bei Bedarf

## Geändert

### Viewer: Tagmetadaten

General- und Meta-Tags zeigen jetzt zusätzliche Informationen direkt in der Liste:

- Score
- Filename-Exclude: Ja/Nein
- durchschnittliche persönliche Sterne als `Ø Sterne: x.x/10`

Artist, Serie/Copyright und Character bleiben kompakt ohne Zusatzspalten, damit die obere Tagaufteilung nicht wieder kaputtgeht.

### Datenbank

Neue Hilfsfunktion:

- `Database.fetch_tag_metadata(tags)`

Sie sammelt pro Tag:

- manuellen bzw. berechneten Score
- Filename-Exclude-Status
- durchschnittliches persönliches Rating aus `post_reviews.stars`

### Previewer

Der Preview-Tab lädt beim Tabwechsel nicht mehr pauschal neu.

Ein Reload passiert nur noch, wenn:

- noch nie geladen wurde
- keine Thumbnails vorhanden sind
- Filter/Sortierung/Limit geändert wurden
- bereits ein Reload läuft oder vorgemerkt ist

Wenn gültige Thumbnails vorhanden sind, wird nur das Grid wieder eingeblendet und neu gezeichnet.

### Vorbereitung für Dateinamen-Sortierung

Neue Default-Konfiguration:

```json
filename.sort_tags_by_average_rating = false
```

Noch ohne aktive Dateinamenlogik. Der Schalter ist nur als vorbereitete Konfigoption für die spätere Sortierung/Reduktion unwichtiger Tags gedacht.
