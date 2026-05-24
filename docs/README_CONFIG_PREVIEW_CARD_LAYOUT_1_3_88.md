# 1.3.88 Config-Vorschau: Preview-Kartenlayout angeglichen

Die Konfigurationsvorschau nutzt weiterhin die echte `ThumbnailCard`, aber das Kartenlayout wurde an die Darstellung im Previewer angepasst:

- Thumbnail links.
- ID, Rating, Score, Parent, Status, Vorauswahl, Kategorie, Verwandtschaft und Pfad rechts neben dem Thumbnail.
- Tags bleiben unterhalb des oberen Kartenbereichs.
- Die Konfigurationsvorschau zeigt dadurch nicht mehr eine andere vertikale Anordnung als der Previewer.

Geändert wurde nur die Kartenstruktur in `app/gui/thumbnail_grid.py`. Die Konfig-Seite nutzt diese Karte unverändert weiter.
