# 1.3.69 Viewer UI/Image Cache

Kleiner Performance-Feinschliff nach dem Viewer-Performance-Test.

## Änderungen

- Der Viewer besitzt nun einen kleinen LRU-Pixmap-Cache.
  - Standard: 12 Bilder.
  - Konfigurierbar über `viewer.pixmap_cache_items`.
  - Vor/zurück durch bereits gesehene Bilder dekodiert nicht erneut dieselbe Datei.
- Der Tag-Widget-Aufbau friert Repaints während des Neubaus kurz ein.
  - Das reduziert UI-Arbeit beim Wechseln zwischen Posts.
  - Die Anzeige und Tag-Funktionen bleiben unverändert.

## Erwartung

Die großen Bremsen wurden bereits in 1.3.68 beseitigt. Dieser Patch optimiert nur die Restkosten:

- `tags_widget_ui` sollte etwas stabiler/niedriger werden.
- `qpixmap_load` fällt vor allem beim Zurückspringen oder erneuten Anzeigen bereits gesehener Bilder.

Der erste Decode eines großen Bildes kann weiterhin spürbar sein. Dafür bräuchte es später asynchrones Vorladen oder Thumbnail/Preview-Modus.
