# 1.3.59 - Getrennte Scoring-Ignore-Flags

Dieser Patch ergänzt getrennte Ignore-Flags für automatisierte Tag-Nutzung.

## Neue Flags pro Tag

In `tag_scores` werden drei getrennte Spalten geführt:

- `ignore_category_influence`
- `ignore_recommendation_score`
- `ignore_llm_input`

Aktiv ausgewertet wird in diesem Patch nur `ignore_category_influence`.
Die anderen beiden Flags sind bewusst schon im Datenmodell und in der UI vorhanden,
damit Vorauswahl- und LLM-Logik später darauf aufbauen können, ohne wieder eine
Migration aus dem Boden zu prügeln.

## Tag-Tab

Der Tag-Tab zeigt neue Spalten:

- `Kat.-Scoring ignoriert`
- `Vorauswahl ignoriert`
- `LLM ignoriert`

Im Rechtsklick-Menü gibt es den neuen Bereich `Scoring / Nutzung` mit Aktionen für
Einzel- und Mehrfachauswahl:

- Für Kategorie-Hinweis ignorieren / wieder nutzen
- Für Vorauswahl ignorieren / wieder nutzen
- Für LLM-Eingabe ignorieren / wieder nutzen
- Für alle automatischen Bewertungen ignorieren / wieder nutzen

Die sichtbaren Zellen werden lokal aktualisiert. Es wird kein vollständiger
`reload_tags()` nach kleinen Änderungen ausgelöst.

## Ähnliche Tags bearbeiten

Der Dialog `Ähnliche Tags suchen/bearbeiten…` kann jetzt zusätzlich diese Flags setzen
oder zurücknehmen. Leere beziehungsweise auf `nicht ändern` stehende Felder bleiben
unverändert.

## Kategorie-Einfluss

`ignore_category_influence = 1` schließt den Tag komplett aus dem weichen
Kategorie-Hinweis aus. Das betrifft nur den Tag-Einfluss, nicht harte Kategorie-Regeln.

Beispiel: Wenn `1girl` ignoriert wird, kann eine explizite Kategorie-Regel mit `1girl`
trotzdem weiter greifen. Nur der statistische `Tag-Hinweis` nutzt diesen Tag nicht mehr.

Im Kategorie-Details-Dialog werden ignorierte Tags als
`Für Kategorie-Hinweis ignoriert` angezeigt.
