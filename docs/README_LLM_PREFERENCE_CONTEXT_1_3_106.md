# 1.3.106 - LLM Preference Context

Dieser Patch erweitert die LLM-Payload um lokale Bewertungs- und Geschmackshistorie.

## Warum

Die bisherige Payload enthielt pro Post Tags und Metadaten. Damit konnte die LLM nur anhand des aktuellen Posts raten. Jetzt bekommt sie zusätzlich einen kompakten Kontext aus bisherigen Entscheidungen.

## Neu in der Payload

Die Payload nutzt jetzt `schema_version: 2` und enthält optional:

```json
"preference_context": {
  "summary": { ... },
  "known_tag_preferences": [ ... ],
  "category_profiles": [ ... ],
  "examples": {
    "liked": [ ... ],
    "rejected": [ ... ],
    "by_category": [ ... ]
  }
}
```

### Enthaltene Informationen

- Gesamtzahl lokaler Posts
- Anzahl gespeicherter und abgelehnter Posts
- Anzahl bewerteter Posts
- Durchschnittliche persönliche Bewertung
- Stärkste positive und negative Tag-Signale
- Aktuelle Batch-Tags mit bereits bekannter Historie
- Kategorieprofile mit häufigen positiven Tags
- Kleine Beispielmengen aus gespeicherten und abgelehnten Posts

Die Tags werden weiterhin über den eingestellten LLM-Exportmodus ausgegeben:

- Original-Tags
- Alias/Canonical-Tags
- gehashte Alias-Tags

Wenn `Tag-Legende an LLM mitsenden` aktiv ist, werden zusätzliche Klartext-/Canonical-Hinweise ergänzt. Sonst bleibt der Privacy-Modus erhalten.

## Neue Konfigurationswerte

```text
llm.include_preference_context
llm.max_preference_tags
llm.max_positive_examples
llm.max_negative_examples
llm.max_category_examples
```

Diese Werte sind im Konfigurations-Tab unter `Scoring / LLM-Tag-Privacy` bearbeitbar.

## Nebenfix

Die lokalen Empfehlungssignale pro Post werden jetzt aus den echten lokalen Tags berechnet, nicht aus bereits exportierten/gehashten LLM-Tokens. Sonst findet der lokale Scorer bei `tag_abcdef...` exakt gar nichts. Sehr überraschend, außer für jeden, der schon einmal eine Hashfunktion gesehen hat.
