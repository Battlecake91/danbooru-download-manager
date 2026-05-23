# 1_3_33 - Viewer-Statuschips und Preview-Ladeanzeige

Dieses Patch-ZIP enthält nur die geänderten Dateien.

## Viewer

- Status-Chips sind jetzt anklickbar.
- Es ist weiterhin immer nur ein Status aktiv.
- Klick auf einen anderen Chip setzt diesen Status.
- Klick auf den aktiven Chip setzt den Post auf `new` zurück.

## Preview-Suche

- Das Autocomplete-Dropdown ist breiter und orientiert sich mindestens an der Suchfeldbreite.
- Include- und Exclude-Tags mit führendem `-` bleiben weiterhin unterstützt.

## Preview-Laden

- Beim Wechsel in den Preview-Tab erscheint eine zentrale Ladefläche mit `Lädt Preview…`.
- Während Karten aufgebaut werden, steht dort `Lädt Thumbnails… X/Y`.
- Die Preview wird erst wieder eingeblendet, wenn der Kartenaufbau fertig ist.
- Der alte Fetch-Tab sollte dadurch nicht mehr als Geisterbild im Preview-Bereich stehen bleiben.
- Zusätzlich wurde ein doppeltes `ORDER BY` in der Preview-SQL-Abfrage entfernt.
