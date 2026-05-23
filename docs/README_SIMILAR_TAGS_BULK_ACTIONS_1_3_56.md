# 1.3.56 - Ähnliche Tags: Massenaktionen statt nur Alias

Der Dialog **Ähnliche Tags suchen/bearbeiten…** im Tag-Tab ist nicht mehr auf Alias-Pflege beschränkt.

## Neu

Nach der Suche per Wildcard-Muster, z. B. `*_hairband`, öffnet sich ein Sammeldialog mit checkbarer Trefferliste. Für alle ausgewählten Tags können mehrere Aktionen gleichzeitig gesetzt werden:

- Alias setzen
- Filename-Ausschluss setzen
- Filename-Ausschluss entfernen
- manuellen Score setzen
- Tags zu einer Kategorie-Regel hinzufügen (`include` oder `exclude`)

Leere oder unveränderte Felder bleiben unberührt. Vor dem Speichern erscheint eine Bestätigung mit den konkreten Aktionen und den betroffenen Tags.

## Verhalten

- Die Trefferliste zeigt vorhandene Aliase und bestehenden Filename-Ausschluss direkt an.
- Sichtbare Tabellenzellen werden lokal aktualisiert.
- Es wird nach den Massenaktionen kein vollständiges `reload_tags()` ausgeführt, damit der Tag-Tab bei großen Datenbanken nicht wieder blockiert.
- Das Suchmuster nutzt weiterhin `*` und `?`.

## Geänderte Dateien

- `app/gui/tag_tab.py`
- `app/core/database.py`
