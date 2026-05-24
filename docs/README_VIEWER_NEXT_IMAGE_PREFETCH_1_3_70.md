# 1.3.70 - Viewer Next-Image-Prefetch

## Ziel

Der Viewer lädt und dekodiert jetzt das nächste lokal vorhandene Bild im Hintergrund vor. Dadurch soll beim normalen Vorwärtsblättern die Zeit in `qpixmap_load` sinken, weil das Bild bereits als `QImage` vorbereitet ist.

## Technische Umsetzung

- Der Viewer nutzt einen einzelnen Hintergrund-Worker (`ThreadPoolExecutor(max_workers=1)`).
- Im Worker wird ausschließlich `QImage` geladen.
- `QPixmap` wird weiterhin nur im GUI-Thread erzeugt.
- Das ist wichtig, weil `QPixmap` nicht sauber für Worker-Threads gedacht ist.
- Der bestehende Pixmap-LRU-Cache bleibt erhalten.
- Prefetch nutzt nur bereits lokal vorhandene Dateien.
- Fehlende Originalbilder werden beim Prefetch nicht heruntergeladen.

## Neue Config-Optionen

Unter `viewer` optional:

```yaml
viewer:
  prefetch_next_image: true
  prefetch_next_count: 1
  pixmap_cache_items: 12
```

`prefetch_next_image` aktiviert/deaktiviert das Vorladen.

`prefetch_next_count` legt fest, wie viele folgende Bilder vorbereitet werden. Standard ist 1. Höhere Werte können mehr RAM verbrauchen.

`pixmap_cache_items` begrenzt weiterhin den Bildcache.

## Performance-Log

Der Viewer-Performance-Test enthält zusätzlich:

```text
prefetch_schedule=...
```

Das misst nur die Zeit zum Einplanen des Prefetch-Jobs, nicht das Hintergrund-Decoding selbst.

Wenn der Prefetch greift, sollte `qpixmap_load` beim nächsten Bild oft deutlich kleiner werden. Bei sehr schnellem Durchklicken kann der Worker noch nicht fertig sein, dann lädt der Viewer wie bisher synchron.

## Verhalten

- Beim Anzeigen von Bild N wird Bild N+1 vorbereitet.
- Beim Wechsel auf Bild N+1 wird das vorbereitete `QImage` in eine `QPixmap` umgewandelt und im Cache abgelegt.
- Beim Schließen des Viewers wird der Prefetch-Worker beendet.

