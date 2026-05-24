# 1.3.94 Previewer: aufgeschlüsselte Tags im echten Preview-Fenster

## Problem

Die Konfig-Vorschau konnte den Modus `Aufgeschlüsselt` anzeigen, der echte Previewer zeigte aber weiterhin die rohe Tag-Zeile.

Ursache: Die SQL-Abfrage im Preview-Fenster lieferte nur `tags`, aber nicht die typisierten Felder `tags_general`, `tags_character`, `tags_copyright`, `tags_artist` und `tags_meta`. Die Preview-Karte konnte deshalb im echten Previewer nicht nach Tagtypen gruppieren und fiel auf Raw zurück.

## Fix

`PreviewWindow.fetch_preview_posts_by_statuses()` liefert jetzt zusätzlich:

- `tags_general`
- `tags_character`
- `tags_copyright`
- `tags_artist`
- `tags_meta`

Damit nutzt der Previewer dieselbe strukturierte Tag-Darstellung wie die Vorschau in der Konfig.

## Auswirkungen

- Keine Änderung am Datenbankschema.
- Keine Änderung an der Konfig-UI.
- Keine Änderung am Preview-Kartenlayout.
- Nur die Previewer-Abfrage wurde ergänzt.
