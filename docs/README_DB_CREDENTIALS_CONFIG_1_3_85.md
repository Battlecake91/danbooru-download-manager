# 1.3.85 - Danbooru-Zugangsdaten in SQLite-Konfiguration

## Ziel

Username und API-Key können jetzt in der Konfigurationsseite gepflegt und in der SQLite-Tabelle `app_settings` gespeichert werden.

## Konfigurationsseite

Im Bereich **Fetch** gibt es neue Felder:

- `username`
- `api_key`
- Checkbox **API-Key anzeigen**

Der API-Key wird standardmäßig als Passwortfeld verdeckt angezeigt.

## Runtime-Verhalten

Beim Speichern werden folgende app_settings geschrieben:

- `username`
- `api_key`

Nach dem Speichern werden die Werte direkt in das laufende `config`-Dict übernommen. Neue Fetch-/Importer-/Download-Services verwenden damit die DB-Zugangsdaten.

Beim Programmstart werden vorhandene `app_settings` nach `db.initialize_schema()` zusätzlich auf die Runtime-Konfiguration gelegt. Dadurch wirken in SQLite gespeicherte Zugangsdaten auch nach einem Neustart.

Hinweis: `database_file` selbst kann nicht auf diese Weise vor dem Öffnen der DB geändert werden, weil dafür bereits eine Datenbankverbindung bestehen muss.

## Sicherheit

Der API-Key wird in SQLite als Klartext gespeichert. Das ist keine Verschlüsselung, sondern nur zentrale lokale Ablage. Die DB-Datei sollte entsprechend geschützt werden.

Damit der API-Key nicht versehentlich im UI herumliegt:

- das Feld ist standardmäßig verdeckt
- `Raw app_settings` maskiert `api_key`
- Konfigurations-Export maskiert `api_key` mit `********`
- beim Import wird ein maskierter API-Key nicht übernommen, damit kein echter Key durch `********` ersetzt wird

