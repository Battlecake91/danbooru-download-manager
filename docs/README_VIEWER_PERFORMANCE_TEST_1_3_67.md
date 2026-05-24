# 1.3.67 - Viewer-Performance-Test

Dieser Patch ergänzt im Bildbetrachter eine einfache Performance-Messung für den Bildwechsel.

## Bedienung

Im Viewer gibt es in der Toolbar eine neue Checkbox:

```text
Perf
```

Wenn sie aktiv ist, schreibt jeder Bildwechsel eine Messzeile in:

```text
<work_dir>/logs/viewer_performance.log
```

Zusätzlich wird dieselbe Zeile auf stdout ausgegeben, damit sie auch in der Konsole bzw. im Journal sichtbar ist.

## Gemessene Abschnitte

Die Logzeile enthält unter anderem:

```text
[PERF][viewer] post=123456 total=1420.0ms get_post_detail=3.2ms get_related_posts=8.1ms category_suggest=40.5ms category_influence=820.4ms tags_metadata=310.7ms ensure_image_path=20.1ms qpixmap_load=110.2ms refresh_image=95.8ms
```

Wichtige Felder:

- `total`: komplette Dauer des Bildwechsels
- `get_post_detail`: Laden der Postdaten
- `get_related_posts`: Parent-/Child-Abfrage
- `related_local_paths`: Prüfung lokaler Related-Dateien
- `category_suggest`: harte Kategorie-Regel / Vorschlag
- `category_influence`: Tag-Hinweis / Einfluss-Scoring
- `category_list`: Kategorien laden
- `final_path_preview`: Dateiname-/Zielpfad-Vorschau
- `tags_typed`: typisierte Tags laden
- `tags_filename_exclude`: Filename-Exclude-Set laden
- `tags_metadata`: Alias, Score, Ignore-Flags und weitere Tag-Metadaten laden
- `tags_widget_ui`: Taglisten im UI befüllen
- `ensure_image_path`: lokalen Bildpfad finden oder Original laden
- `qpixmap_load`: Bilddatei in QPixmap laden
- `refresh_image`: Bild skalieren und anzeigen

## Konfiguration

Optional kann die Messung über die Viewer-Konfiguration vorbereitet werden:

```python
"viewer": {
    "performance": {
        "enabled": true,
        "threshold_ms": 0
    }
}
```

- `enabled`: Checkbox beim Öffnen des Viewers aktivieren
- `threshold_ms`: nur Logzeilen ab dieser Gesamtdauer schreiben; `0` schreibt alles

## Zweck

Der Patch optimiert noch nichts. Er zeigt nur, welcher Teil des Bildwechsels langsam ist. Erst danach sollte gezielt optimiert werden, zum Beispiel Kategorie-Influence-Cache, zusätzliche DB-Indizes oder Lazy Loading für schwere Tag-Metadaten.
