# 1.3.91 Preview-Kartenanzeige konfigurierbar

## Ziel

Die Preview-Karte soll in der GUI-Konfiguration nicht nur in der Größe, sondern auch im sichtbaren Inhalt konfigurierbar sein.

## Neu

Im Konfig-Tab **GUI** gibt es nun den Bereich **Preview-Karten-Inhalte**.

Dort können einzeln ein- und ausgeschaltet werden:

- ID
- Rating
- Score
- Parent / Child-Hinweis
- Status
- Vorauswahl
- Kategorie
- Pfad
- Tags insgesamt
- General-Tags
- Character-Tags
- Meta-Tags
- Copyright/Serie-Tags
- Artist-Tags

Die Vorschau im GUI-Tab nutzt diese Optionen sofort und zeigt die Karte entsprechend an.

## Rating-Anzeige

Das Rating wird in Preview-Karten nicht mehr als Rohwert wie `Rating: g` angezeigt, sondern ausgeschrieben und farbig:

- `g` -> `General`
- `s` -> `Sensitive`
- `q` -> `Questionable`
- `e` -> `Explicit`

## Technisch

Die Einstellungen werden unter `gui.preview_card.*` in `app_settings` gespeichert.

`ThumbnailCard` liest die Optionen aus `config["gui"]["preview_card"]` und blendet die entsprechenden Labels aus bzw. filtert die Tagtypen.

Für die Tagtyp-Filter liefert die Datenbank jetzt zusätzlich zu `tags` auch:

- `tags_general`
- `tags_character`
- `tags_copyright`
- `tags_artist`
- `tags_meta`

Das betrifft `fetch_preview_posts()` und `get_post_detail()`.
