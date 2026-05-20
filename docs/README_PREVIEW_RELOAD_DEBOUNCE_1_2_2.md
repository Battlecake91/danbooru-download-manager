# Danbooru Manager 1.2.2 - Preview Reload Debounce + Viewer-Deduplizierung

## Problem

Beim Ändern des Preview-Limits, z. B. von 100 auf 500, konnten massenhaft Viewer-Fenster entstehen.

Das ist derselbe Grundfehler wie beim Viewer-Query:

- UI-Elemente feuern mehrere Signale
- Preview baut das Grid sofort neu
- Qt verarbeitet währenddessen noch alte Events
- irgendwo wird `open_viewer_requested` mehrfach ausgelöst
- Ergebnis: Fensterzoo bis zum Absturz

## Fix 1: Reloads werden entprellt

`valueChanged` von Ansicht, Status und Limit ruft nicht mehr direkt `reload_posts()` auf.

Stattdessen:

```text
schedule_reload()
→ QTimer singleShot 250 ms
→ reload_posts()
```

Zusätzlich:

```python
self.limit_spin.setKeyboardTracking(False)
```

Beim Tippen von `500` reloadet er also nicht bei jedem Zwischenzustand.

## Fix 2: Reentrancy Guard

Während `reload_posts()` läuft:

- kein zweiter Reload parallel
- weitere Reload-Anfrage wird gemerkt
- danach wird maximal ein Reload nachgezogen

## Fix 3: Viewer nur einmal pro Post-ID

`PreviewWindow` hält jetzt:

```python
self.viewer_windows_by_post_id: dict[int, ImageViewerWindow]
```

Wenn ein Viewer für diese Post-ID schon offen ist:

```text
raise_()
activateWindow()
kein neues Fenster
```

Selbst wenn Qt wieder Signale hustet wie ein alter Drucker, entstehen keine hunderte Viewer-Fenster mehr.

## Geänderte Datei

- `app/gui/preview_window.py`

## Test

1. Preview öffnen
2. Limit von 100 auf 500 ändern
3. Es sollte genau ein verzögerter Reload passieren
4. Es dürfen keine neuen Viewer-Fenster entstehen
5. Mehrfach Doppelklick auf denselben Post öffnet keinen zweiten Viewer, sondern fokussiert den bestehenden
