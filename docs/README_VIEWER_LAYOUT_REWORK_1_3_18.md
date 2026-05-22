# Patch 1.3.18 - Viewer Layout Rework

## Änderungen

- Dateiname-Vorschau-Button im Viewer ausgeblendet.
- Kopfzeile verdichtet:
  - ID
  - farbiges Danbooru-Rating
  - offizieller Score als Zahl
  - Parent-ID
  - bekannte Parent/Child-Posts
  - davon lokal final gespeicherte Posts
- Doppelte obere Rating-/Score-Anzeige aus der Seitenleiste entfernt.
- Parent/Child-Anzeige geändert:
  - Gelber Hinweis erscheint nur, wenn Parent/Child-Posts bekannt sind.
  - Klick auf den Hinweis klappt die Parent/Child-Liste ein/aus.
  - Die Liste bleibt wie bisher nutzbar: Doppelklick lokal/remote öffnen, Rechtsklick für Aktionen.
- Unter dem Bild liegt jetzt eine gemeinsame Steuerzeile:
  - Persönliches Rating
  - `< Vorheriges` / `Position X / Y` / `Nächstes >`
  - Kategorieauswahl
- Artist, Serie/Copyright und Character wurden kompakter gemacht:
  - keine großen leeren Kästen mehr
  - automatische Höhe auf maximal zwei Zeilen
- General/Meta bleiben darunter und skalieren bis maximal sechs Zeilen.
- Die General-Ansicht "nur nicht ausgeschlossene Filename-Tags" bleibt erhalten.

## Geänderte Dateien

- `app/gui/image_viewer.py`
- `app/gui/tag_display.py`
