# Patch 1.3.115 - Preview aufraeumen, LLM-Debug verschieben, Viewer-Steuerung stabilisieren

## Geaendert

- `app/gui/preview_window.py`
- `app/gui/config_tab.py`
- `app/gui/image_viewer.py`

## Previewer

- Die Buttons `LLM-Payload` und `Letzte LLM-Payloads` wurden aus der Previewer-Toolbar entfernt.
- Der Previewer bleibt damit wieder mehr Review-/Sortierflaeche statt Debug-Konsole mit Bildchen.

## Konfiguration / LLM-Debug

- Die LLM-Debug-Aktionen sitzen jetzt im LLM-Bereich der Konfiguration:
  - `LLM-Payload Beispielpost`
  - `Letzte Fetch-LLM-Payloads`
- `LLM-Payload Beispielpost` erzeugt eine Debug-Payload fuer die aktuell eingestellte GUI-Vorschau-Beispielpost-ID.
- Dabei werden die aktuellen Formularwerte verwendet, auch wenn sie noch nicht gespeichert wurden.
- `Letzte Fetch-LLM-Payloads` zeigt weiter die zuletzt nach Fetch erzeugten Batch-Payloads.

## Bildbetrachter

- Die Parent/Child-Anzeige verwendet jetzt `lokal gespeichert` statt `final gespeichert`.
- Die Navigation unter dem Bild ist stabiler:
  - Vorheriges-Button mit fester Breite
  - Positionsanzeige mit fester Breite
  - Naechstes-Button mit fester Breite
  - Die Navigationsgruppe bleibt links am persoenlichen Rating orientiert.
- Die Kategorie-Auswahl darf rechts weiter ihre Breite aendern, ohne die Navigationsbuttons dauernd herumzuschubsen. Kleine Gnade fuer jeden, der nicht gern UI-Fangen spielt.
