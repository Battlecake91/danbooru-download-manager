# 1.3.95 - Start beschleunigt: Lazy Tabs

Dieser Patch reduziert die Startzeit der GUI, indem beim Programmstart nur noch der Fetch-Tab sofort erzeugt wird.

## Problem

`AppWindow` hat bisher beim Start alle Tabs direkt konstruiert:

- Preview / Review
- Importer
- Tags
- Kategorien
- Konfiguration

Mehrere dieser Tabs führen bereits im Konstruktor Datenbankabfragen oder Reloads aus. Besonders teuer ist der Tag-Tab, weil er initial `fetch_tag_overview(..., limit=5000)` lädt. Dadurch musste der Nutzer beim Start warten, obwohl diese Tabs oft gar nicht sofort geöffnet werden.

## Änderung

- `AppWindow` erzeugt beim Start nur noch `FetchTab`.
- Alle anderen Tabs bekommen zuerst einen leichten Platzhalter.
- Beim ersten Öffnen eines Tabs wird der echte Tab erzeugt und ersetzt den Platzhalter.
- Fetch-Signale bleiben erhalten:
  - Fetch gestartet / beendet aktualisiert den Preview-Status, wenn der Preview-Tab schon existiert.
  - Wenn Preview noch nicht geladen wurde, wird ein ausstehender Reload gemerkt und beim ersten Öffnen nachgeholt.
- Import- und Config-Signale werden erst verbunden, wenn die jeweiligen Tabs erzeugt werden.

## Debug

Neue CLI-Option:

```bash
python main.py --gui --debug-startup
```

Damit werden einfache Startzeit-Markierungen für `AppWindow` und Lazy-Tab-Erzeugung ausgegeben.

## Erwarteter Effekt

Das Fenster sollte schneller erscheinen, weil teure Tab-Initialisierung und große DB-Abfragen erst dann passieren, wenn der jeweilige Tab wirklich geöffnet wird.
