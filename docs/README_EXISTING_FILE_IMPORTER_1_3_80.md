# 1.3.80 Importer für bestehende Danbooru-Dateien

Dieser Patch ergänzt einen neuen Tab **Importer**.

## Zweck

Bereits heruntergeladene Dateien können nachträglich in die SQLite-Datenbank übernommen werden. Der Importer liest einen 32-stelligen Danbooru-MD5-Hash aus dem Dateinamen, lädt den passenden Post über `md5:<hash>` nach und speichert dessen Metadaten und Tags in der Datenbank.

Dadurch werden alte Bestände für die aktuelle Preview-, Kategorie- und Scoring-Logik nutzbar.

## Import-Workflow

Im neuen Tab **Importer**:

1. Ordner auswählen
2. Kategorie auswählen
3. optional Unterordner einbeziehen
4. optional **Nach Import nach aktuellem Dateinamensschema umbenennen** aktivieren
5. **Ordner importieren** starten

Für jede Datei:

- MD5 aus Dateiname extrahieren
- Danbooru-Post über `md5:<hash>` laden
- Postdaten und Tags speichern/aktualisieren
- Post als `saved` markieren
- gewählte Kategorie zuweisen
- `final_file_path` und `final_directory` auf die bestehende Datei setzen
- Tag-Statistik aktualisieren, damit gespeicherte Altbestände ins Scoring einfließen

Dateien ohne 32-stelligen MD5 im Namen werden übersprungen.

## Umbenennen nach aktuellem Dateinamensschema

Der Importer kann bestehende Dateien nachträglich nach dem aktuellen Filename-System umbenennen.

Es gibt zwei Wege:

- direkt beim Import: Checkbox **Nach Import nach aktuellem Dateinamensschema umbenennen**
- separat: Button **Gespeicherte Dateien dieser Kategorie umbenennen**

Beim Umbenennen wird das aktuelle Pattern aus der Filename-Konfiguration genutzt, inklusive:

- Artist / Character / Copyright / General / Meta
- Filename-Exclude-Tags
- Tag-Priorisierung nach Score, falls aktiviert
- aktueller Dateiendung bzw. Danbooru-`file_ext`

Die Datenbank wird anschließend auf den neuen Pfad aktualisiert.

## Sicherheitsverhalten

- Der Importer arbeitet in einem Worker-Thread mit eigener SQLite-Verbindung.
- Beim Umbenennen wird nicht blind überschrieben.
- Existiert der Zielname bereits, wird ein Suffix wie `_2`, `_3`, ... angehängt.
- Fehlende Dateien oder nicht gefundene MD5-Posts werden im Log angezeigt und überspringen nicht den ganzen Lauf.

## Geänderte Dateien

- `app/services/existing_file_import_service.py`
- `app/gui/import_tab.py`
- `app/gui/app_window.py`
- `app/core/database.py`
