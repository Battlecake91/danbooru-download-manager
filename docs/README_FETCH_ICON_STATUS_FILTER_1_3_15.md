# 1.3.15 - Fetch-Auswahl, Icon und Statusfilter-Fix

## Icon

Die Anwendung nutzt jetzt das Danbooru-Icon von Wikimedia:

`https://upload.wikimedia.org/wikipedia/commons/b/b5/Danbooru_icon.png`

Beim Start wird bevorzugt `app_icon_file` aus der Config genutzt. Falls kein lokales Icon konfiguriert ist, wird das Icon unter `work_dir/assets/danbooru_icon.png` gecacht.

## Preview-Suche

Die Tag-/Textsuche respektiert wieder den Statusfilter.

Wenn gespeicherte Posts durchsucht werden sollen, muss entweder der Status `Gespeichert` aktiviert oder die Ansicht `Alle bekannten Posts` gewählt werden.

## Fetch-Tab

Die alte Preset-/Checkbox-Mischung wurde entfernt.

Es gibt jetzt eine klare Auswahl:

- **Manuelle Tags / Query**
  - ein Textfeld für die Danbooru-Query
- **Saved Searches**
  - Label-Feld
  - optionales Query-Filter-Feld

Mehrere Labels oder Query-Filter können per Komma getrennt werden.

## Geänderte Dateien

- `app/gui/fetch_tab.py`
- `app/gui/preview_window.py`
- `app/gui/icon_utils.py`
- `app/gui/app_window.py`
- `app/gui/main_window.py`
- `app/gui/image_viewer.py`
- `app/danbooru/api.py`
