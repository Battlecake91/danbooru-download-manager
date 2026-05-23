# 1.3.39 - Viewer Tagspalten optisch geglättet

Geändert:

- General-/Meta-Tagzeilen verwenden wieder normale Schriftstärke.
- Eingebettete Detail-Labels erzwingen `font-weight: normal`.
- Filename-Exclude-Spalte nutzt jetzt feste Kurzwerte:
  - `✖: J` = ja
  - `✖: N` = nein
- Damit bleibt die Spalte optisch gleichmäßiger als mit unterschiedlich breiten Symbolen wie Haken/Strich.

Enthaltene Dateien im Patch-ZIP:

- `app/gui/tag_display.py`
- `docs/README_VIEWER_TAG_COLUMNS_NO_BOLD_1_3_39.md`
