# 1_3_53 Kategorie-Entscheidung im Viewer

Dieses Patch verschiebt die Kategorie-Diagnose aus dem Kategorie-Tab in den Viewer.

## Viewer

Neben der Kategorieauswahl gibt es jetzt den Button:

```text
Warum?
```

Der Button öffnet ein separates Fenster mit der Begründung der automatischen Kategorie-Entscheidung für den aktuell geladenen Post.

Angezeigt wird:

- aktuell im Viewer gewählte Kategorie
- automatische Gewinner-Kategorie
- weitere passende Kategorien weiter unten
- pro Kategorie:
  - globale Bedingungen
  - passende und nicht passende ODER-Gruppen
  - fehlende Tags
  - blockierende Ausschlüsse

## Kategorie-Tab

Der Kategorie-Test wurde aus dem Kategorie-Tab entfernt. Der Tab bleibt für Regelpflege und Kategorie-Reihenfolge zuständig.

## Technik

Die Diagnose-Logik liegt jetzt zentral in `app/core/category_engine.py`, damit Viewer und spätere Funktionen dieselbe Auswertung verwenden können.
