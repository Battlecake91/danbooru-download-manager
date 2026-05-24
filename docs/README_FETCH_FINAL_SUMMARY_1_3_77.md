# 1.3.77 Fetch-Abschlusszusammenfassung

Nach einem erfolgreichen Fetch schreibt der Fetch-Tab jetzt eine kompakte Zusammenfassung ins Log-/Textfeld.

Angezeigt werden:

- Queries verarbeitet / Queries gesamt
- geprüfte Posts
- neue Posts
- bekannte bzw. aktualisierte Posts
- geladene/aktualisierte Thumbnails

Zusätzlich bleibt unter dem Fortschrittsbalken nach dem Fetch eine einzeilige Kurzfassung sichtbar, bis der nächste Fetch gestartet wird.

Intern wurde `FetchResult` um `processed_queries` ergänzt, damit bei Limits wie `max_total_posts` sauber erkennbar bleibt, wie viele Queries tatsächlich bearbeitet wurden.
