# 1.3.90 - Konfig-Vorschau im echten PreviewGrid-Kontext

Die GUI-Konfigurationsvorschau rendert den Beispielpost jetzt nicht mehr als einzeln eingebettete `ThumbnailCard`, sondern in einem echten `ThumbnailGrid`-Container mit einer einzelnen Karte.

Warum:

- Der echte Previewer zeigt `ThumbnailCard` immer innerhalb von `ThumbnailGrid` / `QScrollArea`.
- Direkt in der Konfigseite eingebettet sah die Karte ähnlich aus, aber Layout, Hintergrund und Größenverhalten wichen sichtbar ab.
- Die globale `ThumbnailCard` bleibt unverändert, damit der echte Previewer nicht erneut versehentlich umgebaut wird.

Geändert:

- `app/gui/config_tab.py`
  - Import von `ThumbnailGrid` statt `ThumbnailCard`.
  - GUI-Vorschau nutzt ein `ThumbnailGrid` mit genau einem Beispielpost.
  - Thumbnailgröße und `card_width_extra` werden weiterhin aus den aktuellen GUI-Einstellungen übernommen.
  - Kein automatischer API-Zugriff beim Öffnen der Konfig.

Nicht geändert:

- Kein Datenbankschema.
- Keine Previewer-Logik.
- Keine `ThumbnailCard`-Layoutänderung.
