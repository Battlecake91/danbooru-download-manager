# Patch 1.3.103 - Preview-Sortierung merken und Labels zurückholen

## Ziel

Der Previewer soll die zuletzt verwendete Sortierung behalten. Außerdem waren nach dem letzten Aufräumen zwei sichtbare Beschriftungen zu stark entfernt worden.

## Änderungen

### Previewer

Datei:

- `app/gui/preview_window.py`

Änderungen:

- Die Sortierung wird beim Ändern unter `gui.preview_sort_order` in `app_settings` gespeichert.
- Beim Start des Previewers wird `gui.preview_sort_order` wieder gelesen und als aktive Sortierung gesetzt.
- Falls der gespeicherte Wert unbekannt ist, fällt der Previewer auf `id_desc` zurück.
- Das Feld für die Thumbnailgröße hat wieder eine sichtbare Beschriftung `Thumbnail:`.
- Die Vorauswahl-Checkbox hat wieder eine sichtbare Beschriftung `Vorauswahl:`.

## Hinweise

Die Sortierung wird zusätzlich in der laufenden Runtime-Config aktualisiert, damit der aktuelle Prozess denselben Wert weiterverwendet. Ein Fehler beim Speichern blockiert den Previewer nicht, sondern wird nur in der Statusleiste angezeigt.
