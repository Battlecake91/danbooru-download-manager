# Patch 1.3.96 - Start beschleunigen: Fetch-Tag-Suggestions lazy laden

## Problem

Nach Patch 1.3.95 wurden die schweren Tabs lazy geladen, aber der Start lag weiterhin bei etwa fünf Sekunden:

```text
[STARTUP 42323.685] AppWindow: begin
[STARTUP 42328.704] AppWindow: shown-ready
```

Der verbleibende Blocker war sehr wahrscheinlich der Fetch-Tab. Dieser hat beim Erzeugen sofort `reload_tag_suggestions()` aufgerufen. Diese Funktion ruft `db.suggest_tags(limit=1500)` auf und erzeugt mehrere `GROUP BY`-Abfragen über `post_tags`. Bei größeren Datenbanken ist das für den Programmstart zu teuer.

## Änderung

- `FetchTab` lädt Tag-Suggestions nicht mehr im Konstruktor.
- `TagQueryLineEdit` fordert Suggestions erst beim ersten Fokus auf das manuelle Tag-Suchfeld an.
- Bereits geladene Suggestions werden gecacht und nicht mehrfach geladen.
- `AppWindow` gibt bei `--debug-startup` zusätzlich Messpunkte um die FetchTab-Erzeugung aus:
  - `FetchTab: begin`
  - `FetchTab: end`

## Test

Starten mit:

```bash
python main.py --gui --debug-startup
```

Erwartung:

```text
[STARTUP ...] AppWindow: begin
[STARTUP ...] FetchTab: begin
[STARTUP ...] FetchTab: end
[STARTUP ...] AppWindow: shown-ready
```

Der Abstand zwischen `FetchTab: begin` und `FetchTab: end` sollte deutlich kleiner sein als vorher. Die Tag-Vorschläge im manuellen Suchfeld erscheinen erst, wenn das Feld benutzt wird.
