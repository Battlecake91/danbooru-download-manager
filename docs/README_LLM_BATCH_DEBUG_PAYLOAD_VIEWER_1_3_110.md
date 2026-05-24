# 1.3.110 - LLM Batch Debug und Payload Viewer

Dieser Patch macht den LLM-Batch-Workflow nach einem Fetch sichtbar und prüfbar.

## Änderungen

### Fetch-Log

Nach einem Fetch werden zusätzliche LLM-Diagnosezeilen ausgegeben:

- Eingangsposts für den LLM-Batch
- aktive Statusfilter
- ob bereits bewertete Posts übersprungen werden
- Kandidaten nach Filter
- Anzahl übersprungener Posts
- erzeugte Payloads/Batches
- Post-IDs je Batch

Damit ist sofort sichtbar, ob der Workflow wirklich mehrere Posts in einem Batch verarbeitet oder ob nur ein Einzelpost in der Payload landet.

### Fetch-Zusammenfassung

Die Fetch-Zusammenfassung enthält jetzt detailliertere LLM-Zeilen:

- Eingang
- Kandidaten
- übersprungen
- Batches
- Payloads
- Requests
- gespeicherte Entscheidungen
- die ersten Batch-IDs

### Previewer

Im Previewer gibt es einen neuen Button:

```text
Letzte LLM-Payloads
```

Der Dialog zeigt die zuletzt nach einem Fetch vorbereiteten Payloads aus:

```text
llm.last_fetch_payloads
```

Zusätzlich wird die Zusammenfassung aus:

```text
llm.last_fetch_payload_summary
```

angezeigt.

Der Dialog zeigt pro Payload:

- Payload-Index
- Post-Anzahl
- Post-IDs
- JSON-Payload
- Button zum Kopieren der aktuellen Payload
- Button zum Kopieren aller Payloads

## Zweck

Der Patch ändert nicht die LLM-Entscheidungslogik. Er macht nur sichtbar, wo Posts verloren gehen:

- direkt beim Fetch
- beim Statusfilter
- durch `skip_already_scored`
- beim Batching
- beim Speichern der letzten Payloads

Das ist absichtlich ein Diagnose-Patch, bevor API-Automatik und Übernahme von LLM-Vorschlägen weiter ausgebaut werden.
