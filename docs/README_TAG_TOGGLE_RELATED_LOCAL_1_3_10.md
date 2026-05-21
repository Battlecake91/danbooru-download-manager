# 1.3.10 - Tag-Auswahl toggeln und Parent/Child-Lokalstatus korrigieren

## Änderungen

### Viewer-Taglisten

Die Taglisten im Viewer verwenden jetzt `ToggleSelectListWidget`.

Dadurch kann ein bereits markierter Tag durch einen normalen zweiten Linksklick wieder abgewählt werden. Mehrfachauswahl mit Strg/Umschalt bleibt erhalten.

Betroffene Datei:

- `app/gui/tag_display.py`

### Parent/Child-Lokalstatus

Parent-/Child-Posts gelten nicht mehr als lokal vorhanden, nur weil ein Thumbnail, ein Rejected-Thumbnail oder eine Original-Cache-Datei existiert.

Für `lokal vorhanden` zählt im Viewer jetzt ausschließlich ein existierender `final_file_path`, also ein final gespeicherter Post.

Auch die Preview-Badges `Parent lokal` und `Child(s) lokal` zählen nur noch Posts mit gesetztem `final_file_path`.

Betroffene Dateien:

- `app/gui/image_viewer.py`
- `app/core/database.py`

## Verhalten

- Thumbnail vorhanden, aber nicht final gespeichert: `nur DB/Remote`
- Final gespeichert und Datei existiert: `lokal vorhanden`
- Parent/Child-Zähler in der Preview zählen nur final gespeicherte Parent/Child-Posts
