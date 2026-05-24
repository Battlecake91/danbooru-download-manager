# 1.3.109 - LLM Kategorie-Anonymisierung

Dieser Patch anonymisiert neben Tags jetzt auch Kategorien im LLM-Payload.

## Hintergrund

Vorher wurden Tags im Privacy-Modus als Hashes exportiert, Kategorien aber weiterhin im Klartext gesendet, zum Beispiel `ll`, `uncensored`, `soft`. Das war inkonsequent: Der Payload war damit zwar bei Tags pseudonymisiert, verriet aber weiterhin Teile der lokalen Sortierlogik.

## Änderungen

- Neue LLM-Konfiguration:
  - `llm.category_export_mode`: `hashed` oder `original`
  - `llm.category_hash_prefix`: Standard `cat_`
  - `llm.category_hash_length`: Standard `12`
  - `llm.include_category_legend`: Standard `false`
- `config.available_categories` enthält im Standardmodus jetzt anonymisierte Kategorie-IDs.
- `posts[].current_category` wird anonymisiert.
- `preference_context.category_profiles[].category` wird anonymisiert.
- `preference_context.examples.*[].category` wird anonymisiert.
- Die Standard-Instructions sagen der LLM jetzt explizit, dass `category` aus `config.available_categories` oder `null` kommen soll.
- Antworten der LLM werden vor dem Speichern wieder auf echte lokale Kategorien zurückgemappt.

## Beispiel

Statt:

```json
"available_categories": ["ll", "uncensored", "soft"]
```

steht im Privacy-Modus nun etwa:

```json
"available_categories": ["cat_a1b2c3d4e5f6", "cat_123456abcdef", "cat_fedcba654321"]
```

Wenn die LLM mit `cat_123456abcdef` antwortet, wird intern wieder auf die echte lokale Kategorie zurückgemappt und in `posts.llm_category` gespeichert.

## Hinweise

`include_category_legend` sollte nur zum Debuggen aktiviert werden. Dann enthält der Payload eine Map von anonymer Kategorie-ID auf Klartext-Kategorie. Praktisch, aber natürlich weniger privat. Wie immer: Tarnumhang auf, Schild dran, Schild schlecht.
