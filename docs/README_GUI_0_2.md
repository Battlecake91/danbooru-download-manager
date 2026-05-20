# Danbooru Manager 0.2 - Preview-GUI

Diese Version ergänzt die erste PySide6-GUI.

## Neue Funktionen

- `--gui` startet die Preview-Oberfläche
- Thumbnail-Grid aus SQLite
- Statusfilter
- Suche nach ID oder Tag
- einstellbares Limit
- Rechtsklick auf Thumbnail:
  - Hohes Potential
  - Prüfen
  - Automatisch aussortiert
  - Ablehnen
  - Akzeptieren
  - Neu zurücksetzen

## Installation

```powershell
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
```

## Start

```powershell
& ".\.venv\Scripts\python.exe" main.py --config config.yaml --gui
```

Oder über VSCode Task:

```text
GUI
```

## Geänderte Dateien

- `requirements.txt`
- `main.py`
- `app/core/database.py`
- `app/gui/__init__.py`
- `app/gui/main_window.py`
- `app/gui/preview_window.py`
- `app/gui/thumbnail_grid.py`
- `.vscode/tasks.json`
- `.vscode/settings.json`

## Nächster Schritt

Als nächstes sinnvoll:

- Doppelklick öffnet Bildbetrachter
- Download vollständiger Datei aus GUI
- Hotkeys für Statusmarkierung
- zweite Liste für automatisch aussortierte Posts
- Tag-Tab
