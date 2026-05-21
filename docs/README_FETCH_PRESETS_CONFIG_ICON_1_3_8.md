# Danbooru Manager 1.3.8 - Fetch-Presets, Credentials und Icon

## Änderung 1: Such-Tags raus aus der allgemeinen Konfiguration

Der Config-Tab zeigt keine Such-Tags, Saved-Search-Queries oder Rating-Filter mehr.

Diese Dinge gehören jetzt ausschließlich in:

```text
Fetch / Suche → Presets
```

Endlich keine Suchlogik mehr im allgemeinen Config-Sumpf. Ein winziger Sieg gegen Chaos, diese klebrige Lieblingssubstanz der Softwareentwicklung.

## Änderung 2: Fetch-Seite überarbeitet

Der Tab `Fetch / Suche` arbeitet jetzt so:

```text
Preset auswählen
→ Felder werden automatisch gefüllt
→ optional Felder ändern
→ Fetch starten
```

Oder:

```text
Manuell / aktuelle Felder
→ Felder selbst ausfüllen
→ Fetch starten
```

## Preset-Felder

```text
Name
Modus: tags oder saved_searches
Tags / Query
Saved-Search-Labels
Saved-Search-Queries
Zusatz-Tags
limit
max_posts_per_query
max_total_posts
```

## Beispielpresets

```yaml
fetch_presets:
  - name: "Saved Searches: default"
    mode: "saved_searches"
    saved_search_labels:
      - "default"
    extra_tags: ""

  - name: "Tags: 1girl cute smile"
    mode: "tags"
    query: "1girl cute smile"
    extra_tags: "( rating:s or rating:q )"
```

## Presets speichern

Presets werden in SQLite gespeichert:

```sql
app_settings.key = 'fetch.presets'
```

## Änderung 3: Username und API-Key im Config-Tab

Im Config-Tab gibt es jetzt:

```text
Danbooru Login
- Username
- API-Key
- API-Key anzeigen
```

Der API-Key wird im UI als Passwortfeld angezeigt.

Gespeichert wird er in SQLite `app_settings`. Das ist lokal und bequem, aber kein Hochsicherheitstresor. Dateirechte zählen, weil Magie leider ausverkauft ist.

## Änderung 4: Danbooru-Icon

Die GUI nutzt das Danbooru-Icon:

```text
https://upload.wikimedia.org/wikipedia/commons/b/b5/Danbooru_icon.png
```

Wenn `app_icon_file` nicht gesetzt ist, wird das Icon beim Start nach:

```text
<work_dir>/assets/danbooru_icon.png
```

geladen und als Fenster-/App-Icon verwendet.

## Geänderte Dateien

```text
app/gui/app_window.py
app/gui/main_window.py
app/gui/fetch_tab.py
app/gui/config_tab.py
config.example.yaml
```

## Neue Datei

```text
app/gui/icon_utils.py
```
