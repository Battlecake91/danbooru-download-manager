# Danbooru Manager 1.3.2 - Doppeltes Speichern verhindern

## Problem

Ein bereits gespeicherter Post konnte erneut final gespeichert werden.
Dadurch entstanden Dateikopien mit `_2`, `_3`, usw.

## Fix

`FinalSaveService.save_post()` prüft jetzt vor dem Speichern:

```text
status == saved
oder
final_file_path ist gesetzt
```

Falls ja:

```text
kein Kopieren
kein neuer Dateiname
Meldung: Bereits gespeichert
```

## Neue Exception

```python
AlreadySavedError
```

Diese enthält:

- Post-ID
- finalen Pfad, falls vorhanden

## Viewer

Der Viewer fängt `AlreadySavedError` ab und zeigt eine Meldung:

```text
Post ist bereits gespeichert.
Pfad: ...
```

Außerdem:

- Button `Final speichern (F)` wird deaktiviert, wenn der aktuelle Post bereits gespeichert ist
- nach erfolgreichem Speichern wird der Button ebenfalls deaktiviert

## Geänderte Dateien

```text
app/services/final_save_service.py
app/gui/image_viewer.py
```
