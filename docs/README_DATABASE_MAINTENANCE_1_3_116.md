# 1.3.116 - Datenbank-Wartung und Größenanalyse

Dieser Patch ergänzt einen lazy geladenen Tab **Wartung** mit Werkzeugen zur Analyse und Bereinigung der lokalen SQLite-Datenbank.

## Neu

- Neuer Tab **Wartung** im Hauptfenster.
- Datenbankgrößenanalyse mit:
  - DB-Dateigröße
  - WAL-/SHM-Größe
  - SQLite-Page- und Freelist-Informationen
  - Zeilenzahlen wichtiger Tabellen
  - größte Tabellen/Indizes via `dbstat`, falls verfügbar
  - größte Einträge in `app_settings`
- Button **LLM-Debug-Payloads löschen**:
  - löscht `llm.last_fetch_payloads`
  - löscht `llm.last_fetch_payload_summary`
  - verändert keine gespeicherten LLM-Ergebnisse an Posts
- Button **WAL komprimieren**:
  - führt `PRAGMA wal_checkpoint(TRUNCATE)` aus
- Button **VACUUM ausführen**:
  - kompaktiert die eigentliche SQLite-Datei
  - sinnvoll, wenn `freelist_count` bzw. geschätzter freier Platz groß ist

## Warum

Die DB kann durch viele Posts, Tags, Indizes und Debug-Payloads schnell wachsen. Besonders `llm.last_fetch_payloads` kann große JSON-Blöcke enthalten und soll deshalb gezielt löschbar sein.

## Hinweis

`VACUUM` sollte nicht während Fetch/Import laufen. Es kann bei größeren Datenbanken eine Weile dauern.
