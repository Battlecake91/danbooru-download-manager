# Patch 1.3.113 - Parent/Child Workflow und Finaldateien löschen

## Previewer

- Parent/Child-Posts werden nach dem normalen Sortieren gruppiert, soweit sie im geladenen Ergebnis enthalten sind.
- Dadurch stehen Parent und Childs im Previewer nebeneinander, statt später erneut wie ein Déjà-vu mit Thumbnail aufzutauchen.
- Preview-Karten zeigen Parent/Child-Bezug deutlicher an:
  - Teil einer Parent/Child-Gruppe
  - Parent lokal/DB bekannt
  - bekannte Child-Posts
  - Child-Hinweis von Danbooru

## Viewer

- Die Parent/Child-Liste im Viewer öffnet lokal vorhandene verwandte Posts jetzt per Doppelklick in einem separaten Viewer-Fenster.
- Im Kontextmenü der Parent/Child-Liste gibt es zusätzlich:
  - In separatem Viewer öffnen
  - Lokale Datei im System öffnen
  - Lokalen Ordner öffnen
  - Remote Originalpost öffnen
  - Links/Pfade kopieren

## Finaldateien löschen

- Im Viewer gibt es einen neuen Button: `Finaldatei löschen`.
- Im Previewer-Kontextmenü gibt es: `Finaldatei aus gespeichertem Pfad löschen`.
- Bei Mehrfachauswahl im Previewer wirkt die Löschaktion auf alle markierten Posts.
- Gelöscht wird nur die lokal gespeicherte Finaldatei aus `final_file_path`.
- Der DB-Post bleibt erhalten.
- `final_file_path`, `final_directory` und `saved_at` werden geleert.
- Wenn der Status vorher `saved` war, wird er auf `new` gesetzt.

## Nebenbei

- `count_preview_posts()` hatte eine doppelte `SELECT COUNT(*) AS count`-Zeile aus einem früheren Patchstand. Das wurde bereinigt.
