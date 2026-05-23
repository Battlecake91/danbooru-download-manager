# 1.3.62 - Tag-Tab: Bulk-Kontextmenü für Scoring/Nutzung

Diese Version bringt die Scoring-/Nutzungsflags im Tag-Tab gezielt ins Kontextmenü zurück.

## Hintergrund

In 1.3.60/1.3.61 wurden viele Optionen direkt in der Tag-Tabelle bearbeitbar:

- Filename-Exclude per Klick
- Kategorie-Hinweis ignorieren per Klick
- Vorauswahl ignorieren per Klick
- LLM-Eingabe ignorieren per Klick
- Alias direkt in der Alias-Spalte
- manueller Score direkt in der Score-Spalte

Das ist für Einzelwerte angenehm, aber bei Mehrfachauswahl unpraktisch, wenn man nicht exakt in eine der Optionsspalten klicken will.

## Neu

Im Tag-Tab gibt es wieder ein gezieltes Kontext-Untermenü:

```text
Scoring / Nutzung
├─ Kategorie-Hinweis ignorieren
├─ Kategorie-Hinweis wieder nutzen
├─ Vorauswahl ignorieren
├─ Vorauswahl wieder nutzen
├─ LLM-Eingabe ignorieren
├─ LLM-Eingabe wieder nutzen
├─ Alle automatischen Bewertungen ignorieren
└─ Alle automatischen Bewertungen wieder nutzen
```

Die Aktionen gelten für alle markierten Tags.

## Weiterhin gültig

Die direkten Zellaktionen bleiben erhalten:

- Klick in `Filename-Exclude` toggelt Filename-Ausschluss.
- Klick in `Kat.-Scoring ignoriert` toggelt Kategorie-Hinweis-Ignore.
- Klick in `Vorauswahl ignoriert` toggelt Vorauswahl-Ignore.
- Klick in `LLM ignoriert` toggelt LLM-Input-Ignore.
- Alias und manueller Score bleiben direkt in der Tabelle editierbar.

## Verhalten bei Mehrfachauswahl

Wenn mehrere Tags markiert sind und eine Kontextmenüaktion ausgelöst wird, wird die Änderung auf alle markierten Tags angewendet.

Die sichtbaren Tabellenzellen werden lokal aktualisiert. Es wird kein vollständiges `reload_tags()` ausgeführt.
