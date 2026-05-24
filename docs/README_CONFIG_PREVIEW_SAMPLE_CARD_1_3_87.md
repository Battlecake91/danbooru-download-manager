# 1.3.87 - Konfigurationsvorschau als echte Preview-Karte

## Ziel

Die GUI-Thumbnail-Vorschau in der Konfigurationsseite ist jetzt keine abstrahierte Box mehr, sondern nutzt dieselbe `ThumbnailCard`-Darstellung wie das Preview-Fenster.

Damit zeigt die Vorschau nun auch:

- Kartenrahmen
- Thumbnail
- Post-ID / Rating / Score
- Status
- Vorauswahl-Score
- Kategorie
- Pfad, falls vorhanden
- kompakte Tags

## GUI-Tab

Im Tab `GUI` wird unter `Vorschau` die echte Preview-Karte des konfigurierten Beispielposts angezeigt.

Die Vorschau reagiert auf:

- Thumbnail-Preset
- `thumbnail_size`
- `card_width_extra`

## Custom (Expert)

Im Tab `Custom (Expert)` gibt es den neuen Bereich:

`GUI-Vorschau Beispielpost`

Dort kann eine Danbooru-Post-ID eingetragen werden. Der Button `Beispielpost laden/aktualisieren` lädt diesen Post einmal über die Danbooru-API, speichert die Metadaten in der lokalen Datenbank und lädt das Thumbnail in den lokalen Thumbnail-Cache.

Danach wird die Karte in der GUI-Konfiguration lokal aus DB und Thumbnail-Datei dargestellt. Beim normalen Öffnen der Konfigurationsseite wird nicht automatisch die API abgefragt.

## Neue Einstellung

```text
gui.preview_sample_post_id
```

Default: `1`

Der Wert wird in `app_settings` gespeichert und über Export/Import wie andere Einstellungen mitgenommen.

## Sicherheit / Verhalten

- Kein automatischer API-Zugriff beim Öffnen der Konfigurationsseite.
- Der Beispielpost wird nur per Button geladen/aktualisiert.
- Es wird nur die lokale Preview-Darstellung aktualisiert.
- Keine Änderung am Preview-Fenster selbst.
- Keine Änderung am Fetch-Workflow.
