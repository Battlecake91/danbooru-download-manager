# 1.3.68 Viewer Performance Cache

Dieser Patch reduziert die Wartezeit beim Bildwechsel im Viewer.

## Ursache

Der Performance-Test aus 1.3.67 zeigte klar:

- `category_influence`: ca. 700-800 ms
- `tags_metadata`: ca. 230-275 ms
- Bildladen: deutlich kleiner, ca. 27-84 ms

Der Engpass lag also in synchronen DB-/Statistikabfragen im GUI-Thread, nicht primär beim Laden des Bildes.

## Änderungen

### Kategorie-Einfluss-Cache

`CategoryEngine` cached Kategorie/Tag-Treffer pro Original-Tag im RAM.

Beim ersten Vorkommen eines Tags werden dessen historischen Kategorie-Treffer aus SQLite geladen. Danach werden die gleichen Treffer für weitere Posts wiederverwendet.

Das hilft besonders bei häufigen Tags, die über viele Bilder hinweg erneut vorkommen.

### Leichte Tag-Metadaten für den Viewer

Der Viewer nutzt jetzt `fetch_tag_display_metadata()` statt der schweren `fetch_tag_metadata()`.

Die neue Methode lädt nur direkte Tag-Einstellungen:

- Alias / Canonical Tag
- LLM-Token
- manueller Score
- gespeicherter computed Score
- Filename-Exclude
- Ignore-Flags

Sie berechnet nicht mehr bei jedem Bildwechsel historische Aggregationen über alle bekannten Posts.

### DB-Indizes

Zusätzliche sichere Indizes wurden ergänzt für häufige Join-Pfade:

- `post_tags(tag, post_id)`
- `post_tags(post_id, tag)`
- `post_categories(post_id, category_id)`
- `post_categories(category_id, post_id)`
- `post_reviews(post_id)`
- `tag_scores(tag)`
- `tag_aliases(original_tag)`
- `filename_excluded_tags(tag)`

## Cache-Invalidierung

Der Kategorie-Einfluss-Cache wird im Viewer geleert, wenn dort relevante Daten geändert werden:

- manuelle Kategorie-Zuordnung
- Scoring-Flags
- Alias
- manueller Score

Änderungen aus anderen Tabs können im laufenden Viewer noch bis zur nächsten Cache-Leerung veraltet wirken. Das ist für diesen Performance-Patch bewusst einfach gehalten.

## Erwartung

Nach den ersten paar Bildern sollten `category_influence` und `tags_metadata` deutlich fallen.

Der Performance-Test aus 1.3.67 bleibt erhalten. Zum Prüfen:

1. Viewer öffnen
2. `Perf` aktivieren
3. mehrere Bilder weiterklicken
4. `logs/viewer_performance.log` prüfen
