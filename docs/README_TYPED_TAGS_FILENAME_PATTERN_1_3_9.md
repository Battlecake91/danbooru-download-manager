# Danbooru Manager 1.3.9 - Typisierte Tags und Dateinamen-Pattern

## Neu: Viewer zeigt Tags nach Danbooru-Typ

Der Bildbetrachter nutzt jetzt die in `post_tags.tag_type` gespeicherten Danbooru-Kategorien und zeigt sie getrennt an:

```text
Artist
Character
Serie / Copyright
General
Meta
```

Die Tags bleiben im Viewer auswählbar. Rechtsklick-Aktionen funktionieren weiterhin pro einzelner Gruppe und auch gruppenübergreifend bei Mehrfachauswahl:

- zu Kategorie hinzufügen
- vom Dateinamen ausschließen
- Filename-Ausschluss entfernen
- Alias bearbeiten
- manuellen Score bearbeiten
- Tags kopieren
- als Query nutzen

## Dateinamen-Pattern

Der Dateiname kann über Platzhalter definiert werden, zum Beispiel:

```text
%artists%_%character%_%general%_%postID%
```

Unterstützte Platzhalter:

```text
%artist%
%artists%
%character%
%characters%
%copyright%
%copyrights%
%series%
%serie%
%general%
%meta%
%tags%
%postid%
%postID%
%id%
%hash%
%ext%
```

Zusätzlich bleiben alte `{id}`-/`{tags}`-/`{hash}`-/`{ext}`-Platzhalter kompatibel.

## Config / SQLite

Im Konfigurationstab gibt es jetzt den Abschnitt `Dateiname`.

Gespeicherte SQLite-Keys:

```text
filename.pattern
filename.tags_count
filename.max_length
filename.hash_length
```

Beispiel in YAML bzw. Runtime-Config:

```yaml
filename:
  pattern: "%artists%_%characters%_%general%_%postid%"
  max_length: 180
  tags_count: 8
  hash_length: 8
  excluded_tags: []
```

`%general%` nutzt höchstens `filename.tags_count` General-Tags. Filename-Excludes aus SQLite werden beim finalen Speichern berücksichtigt.

## Geänderte Dateien

```text
app/core/config.py
app/core/filename_builder.py
app/gui/config_tab.py
app/gui/image_viewer.py
app/gui/tag_display.py
docs/README_TYPED_TAGS_FILENAME_PATTERN_1_3_9.md
```
