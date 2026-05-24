# 1.3.108 - LLM-Batch-Vorauswahl nach Fetch

Dieser Patch verdrahtet die LLM-Vorauswahl mit dem Fetch-Workflow.

## Ziel

Ein Fetch erzeugt nicht mehr gedanklich einen Prompt pro Post. Neue oder potentielle Posts werden gesammelt und in Batches mit `llm.max_posts_per_request` verarbeitet.

## Neue Konfiguration

```text
llm.run_after_fetch
llm.skip_already_scored
llm.after_fetch_statuses
```

Im Konfigurations-Tab gibt es unter Scoring / LLM jetzt:

```text
Nach Fetch: Nach Fetch als Batch vorsortieren
Bereits LLM-bewertete Posts überspringen
```

## Ablauf

Nach dem Fetch:

1. Der Worker sammelt die neuen Post-IDs.
2. Die IDs werden auf Status `new` / `potential` gefiltert.
3. Bereits LLM-bewertete Posts werden optional übersprungen.
4. Die Kandidaten werden in Batch-Payloads aufgeteilt.
5. Die Payloads werden in `app_settings` unter `llm.last_fetch_payloads` gespeichert.
6. Wenn LLM deaktiviert ist oder Backend `none` ist, endet der Lauf hier.
7. Wenn LLM aktiv ist und ein Backend gesetzt ist, werden die Batches gesendet.
8. Entscheidungen werden in `posts` gespeichert.

## Neue DB-Felder

```text
posts.llm_decision
posts.llm_category
posts.llm_reason
posts.llm_model
posts.llm_reviewed_at
```

`posts.llm_score` existierte bereits und wird weiter genutzt.

## Unterstützte Backends

### openai_compatible

Sendet an `<endpoint_url>/chat/completions`, außer `endpoint_url` endet bereits auf `/chat/completions`.

Erwartet eine Antwort mit:

```json
{
  "posts": [
    {
      "post_id": 123,
      "score": 42,
      "decision": "keep",
      "category": "soft",
      "reason": "Kurze Begründung"
    }
  ]
}
```

### local

Sendet an `endpoint_url`:

```json
{
  "model": "...",
  "payload": { ... }
}
```

Akzeptiert Antworten mit `posts`, `content` oder `response`.

## Previewer

Neue Sortierungen:

```text
LLM-Score: hoch → niedrig
LLM-Score: niedrig → hoch
```

## Wichtig

Die LLM-Entscheidung ändert noch nicht automatisch den Workflow-Status und speichert keine Kategorie final. Sie wird als Vorschlag gespeichert. Status-Automatik kommt erst später, wenn das Verhalten geprüft ist. Weil Maschinen nicht direkt die Schlüssel für den Panikraum bekommen.
