# 1.3.38 - Thumbnail-Reparatur und Scoring-Ausschluss

## Previewer

- Neuer Button `Thumbnail neu laden` in der Preview-Toolbar.
- Rechtsklick auf einen Post zeigt ebenfalls `Thumbnail neu laden`.
- Bei Mehrfachauswahl werden alle ausgewählten Thumbnails neu geladen.
- Das Thumbnail wird mit `force=True` aus Danbooru neu geholt und der Pfad in der DB aktualisiert.
- Der Pixmap-Cache wird für den betroffenen Pfad geleert, damit graue Platzhalter nicht aus dem Cache wieder auftauchen.

## Viewer / Tags

- General- und Meta-Tagzeilen bleiben linksbündig nach Tagname und rechtsbündig nach kompakten Spalten ausgerichtet.
- Filename-Exclude nutzt jetzt feste Symbole statt unterschiedlich breitem `ja`/`nein`:
  - `✖: ✓` = vom Dateinamen ausgeschlossen
  - `✖: –` = nicht ausgeschlossen
- Tags können per Rechtsklick vom Tag-Scoring ausgeschlossen oder wieder eingeschlossen werden.
- Scoring-ausgeschlossene Tags zeigen in der Durchschnittsspalte `⌀☆: aus`.

## Datenbank

- `tag_scores.scoring_excluded INTEGER DEFAULT 0` ergänzt.
- Neue Methoden:
  - `set_tag_scoring_excluded(tag, excluded)`
  - `scoring_excluded_tag_set()`
- Export/Import nimmt `scoring_excluded` bei `tag_scores` mit.

## Konzept

Manueller Score und durchschnittliche Sterne sind getrennte Werte:

- `manual_score`: manuelle Gewichtung des Tags, überschreibt den technischen Tag-Score.
- `average_rating`: Durchschnitt des persönlichen Post-Ratings bei Posts mit diesem Tag.
- `scoring_excluded`: markiert Tags, die für spätere automatische Gewichtung/Dateinamen-Sortierung ignoriert werden sollen.
