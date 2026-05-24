# Patch 1.3.104 - Kategorie-Details direkt im Previewer

## Ziel

Der Previewer kann jetzt die Kategorie-Entscheidung direkt anzeigen, ohne dass der Post zuerst im Bildbetrachter geöffnet werden muss.

## Änderungen

### `app/gui/preview_window.py`

- Neuer Button in der oberen Previewer-Aktionsleiste: `Kategorie-Details`.
- Der Button öffnet den bestehenden Kategorie-Details-Dialog für den aktuell ausgewählten Post.
- Bei Mehrfachauswahl wird der aktuelle Post verwendet und eine kurze Statusmeldung angezeigt.
- Der sichtbare Kategorie-Vorschlag der Preview-Karte wird an den Diagnosebericht übergeben, damit auch abweichende manuelle/angezeigte Kategorien sauber berücksichtigt werden.
- Falls SQLite gerade gesperrt ist, erscheint eine verständliche Meldung statt eines Tracebacks.

### `app/gui/thumbnail_grid.py`

- Neues Signal `category_details_requested`.
- Kontextmenü der Preview-Karten hat jetzt `Kategorie-Details anzeigen`.
- Der Rechtsklick-Kontext kann damit dieselbe Kategorie-Diagnose öffnen wie der Toolbar-Button.

## Bedienung

- Einen Post im Previewer markieren.
- `Kategorie-Details` klicken.
- Alternativ Rechtsklick auf eine Preview-Karte → `Kategorie-Details anzeigen`.

Bei Mehrfachauswahl zeigt der Button die Details für den aktuellen fokussierten Post. Massen-Diagnose wäre möglich, aber als Popup-Friedhof eher eine Strafe als ein Feature.
