# 1.3.75 Preview: Vorauswahl-Filter und Score-Zusammenfassung

Dieser Patch ergänzt den Previewer um einen direkten Filter für den lokalen Vorauswahl-Score.

## Neu

- Toolbar-Option `Vorauswahl ≥`
- Mindestwert per Spinbox einstellbar
- Filter ist nur aktiv, wenn die Checkbox aktiviert ist
- Trefferliste wird nach Kategorie- und Vorauswahlfilter gemeinsam gefiltert
- Infozeile zeigt jetzt zusätzlich:
  - aktiven Vorauswahlfilter
  - Anzahl positiver, neutraler und negativer Scores
  - Durchschnitt
  - besten und schlechtesten Score im geladenen Trefferbereich

## Verhalten

Der Score-Filter arbeitet auf dem bereits berechneten lokalen Vorauswahl-Score aus `RecommendationEngine`.

Tags mit `ignore_recommendation_score` bleiben weiterhin aus dem Score herausgerechnet.

## Ziel

Bei vielen Thumbnails kann schneller nur auf gute Kandidaten eingeschränkt werden, ohne direkt LLM-Scoring zu benötigen.
