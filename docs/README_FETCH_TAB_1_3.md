# Danbooru Manager 1.3 - Fetch / Suche Tab

## Neu

Die GUI hat jetzt als ersten Tab:

```text
Fetch / Suche
```

Dort können neue Posts direkt aus der GUI geladen werden.

## Funktionen

- vordefinierte Fetch-Presets
- manuelle Tag-Query
- optionale Zusatz-Tags
- Saved-Search-Modus
- API-Limit
- Max Posts pro Query
- Max Posts gesamt
- Fetch läuft in einem QThread
- nach Fetch wird Preview aktualisiert und geöffnet

## Geänderte Dateien

```text
app/gui/app_window.py
config.example.yaml
```

## Neue Datei

```text
app/gui/fetch_tab.py
```

## Config-Ergänzung

```yaml
fetch_presets:
  - name: "Standard: Config Query"
    mode: "tags"
    query: "order:id_desc"
    extra_tags: "( rating:q or rating:e )"
    limit: 100
    max_posts_per_query: 500
    max_total_posts: 1000

  - name: "Saved Searches: explicit/questionable"
    mode: "saved_searches"
    saved_search_labels: []
    saved_search_queries: []
    extra_tags: "( rating:q or rating:e )"
    limit: 100
    max_posts_per_query: 500
    max_total_posts: 1000
```

## Modi

### `tags`

Nutzt direkte Danbooru-Tag-Suche:

```yaml
mode: "tags"
query: "blonde_hair order:id_desc"
extra_tags: "( rating:q or rating:e )"
```

Daraus wird:

```text
blonde_hair order:id_desc ( rating:q or rating:e )
```

### `saved_searches`

Nutzt gespeicherte Danbooru-Suchen:

```yaml
mode: "saved_searches"
saved_search_labels: []
saved_search_queries: []
extra_tags: "( rating:q or rating:e )"
```

## Manuelle Suche

Im Tab kann "Manuelle Query verwenden statt Preset" aktiviert werden.

Dann gelten:

- Tags / Query
- Zusatz-Tags

und Preset/Saved-Search-Auswahl wird ignoriert.

## Hinweis

Der Fetch läuft in einem Worker-Thread, damit die GUI nicht blockiert.
SQLite wird dabei mit derselben DB-Instanz benutzt. Das funktioniert meistens, solange der bestehende Code nicht bewusst Thread-Sperren nutzt.
Falls SQLite meckert, muss der Worker eine eigene DB-Verbindung öffnen.
