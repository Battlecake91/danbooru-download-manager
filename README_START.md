# Danbooru Manager Starter 0.1

Erste Basis für die neue GUI-Version des Danbooru-Downloaders.

Diese Version kann noch keine GUI. Sie erstellt zuerst das Fundament:

- YAML-Config laden
- SQLite-Datenbank erstellen
- Kategorien aus Config übernehmen
- Filename-Exclude-Tags übernehmen
- LLM-Tag-Aliase übernehmen
- alte `downloaded_ids.txt` übernehmen
- Danbooru-Posts per API laden
- Post-Metadaten und Tags speichern
- Thumbnails lokal cachen

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Unter Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Config anlegen

```bash
cp config.example.yaml config.yaml
```

Optional `.env`:

```env
DANBOORU_USERNAME=dein_username
DANBOORU_API_KEY=dein_api_key
```

## Datenbank initialisieren

```bash
python main.py --config config.yaml --init-db
```

## Alte History übernehmen

```bash
python main.py --config config.yaml --import-history
```

## Posts und Thumbnails laden

```bash
python main.py --config config.yaml --fetch
```

Mit Debug:

```bash
python main.py --config config.yaml --fetch --debug
```

## Nächster Schritt

Als nächstes kommt die erste PySide6-GUI:

- Preview-Fenster
- Thumbnail-Grid
- Status setzen:
  - hohes Potential
  - prüfen
  - automatisch aussortiert
  - abgelehnt
- Daten aus SQLite anzeigen
