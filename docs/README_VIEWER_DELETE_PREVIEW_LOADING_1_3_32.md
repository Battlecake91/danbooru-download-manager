# 1.3.32 - Viewer Delete-Tagaktion und Preview-Ladeanzeige

## Viewer

- Wenn im Viewer Tags markiert sind und die Option `Nur nicht ausgeschlossene Filename-Tags anzeigen` aktiv ist, schließt `Entf` die markierten Tags vom Dateinamen aus.
- Ohne markierte Tags oder ohne aktive Filteroption bleibt `Entf` wie bisher: aktuelles Bild ablehnen.
- Die Tag-Aktion per `Entf` zeigt keinen Dialog mehr, sondern nur eine kurze Statusmeldung.

## Preview

- Beim Laden der Preview wird ein mittiger Hinweis `Lädt Preview…` mit endlosem Balken angezeigt.
- Während die Thumbnail-Karten in Batches aufgebaut werden, bleibt die Statuszeile auf `Lädt Preview-Karten… X/Y`.
- `Preview geladen` erscheint erst, wenn der Kartenaufbau abgeschlossen ist.
- Der Grid-Aufbau deaktiviert Updates nicht mehr über mehrere QTimer-Batches hinweg. Dadurch sollte das schwarze Preview-Fenster verschwinden.

## ZIP-Hinweis

Dieses Patch-ZIP enthält nur die geänderten Dateien.
