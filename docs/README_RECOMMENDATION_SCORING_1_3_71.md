# 1.3.71 - Vorauswahl-Scoring ohne LLM

Dieser Patch ergänzt eine lokale, deterministische Vorauswahlwertung für Preview-Karten.

## Neu

- Neues Modul `app/core/recommendation_engine.py`.
- Preview-Karten zeigen `Vorauswahl: +x` bzw. negative Werte an.
- Tooltip der Vorauswahl zeigt die stärksten positiven und negativen Tag-Beiträge.
- Die Preview-Sortierung enthält:
  - `Vorauswahl: hoch → niedrig`
  - `Vorauswahl: niedrig → hoch`

## Bewertungslogik

Die lokale Vorauswahl nutzt vorhandene Tag-Scores:

- manueller Score, falls vorhanden
- sonst gespeicherter berechneter Score
- `scoring_excluded` wird ignoriert
- `ignore_recommendation_score` wird ignoriert
- Aliase/Canonical-Tags werden berücksichtigt, damit Varianten nicht mehrfach zählen

## Wichtig

Das ist noch keine LLM-Bewertung. Es ist nur der lokale Basisscore, auf dem spätere LLM-/Vorauswahlfunktionen aufbauen können.

## Geänderte Dateien

- `app/core/recommendation_engine.py`
- `app/gui/preview_window.py`
- `app/gui/thumbnail_grid.py`
