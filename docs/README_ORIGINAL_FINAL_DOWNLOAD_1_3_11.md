# 1.3.11 - Finales Speichern lädt wieder die Originaldatei

## Problem

Bei manchen Posts wurde final nicht die Originaldatei gespeichert, sondern nur die zuvor geladene Viewer-/Sample-/Large-Datei. Beispiel: Danbooru-Original `1774x1080`, lokal final gespeichert aber nur `850x468`.

Ursache: `FinalSaveService` hat `original_cache_path` direkt als Quelle akzeptiert. Dieser Pfad konnte aber aus dem Viewer-Download stammen und je nach `viewer_download_source` nur Danbooru `large_file_url` enthalten.

## Änderung

- `DownloadService.ensure_original_cached()` bleibt für den Viewer zuständig und darf weiterhin eine kleinere Viewer-Datei laden.
- Neu: `DownloadService.ensure_full_original_cached()` lädt für final gespeicherte Dateien strikt `file_url`.
- `FinalSaveService.source_path_for_post(..., download_if_missing=True)` nutzt jetzt nur noch `ensure_full_original_cached()`.
- Alte Cache-Dateien wie `123_large.jpg` oder `123_preview.jpg` werden beim finalen Speichern ignoriert.
- Die echte Originaldatei wird als `123_file.<ext>` im Original-Cache gespeichert.

## Ergebnis

Final gespeicherte Dateien kommen wieder aus Danboorus `file_url`, nicht aus Thumbnail, Preview, Large/Sample oder Viewer-Cache.

## Hinweis

Bereits falsch gespeicherte Dateien werden dadurch nicht automatisch ersetzt. Diese Posts müssen erneut gespeichert oder manuell korrigiert werden, weil die falsche Datei bereits als finaler Pfad in der Datenbank steht.
