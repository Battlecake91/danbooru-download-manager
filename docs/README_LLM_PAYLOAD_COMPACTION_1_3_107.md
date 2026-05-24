# 1.3.107 - LLM Payload Compaction + Confidence

Dieser Patch macht den LLM-Payload kleiner und aussagekraeftiger.

## Aenderungen

- Payload-Schema auf `schema_version: 3` angehoben.
- `known_tag_preferences` enthaelt jetzt zusaetzlich:
  - `confidence`
  - `conflict`, falls manuelle Bewertung und Historie gegeneinander laufen
- Schwache, nicht hilfreiche Tag-Praeferenzen werden aus dem Payload entfernt.
- Kategorieprofile enthalten `profile_confidence`:
  - `high`
  - `medium`
  - `low`
  - `very_low`
- Sehr schwache Kategorieprofile mit weniger als 5 gespeicherten Posts senden keine grossen Top-Tag-Listen mehr.
- Beispielposts werden gekuerzt:
  - Standard: maximal 30 Tags je Beispiel
  - Prioritaet fuer Tags im aktuellen Batch, starke Preference-Tags und Kategorieprofil-Tags
- Neuer Payload-Block `payload_stats` zeigt, wie stark der Payload kompaktiert wurde.

## Neue Konfiguration

```text
llm.max_example_tags: 30
```

Im Konfigurations-Tab gibt es dazu das Feld `Tags/Beispiel`.

## Zweck

Die LLM soll weniger JSON-Ballast bekommen und staerkere Signale klarer erkennen.
Vorher bekam sie viele neutrale oder widerspruechliche Rohdaten. Jetzt bekommt sie weniger Daten,
aber mit Confidence- und Conflict-Hinweisen. Ja, weniger Laerm hilft manchmal. Welch Ketzeridee.
