# 1.3.74 Preview-Statuswechsel: Tag-Statistik gebündelt

Dieser Patch reduziert die Wartezeit bei Statusänderungen im Previewer, besonders bei großen Mehrfachauswahlen.

## Problem

Die bisherige Bulk-Statusfunktion schrieb zwar nur noch einen Commit, aktualisierte danach aber weiterhin für jeden einzelnen Post die Tag-Statistik. Bei 100 markierten Thumbnails bedeutete das viele redundante Aggregationen über `post_tags`, `posts`, `post_reviews` und `tag_scores`.

## Änderung

`Database.set_post_statuses()` ermittelt jetzt vor der Änderung:

- alte Statuswerte der betroffenen Posts
- ob `saved`, `rejected` oder `auto_rejected` überhaupt betroffen ist
- die vereinigte Tagmenge aller betroffenen Posts

Danach werden die Posts aktualisiert und die Tag-Statistik wird nur noch einmal für die gesamte betroffene Tagmenge berechnet.

## Zusätzliche Optimierung

Wenn weder der alte noch der neue Status Einfluss auf die Tag-Score-Statistik hat, wird die Statistikaktualisierung komplett übersprungen. Das betrifft zum Beispiel reine Wechsel zwischen `new`, `potential` und `already_known`.

## Unverändert

- Statuslogik bleibt gleich.
- Thumbnail-Verschiebung für `saved`/`rejected` bleibt erhalten.
- UI-Verhalten bleibt gleich.
- Keine Änderung am Datenbankschema.
