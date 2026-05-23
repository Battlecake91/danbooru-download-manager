# 1.3.55 - Alias-Massenpflege im Tag-Tab

Dieser Patch erweitert den Tag-Tab um einfache Massenpflege für Tag-Aliase.

## Neue Aktionen im Kontextmenü

Bei Rechtsklick auf einen oder mehrere Tags gibt es jetzt zusätzlich:

- **Alias bearbeiten** bei einem einzelnen Tag
- **Alias für Auswahl setzen…** bei mehreren markierten Tags
- **Alias entfernen** / **Alias für Auswahl entfernen…**
- **Ähnliche Tags suchen…**

## Alias für Auswahl setzen

Mehrere Tags markieren, Rechtsklick, **Alias für Auswahl setzen…** wählen und den gemeinsamen Alias eingeben.

Vor dem Speichern zeigt die GUI eine Bestätigung mit den betroffenen Tags. Ein leerer Alias entfernt den vorhandenen Alias.

## Ähnliche Tags suchen

Die Aktion schlägt aus dem angeklickten Tag ein Suchmuster vor, z. B.:

- `red_hairband` → `*_hairband`
- `blue_eyes` → `*_eyes`

Unterstützt werden:

- `*` für beliebig viele Zeichen
- `?` für ein Zeichen

Die Treffer werden in einem Dialog mit Checkboxen angezeigt. Nicht passende Treffer können abgewählt werden. Danach wird ein gemeinsamer Alias gesetzt oder bei leerem Alias entfernt.

## Performance-Hinweis

Alias-Änderungen aktualisieren nur die sichtbaren Tabellenzellen lokal. Es wird bewusst kein vollständiges `reload_tags()` ausgelöst, damit der Tag-Tab bei großen Datenbanken nicht wieder blockiert.
