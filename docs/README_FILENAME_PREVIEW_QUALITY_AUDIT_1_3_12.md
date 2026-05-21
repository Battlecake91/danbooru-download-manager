# 1.3.12 - Dateiname-Vorschau und temporäre Qualitätsprüfung

## Dateiname-Vorschau im Viewer

Der Viewer zeigt unter dem Zielpfad jetzt eine Dateiname-Vorschau an:

- finaler Dateiname laut aktuellem `filename.pattern`
- verwendetes Pattern
- Anzahl der verwendeten Artist-, Character-, Copyright-, General- und Meta-Tags
- die aktuell im Dateinamen enthaltenen General-Tags
- Anzahl der durch Filename-Exclude entfernten Tags

Damit kann man direkt sehen, ob noch unnötige Tags im Dateinamen landen und sie über den Tag-Rechtsklick in den Filename-Exclude schieben.

## Neue Metadaten in der Datenbank

Die Tabelle `posts` bekommt per Migration diese Spalten:

- `image_width`
- `image_height`
- `file_size`

Neue Fetch-Läufe speichern diese Werte direkt aus der Danbooru-API. Für alte Einträge kann die temporäre Wartungsseite fehlende Werte nachladen.

## Temporärer Tab: Wartung temporär

Es gibt einen neuen Tab `Wartung temporär`.

Funktion:

1. `Gespeicherte Dateien prüfen` scannt alle Posts mit `final_file_path`.
2. Lokale Bildmaße werden mit `QImageReader` gelesen.
3. Danbooru-Originalmaße werden aus der DB genommen oder optional live von Danbooru nachgeladen.
4. Wenn lokale Breite oder Höhe kleiner als das Danbooru-Original ist, wird der Post als `Verdächtig` markiert.
5. Zusätzlich wird die lokale Dateigröße gegen `file_size` geprüft, falls vorhanden.

## Reparatur

- `Ausgewählte Verdächtige neu laden/ersetzen`
- `Alle Verdächtigen neu laden/ersetzen`

Die Reparatur lädt strikt `file_url` über `DownloadService.ensure_full_original_cached()` und ersetzt die Datei am bestehenden `final_file_path`. Der Dateiname und der Zielordner bleiben also erhalten.

## Hinweis

Der Wartungs-Tab ist als temporäre Reparaturfunktion gedacht und kann später wieder entfernt werden, sobald die alten falsch gespeicherten Sample-/Thumbnail-Dateien bereinigt sind.
