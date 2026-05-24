# 1.3.83 Import-Reparatur und vorhandene Post-IDs

Dieser Patch erweitert den Importer um zwei sichere Reparatur-/Update-Wege für bereits heruntergeladene Dateien.

## Import-Reparatur

Im Tab **Importer** gibt es jetzt den Bereich **Import reparieren**.

Workflow:

1. Betroffenen Ordner auswählen.
2. Bei **Falsch importiert als** die alte/falsche Kategorie wählen.
3. Bei **Kategorie** die neue/richtige Kategorie wählen.
4. Optional **Nach Import/Reparatur im bestehenden Ordner nach aktuellem Dateinamensschema umbenennen** aktivieren.
5. **Import-Kategorie im Ordner reparieren** drücken.

Der Importer sucht gespeicherte Posts, deren `final_file_path` im gewählten Ordner liegt und die noch der alten Kategorie zugeordnet sind. Danach wird die Kategorie auf die neue Kategorie gesetzt.

Wichtig:

- Dateien werden nicht verschoben.
- Optional wird nur im bestehenden Ordner umbenannt.
- Die Tag-Statistik wird für betroffene Tags aktualisiert.
- Der gespeicherte Dateipfad bleibt erhalten bzw. wird bei Umbenennung aktualisiert.

## Vorhandene Post-IDs beim Import

Beim normalen Ordnerimport gibt es jetzt die Option:

```text
Vorhandene Post-IDs aktualisieren: Pfad und Kategorie überschreiben
```

Standard: aktiviert.

Wenn ein Danbooru-Post bereits in der Datenbank existiert, wird bei aktivierter Option:

- Danbooru-Metadaten aktualisiert,
- Status auf `saved` gesetzt,
- `final_file_path` und `final_directory` auf die importierte Datei gesetzt,
- die gewählte Kategorie gesetzt,
- die Tag-Statistik aktualisiert.

Wenn die Option deaktiviert ist, werden vorhandene Post-IDs übersprungen.

## Hintergrund

Das ist vor allem für zwei Fälle gedacht:

- Ein Import wurde versehentlich mit falscher Kategorie ausgeführt.
- Bestehende Dateien sollen später neu mit korrektem Pfad/Kategorie in die Datenbank übernommen werden, ohne Duplikate oder manuelles SQL-Gefummel.
