# 1.3.17 - Viewer kompakter, Status-Chips und Filename-General-Filter

## Viewer-Layout

- Das persönliche Rating liegt jetzt direkt unter dem Bild.
- Die Kategorieauswahl liegt ebenfalls unter dem Bild neben dem persönlichen Rating.
- Die Navigation wurde nach unten verlegt:
  - `< Vorheriges`
  - große Positionsanzeige
  - `Nächstes >`
- Der offizielle Danbooru-Score wird nur noch als Zahl in den allgemeinen Informationen angezeigt.
- Die Sterne bleiben ausschließlich für das persönliche Rating.

## Statusanzeige

- Status wird jetzt als farbige Chip-Leiste dargestellt.
- Jeder Status-Chip hat eine farbige Umrandung.
- Der aktive Status ist gefüllt und hebt sich deutlich ab.

## Tags

- Artist, Serie/Copyright und Character werden nebeneinander angezeigt.
- Tag-Listen skalieren ihre Höhe anhand der enthaltenen Zeilen bis zu einer sinnvollen Obergrenze.
- General und Meta stehen darunter.
- Für General-Tags gibt es eine neue Ansicht:
  - `General: nur nicht ausgeschlossene Filename-Tags anzeigen`
  - Damit bleiben nur Tags sichtbar, die aktuell nicht im Filename-Exclude stehen.
  - Das hilft beim weiteren Aussortieren unnötiger Filename-Tags.

## Hinweise

- Rechtsklick-Aktionen auf Tags bleiben erhalten.
- Auswahl-Toggle per erneutem Linksklick bleibt erhalten.
- Filename-Exclude-Änderungen aktualisieren den General-Filter sofort.
