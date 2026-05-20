# Danbooru Manager 1.1.2 - Globales GUI-Fehlerlog

## Warum?

Wenn `tag_tab_error.log` nicht existiert, passiert der Fehler wahrscheinlich außerhalb der lokalen `safe()`-Blöcke oder die App läuft aus einem anderen Arbeitsverzeichnis.

## Neu

Fehler werden jetzt fest unter dem konfigurierten `work_dir` geloggt:

```text
<work_dir>/logs/gui_error.log
```

Beispiel bei Standardkonfiguration:

```text
danbooru_manager_data/logs/gui_error.log
```

## Änderungen

- globaler Python/Qt Exception-Hook
- GUI-Startfehler werden geloggt
- Tag-Tab schreibt ebenfalls in `work_dir/logs/gui_error.log`
- Kontextmenü, Doppelklick, Reload und Filterwechsel im Tag-Tab sind abgesichert

## Geänderte Dateien

- `app/gui/main_window.py`
- `app/gui/tag_tab.py`

## Neue Datei

- `app/gui/error_handler.py`

## Wenn es weiter ohne Log abstürzt

Dann ist es wahrscheinlich ein nativer Qt/PySide-Crash oder ein Prozessabbruch außerhalb von Python.
Dann bitte die VSCode-Terminalausgabe direkt schicken.
