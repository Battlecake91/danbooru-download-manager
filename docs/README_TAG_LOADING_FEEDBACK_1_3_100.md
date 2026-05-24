# Patch 1.3.100 - sichtbare Ladeanzeige beim Laden von Tags

Dieser Patch ergänzt sichtbare Rückmeldung, wenn Tag-Daten geladen werden.

## Änderungen

- Lazy-Tabs zeigen beim ersten Öffnen jetzt eine aktive Meldung wie `Lade Tags…`, bevor der schwere Tab konstruiert wird.
- Die Statusleiste zeigt ebenfalls `Lade <Tab>…` und danach `<Tab> geladen.`.
- Im Viewer wird der Tagbereich beim Neuaufbau sichtbar auf `Lade Tags…` gesetzt.
- Nach erfolgreichem Laden zeigt die Statusleiste kurz `Tags geladen.`.

## Zweck

Beim Öffnen des Tags-Tabs oder beim Wechsel auf Posts mit vielen Tags wirkt die Oberfläche nicht mehr eingefroren. Die Arbeit selbst kann je nach Datenbankgröße weiterhin dauern, aber der Nutzer sieht wenigstens, dass die Anwendung lädt und nicht nur beleidigt schweigt.
