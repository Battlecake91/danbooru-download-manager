# 1.3.114 - Importer Post-ID-Erkennung und lokale Datei-Begriffe

## Ziel

Dieser Patch räumt die Bezeichnungen im Previewer/Viewer auf und erweitert den Importer.

## UI-Begriffe

- `Final speichern` wurde in der sichtbaren UI zu `Speichern` geändert.
- `Finaldatei` wurde in der sichtbaren UI zu `Lokale Datei` geändert.
- Löschdialoge und Hinweise sprechen jetzt von lokaler Datei bzw. lokalem Pfad.

Intern bleiben bestehende DB-Felder wie `final_file_path` unverändert. Das ist Absicht, damit keine Migration nur wegen schönerer Wörter nötig wird. Menschen lieben Umbenennungen, Datenbanken eher nicht.

## Importer

Der Importer kann bestehende Dateien jetzt nicht nur über einen MD5-Hash im Dateinamen zuordnen, sondern auch über eine Danbooru-Post-ID im Dateinamen.

Priorität:

1. MD5-Hash, falls ein 32-stelliger Hash gefunden wird.
2. Post-ID, falls kein MD5 vorhanden ist.

Erkannte Post-ID-Muster:

- explizite Muster wie `post_123456`, `postid-123456`, `id_123456`, `danbooru_123456`
- als Fallback eine alleinstehende 5- bis 12-stellige Zahl

## Hinweis im Importer

Der Importer zeigt jetzt einen gelben Warnhinweis:

> Achtung: Der Import kann nur funktionieren, wenn die Danbooru-Post-ID oder der MD5-Hash im Dateinamen steht.

## Verhalten bei nicht erkannten Dateien

Wenn weder MD5 noch Post-ID gefunden wird, wird die Datei übersprungen und als `Ohne ID/MD5` gezählt.

## Geänderte Dateien

- `app/gui/image_viewer.py`
- `app/gui/preview_window.py`
- `app/gui/thumbnail_grid.py`
- `app/gui/import_tab.py`
- `app/services/existing_file_import_service.py`
