# 1.3.112 - LLM API-Key direkt in der App

Dieser Patch erlaubt, den API-Key fuer OpenAI-kompatible LLM-Backends direkt in der GUI zu hinterlegen.

## Geaendert

- Neuer Konfigurationswert: `llm.api_key`
- Im Konfigurations-Tab unter `Scoring / LLM-Tag-Privacy` gibt es jetzt ein maskiertes Feld `API-Key`.
- Das bestehende Feld `API-Key Env` bleibt als Fallback erhalten.
- Prioritaet beim Senden:
  1. `llm.api_key` aus der lokalen SQLite-Konfiguration
  2. Umgebungsvariable aus `llm.api_key_env`
- Wenn Backend `openai_compatible` aktiv ist und kein Key gefunden wird, gibt es jetzt eine klare Fehlermeldung statt eines spaeten 401-Fehlers.

## Hinweis

Der API-Key wird maskiert angezeigt und nicht in Logs geschrieben. Er liegt aber lokal in der SQLite-Konfiguration. Wer maximale Sicherheit will, nutzt weiterhin `API-Key Env`.
