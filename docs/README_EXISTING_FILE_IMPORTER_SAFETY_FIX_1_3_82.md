# 1.3.82 Existing-File-Importer Safety-Fix

## Problem

Beim Import mit aktivierter Umbenennung wurden bestehende Dateien in den Kategorie-Ausgabeordner verschoben. Dadurch wirkten sie im Importordner wie gelöscht.

## Fix

- Der Importer verschiebt bestehende Dateien beim Umbenennen nicht mehr in den Kategorie-Ausgabeordner.
- Umbenennung passiert nur noch im aktuellen Ordner der Datei.
- Der gespeicherte Dateipfad in der Datenbank wird auf den neuen Namen im selben Ordner aktualisiert.
- Bei Namenskollisionen wird weiterhin `_2`, `_3` usw. angehängt.
- Die UI-Texte weisen jetzt klar darauf hin, dass im bestehenden Ordner umbenannt wird.

## Hinweis

Bereits betroffene Dateien wurden sehr wahrscheinlich nicht gelöscht, sondern in den konfigurierten Kategorie-Ausgabeordner verschoben. Der aktuelle Pfad sollte in der Datenbank unter `final_file_path` stehen.
