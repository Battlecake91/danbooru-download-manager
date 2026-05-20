# Danbooru Manager 0.6 - Thumbnail-Quelle und Hotkeys

## Neu

### Bessere Thumbnail-Qualität

Die Download-Quelle für Thumbnails ist nun konfigurierbar:

```yaml
thumbnail_download_source: "large"
thumbnail_redownload_existing: false
```

Mögliche Werte:

- `preview`: kleine Danbooru-Vorschau, schnell, aber unscharf
- `large`: `large_file_url`, meist guter Kompromiss
- `file`: Originaldatei, scharf, aber potentiell groß
- `best`: `file -> large -> preview`

Die neuen Cache-Dateien enthalten die Quelle im Namen:

```text
12345678_large.jpg
12345678_preview.jpg
```

Wenn bereits unscharfe `preview`-Thumbnails vorhanden sind, reicht meist:

```yaml
thumbnail_download_source: "large"
```

und danach ein neuer Fetch-Lauf. Der neue Pfad wird in der Datenbank gesetzt.

Falls wirklich überschrieben werden soll:

```yaml
thumbnail_redownload_existing: true
```

### Tastaturbedienung

Die Grid-Ansicht unterstützt nun Auswahl und Hotkeys.

Navigation:

- `←`, `→`, `↑`, `↓`: aktuelle Karte bewegen
- `Shift + Pfeiltaste`: Bereich auswählen
- `Leertaste`: aktuelle Karte zur Auswahl hinzufügen/entfernen
- `Ctrl + A`: alle sichtbaren Karten auswählen
- `Esc`: Auswahl löschen
- `Enter`: Originalpost öffnen

Status-Hotkeys:

- `H`: Hohes Potential
- `P`: Prüfen
- `S`: Zum Speichern vormerken
- `A`: Automatisch aussortiert
- `Entf`: Ablehnen
- `G`: Als gespeichert markieren
- `K`: Bereits bekannt
- `N`: Neu zurücksetzen

Maus:

- Linksklick: Karte auswählen
- Ctrl + Linksklick: Karte zur Mehrfachauswahl hinzufügen/entfernen
- Shift + Linksklick: Bereich auswählen
- Rechtsklick: Kontextmenü

## Geänderte Dateien

- `config.example.yaml`
- `app/core/config.py`
- `app/danbooru/thumbnail_cache.py`
- `app/gui/thumbnail_grid.py`
