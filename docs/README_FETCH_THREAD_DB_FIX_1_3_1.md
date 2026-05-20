# Danbooru Manager 1.3.1 - Fetch-Thread SQLite-Fix

## Problem

Beim Starten eines Fetch aus dem GUI-Tab kam:

```text
sqlite3.ProgrammingError:
SQLite objects created in a thread can only be used in that same thread.
```

## Ursache

Der GUI-Thread hatte die SQLite-Verbindung erstellt.
Der Fetch läuft aber in einem `QThread`.

SQLite-Verbindungen dürfen standardmäßig nur in dem Thread benutzt werden, in dem sie erstellt wurden.

Also:

```text
GUI-Thread erstellt db.connection
Worker-Thread benutzt db.connection
SQLite sagt: nö
```

Sehr kleinlich, aber technisch korrekt. Und damit leider nervig.

## Fix

`FetchWorker` bekommt nicht mehr die GUI-DB-Verbindung.

Stattdessen öffnet der Worker im eigenen Thread:

```python
worker_db = Database(Path(config["database_file"]))
worker_db.connect()
worker_db.initialize_schema()
```

Dann nutzt `PostImportService` diese Worker-DB:

```python
service = PostImportService(config, worker_db)
```

Am Ende wird sie geschlossen:

```python
worker_db.close()
```

Die GUI hat weiterhin ihre eigene DB-Verbindung.

## Geänderte Datei

```text
app/gui/fetch_tab.py
```

## Test

1. GUI starten
2. Tab `Fetch / Suche`
3. Preset `Saved Searches`
4. `Saved Searches verwenden` aktiv
5. `Fetch starten`

Erwartet:

- Kein SQLite-Threading-Fehler
- Fetch läuft
- Preview wird danach aktualisiert
