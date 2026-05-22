# 1.3.27 - Fetch-Statusanzeige

## Geändert

- `app/gui/fetch_tab.py`
- `app/gui/app_window.py`
- `app/gui/preview_window.py`

## Inhalt

### Fetch-Status im Previewer

Während ein Fetch läuft, wird im Preview-Tab sichtbar angezeigt:

- Toolbar-Chip `Fetch läuft…`
- Statusbar-Hinweis
- Leerer Preview zeigt `Fetch läuft… Noch keine Posts in dieser Ansicht.`
- Der Tab-Titel wird temporär zu `Preview / Review · Fetch läuft`

Nach Abschluss oder Fehler wird der Status wieder zurückgesetzt.

### Technische Änderung

`FetchTab` sendet jetzt zusätzliche Signale:

- `fetch_started`
- `fetch_failed_signal`

`AppWindow` reicht diesen Zustand an `PreviewWindow.set_fetch_running()` weiter.
