# 1.3.35 - Preview: manuelle Filter-Anwendung und stabilere Ladeanzeige

Dieses Patch-ZIP enthält nur die geänderten Dateien.

## Änderungen

### Preview-Limit

- Standard-Limit ist jetzt 100 statt 500.
- Der Wert kommt aus `gui.preview_limit`, falls vorhanden.

### Limit-Feld

- Enter lädt neu.
- Reiner Fokusverlust lädt nicht mehr neu.
- Wertänderung zeigt nur noch einen Hinweis, dass `Neu laden` oder Enter nötig ist.

### Filter

- Status-Checkboxen laden nicht mehr automatisch neu.
- `Alle`-Status-Checkbox lädt nicht mehr automatisch neu.
- Kategorie-Filter lädt nicht mehr automatisch neu.
- Sortierung lädt nicht mehr automatisch neu.
- Suchfeld lädt weiterhin mit Enter neu.
- Button `Neu laden` lädt wie bisher.
- Nur die Auswahl `Ansicht` triggert weiterhin sofort ein Neuladen.

### Preview-Ladeanzeige

- Der Preview-Tab lädt beim App-Start nicht mehr im versteckten Tab vor.
- Beim Wechsel auf Preview wird zuerst eine deckende Ladefläche angezeigt.
- Der eigentliche Reload startet verzögert per Timer, damit Qt vorher wirklich neu zeichnen kann.
- Nach dem Thumbnail-Aufbau wird das Grid explizit sichtbar geschaltet und neu gezeichnet.

