# 1.3.13 - Viewer-Reparaturknöpfe und Wartungsfix

## Viewer

Neue Funktionen im Bildbetrachter:

- **Final überschreiben**
  - lädt Danbooru `file_url` frisch neu
  - überschreibt die bestehende finale Datei am vorhandenen `final_file_path`
  - behält Dateiname und Zielordner bei
  - funktioniert auch, wenn vorher versehentlich Sample/Large/Thumbnail final gespeichert wurde

- **Post neu holen**
  - lädt die Post-Metadaten neu von Danbooru
  - aktualisiert Tags, URLs, Originalmaße und Dateigröße
  - lädt die Viewer-Datei neu gemäß `viewer_download_source`

- **Aus DB entfernen**
  - löscht den Post aus der lokalen Datenbank inklusive Tags, Review und Kategoriezuordnung
  - löscht keine Bilddateien auf der Platte

## Filename-Preview

- `on_category_changed()` akzeptiert jetzt das Qt-Signalargument korrekt.
- Die Dateiname-Vorschau wird bei Kategorieänderung aktualisiert.
- Die Vorschau wird nach Filename-Exclude-Aktionen im Viewer aktualisiert.
- Bei Fokuswechsel zurück in den Viewer wird die Vorschau erneut berechnet, damit Änderungen aus anderen Tabs nicht ewig wie abgestandener Kaffee angezeigt werden.

## DownloadService

- `ensure_original_cached(..., force=True)` lädt Viewer-Dateien wirklich neu.
- `ensure_full_original_cached(..., force=True)` lädt die echte Danbooru-Originaldatei erneut über `file_url`.

## Wartung temporär

- Fehlende finale Dateien mit vorhandenem `final_file_path` können jetzt repariert werden.
- Die Reparatur bricht nicht mehr ab, nur weil die lokale finale Datei fehlt.
- Zielordner werden bei Bedarf neu angelegt.
- Der Button lädt jetzt alle **Verdächtigen/Fehlenden** neu, nicht nur verdächtige Auflösungen.

