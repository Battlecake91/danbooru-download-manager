# Patch 1.3.118 - i18n start

## Ziel

Dieser Patch startet die Umstellung der GUI auf Language-Files. Englisch ist ab jetzt der Default. Deutsch bleibt als zweite Sprache erhalten, damit der bestehende Stand nicht sofort wie ein schlecht übersetzter Waschmaschinenfehler aussieht.

## Neue Struktur

- `app/i18n/i18n.py`
  - lädt Übersetzungen aus JSON-Dateien
  - unterstützt Fallback auf Englisch
  - bietet `tr(...)`, `available_languages()` und `language_from_config(...)`
- `app/i18n/locales/en.json`
  - englische UI-Texte für die zuerst migrierten Bereiche
- `app/i18n/locales/de.json`
  - deutsche UI-Texte als Fallback/zweite Sprache

## Geänderte Bereiche

- `app/core/config.py`
  - neuer Default: `ui.language = "en"`
- `app/gui/app_window.py`
  - Fenstertitel
  - Haupttabs
  - Lazy-Loading-Platzhalter
  - Lazy-Loading-Statusmeldungen
  - Fetch-läuft-Tabtitel
- `app/gui/config_tab.py`
  - Sprachwahl unter Basis / Interface
  - zentrale Config-Tabtitel teilweise über i18n
  - Hauptbuttons unten teilweise über i18n
  - Speichern-Dialog teilweise über i18n

## Aktueller Migrationsstand

Die i18n-Infrastruktur steht. Die komplette Oberfläche ist noch nicht vollständig migriert. Das ist Absicht: erst Fundament, dann Tab für Tab migrieren. Sonst entsteht ein halb englischer, halb deutscher GUI-Zombie mit Toolbar.

Bei einer String-Inventur wurden nach diesem Patch noch rund 500 deutschsprachige bzw. deutsch wirkende String-Konstanten gefunden. Die größten Brocken sind:

- `app/gui/tag_tab.py`
- `app/gui/image_viewer.py`
- `app/gui/preview_window.py`
- `app/gui/maintenance_tab.py`
- `app/gui/config_tab.py`
- `app/gui/import_tab.py`
- `app/gui/category_tab.py`
- `app/gui/fetch_tab.py`

## Nächster sinnvoller Schritt

Als nächstes sollte der Fetch-Tab und danach Preview/ThumbnailGrid migriert werden. Danach Viewer, Tags, Kategorien, Importer, Wartung. Logs und technische Fehlertexte können später kommen, solange die UI zuerst sauber englisch wird.
