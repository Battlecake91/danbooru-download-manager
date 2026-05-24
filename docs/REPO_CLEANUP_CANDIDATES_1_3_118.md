# Repo-Cleanup-Kandidaten nach Patch 1.3.118

## Sicher entfernbar

Diese Dateien/Ordner werden für Laufzeit, Build und Entwicklung nicht benötigt:

- `app/__pycache__/`
- `app/core/__pycache__/`
- `app/danbooru/__pycache__/`
- `app/gui/__pycache__/`
- `app/services/__pycache__/`

Begründung: Das sind generierte Python-Bytecode-Caches. Python erzeugt sie bei Bedarf neu. In einem Repo und besonders in Patch-ZIPs haben sie nichts verloren. Natürlich legt Python sie wieder an, weil offenbar auch Maschinen gern Müll produzieren.

## Sehr wahrscheinlich entfernbar

Diese Dateien sind leer und werden nirgends importiert:

- `app/core/models.py`
- `app/gui/preview_grid.py`
- `app/gui/preview_model.py`

Begründung: Alle drei Dateien haben aktuell 0 Byte Inhalt bzw. keinen Code. Eine statische Importprüfung über `app/**/*.py` und `main.py` findet keine Nutzung. Falls sie nur als Platzhalter für spätere Architektur gedacht waren, können sie bleiben. Technisch gebraucht werden sie aktuell nicht.

## Nicht löschen, aber aus Release-Paketen ausschließen

- `.vscode/settings.json`
- `.vscode/tasks.json`

Begründung: Entwicklerkomfort, aber nicht relevant für die fertige Windows-Exe.

## Dokumentations-Altlasten

Der Ordner `docs/` enthält viele historische Patch-README-Dateien. Die sind nicht für die Laufzeit nötig, aber als Änderungsverlauf nützlich. Für ein Release-Paket kann man sie weglassen oder in eine separate Entwickler-Dokumentation verschieben.

Empfehlung:

- Im Git-Repo behalten, bis eine saubere `CHANGELOG.md` existiert.
- In der späteren PyInstaller-/Release-Ausgabe nicht mit ausliefern.
