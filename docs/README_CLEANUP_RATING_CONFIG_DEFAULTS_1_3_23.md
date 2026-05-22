# 1.3.23 - Cleanup, Rating 0-10 und SQLite-Defaults

## Geändert

### Temporäre Wartung entfernt

Der Tab `Wartung temporär` wird nicht mehr in der Hauptoberfläche angezeigt.
Die Datei `app/gui/maintenance_tab.py` bleibt vorerst im Repo, wird aber nicht mehr importiert oder als Tab eingebunden.

### Persönliches Rating 0-10

Das persönliche Rating im Viewer arbeitet jetzt als 0-10-System:

- Anzeige: `Persönliches Rating: X/10`
- 10 kompakte Sterne
- Linksklick auf einen Stern setzt 1-10
- Rechtsklick auf die Sternleiste setzt wieder 0
- Datenbankwert `post_reviews.stars` wird als Integer 0-10 gespeichert

Alte 0-5-Werte werden beim DB-Start einmalig auf 0-10 migriert:

- 2.5 wird 5
- 4 wird 8
- 5 wird 10

Die Migration wird über `app_settings.migration.personal_rating_0_10` markiert und nicht mehrfach ausgeführt.

### YAML nicht mehr nötig

`config.yaml` ist nicht mehr Pflicht. Die Anwendung startet jetzt mit internen Defaults, wenn keine YAML existiert.

Eine vorhandene YAML-Datei wird weiterhin optional als altes Start-Overlay gelesen. Damit bleiben alte Setups lauffähig, aber die laufende Konfiguration bleibt SQLite/app_settings.

`PyYAML` wurde aus `requirements.txt` entfernt. Es wird nur noch benötigt, wenn tatsächlich eine alte YAML-Datei geladen werden soll.

### Konfigurations-Export/Import/Reset

Im Konfigurationstab gibt es neue Aktionen:

- `Konfiguration exportieren`
- `Konfiguration importieren`
- `SQLite-Konfiguration auf Defaults`

Der Export ist JSON und enthält:

- `app_settings`
- Kategorien und Regeln
- Filename-Ausschlüsse
- Tag-Aliase
- manuelle Tag-Gewichtungen

Der Import aktualisiert/ergänzt vorhandene Kategorien, Regeln, Filename-Ausschlüsse, Aliase und Gewichtungen. Er löscht keine Posts und keine Bilddateien.

Der Default-Reset löscht nur `app_settings` und schreibt die internen Defaultwerte neu. Kategorien, Posts, Tags, Aliase und Gewichtungen bleiben erhalten.

## Betroffene Dateien

- `app/core/config.py`
- `app/core/database.py`
- `app/gui/app_window.py`
- `app/gui/config_tab.py`
- `app/gui/image_viewer.py`
- `main.py`
- `requirements.txt`
