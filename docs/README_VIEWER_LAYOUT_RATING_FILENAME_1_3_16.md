# 1.3.16 - Viewer-Layout, Rating-Sterne, Dateiname ohne unknown

## Dateiname

- Leere Platzhalter werden nicht mehr mit `unknown` gefüllt.
- Wenn `%artist%` / `%artists%` leer ist und der Copyright-Tag `original` vorhanden ist, wird `original` als Artist-Platzhalter verwendet.
- Wenn durch leere Platzhalter kein sinnvoller Name entsteht, fällt der Builder auf `<post_id><ext>` zurück.

## Tags in der Datenbank

Beim Fetch werden alle von Danbooru gelieferten Tag-Gruppen gespeichert:

- `tag_string_artist` -> `post_tags.tag_type = artist`
- `tag_string_character` -> `post_tags.tag_type = character`
- `tag_string_copyright` -> `post_tags.tag_type = copyright`
- `tag_string_general` -> `post_tags.tag_type = general`
- `tag_string_meta` -> `post_tags.tag_type = meta`

## Viewer

- Dateiname-Vorschau ist nicht mehr dauerhaft sichtbar.
- Neuer Button `Dateiname-Vorschau anzeigen` klappt die Vorschau bei Bedarf aus.
- Neue Kopfzeile: `ID - Rating`.
- Neue Fußzeile: `Rating - Position`.
- Danbooru-Rating wird farbig dargestellt:
  - safe: grün
  - questionable: gelb
  - explizit: rot
- Score wird als 5-Sterne-Skala relativ zum höchsten Score in der aktuellen Viewer-Liste dargestellt.
- Persönliches Rating ist ein eigenes Sternfeld mit halben Sternschritten.
- Klick links/rechts in einen Stern setzt halbe bzw. volle Werte.
- Die persönlichen Sterne werden in `post_reviews.stars` gespeichert.

## Aufgeräumte Statusaktionen

Entfernt aus Viewer-Buttons und Hotkeys:

- Auto raus
- Prüfen
- Speichern vormerken

Im Viewer bleiben:

- `High Potential [H]`
- `Ablehnen [Entf]`
- `Neu [N]`
- `Final speichern (F)`

Im Preview-Kontextmenü wurden die unnötigen Statusaktionen ebenfalls entfernt.
