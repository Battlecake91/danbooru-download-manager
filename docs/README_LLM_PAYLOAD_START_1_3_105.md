# 1.3.105 - LLM-Integration Start: Payload statt Blindflug

Dieser Patch entfernt die Preview-Funktion **Kategorie-Details**, weil sie im Workflow keinen echten Nutzen bringt.

## Neu

### Previewer

- Neuer Button: **LLM-Payload**
- Rechts oben neben den normalen Aktionen.
- Erzeugt für die aktuell ausgewählten Preview-Posts eine JSON-Payload.
- Die Payload wird in einem Dialog angezeigt und kann in die Zwischenablage kopiert werden.
- Es wird noch nichts automatisch an einen LLM-Anbieter gesendet.

Das ist absichtlich die erste Stufe, damit der Prompt und die exportierten Tags kontrollierbar bleiben, bevor ein Modell anfängt, selbstbewusst Unsinn zu würfeln.

### Konfiguration

Im Tab **Scoring** gibt es nun grundlegende LLM-Einstellungen:

- LLM aktivieren
- Backend: `none`, `openai_compatible`, `local`
- Endpoint-URL
- Modell
- API-Key-Umgebungsvariable
- Timeout
- Posts pro Request
- Tags pro Post
- optionaler System-Prompt
- Tag-Export-Modus: Original, Alias oder gehashte Alias-Tags
- Hash-Prefix und Hash-Länge
- optionale Tag-Legende

Die Werte werden wie die restliche Konfiguration in `app_settings` gespeichert.

## Payload-Inhalt

Die Payload enthält:

- Aufgabe: `danbooru_post_preselection`
- erwartetes Antwortschema
- verfügbare Kategorien
- pro Post:
  - Post-ID
  - Rating
  - Danbooru-Score
  - Status
  - lokale Bewertung
  - bisherige Kategorie
  - lokalen Vorauswahl-Score
  - positive/negative lokale Signale
  - exportierte Tags

Tags mit `ignore_llm_input` werden ausgelassen. Der bestehende Privacy-Pfad über Alias und Salted Hash wird weiterverwendet.

## Entfernt

- Button **Kategorie-Details** im Previewer
- Kontextmenüpunkt **Kategorie-Details anzeigen**
- Previewer-Signalpfad für Kategorie-Details

## Nächster sinnvoller Schritt

Danach kann ein Worker ergänzt werden, der diese Payload tatsächlich an einen konfigurierten OpenAI-kompatiblen oder lokalen Endpunkt sendet und die Antwort als `llm_score` / Kategorie-Vorschlag zurück in die Datenbank schreibt.
