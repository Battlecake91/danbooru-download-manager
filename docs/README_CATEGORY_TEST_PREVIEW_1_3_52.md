# Danbooru Downloader 1.3.52 - Kategorie-Test / Vorschau

Dieses Patch-ZIP enthält nur geänderte Dateien.

## Geändert

- `app/gui/category_tab.py`

## Kategorie-Buttons

Die Kategorie-Bedienung links ist jetzt zweizeilig angeordnet:

```text
↑ Kategorie hoch | ↓ Kategorie runter
Kategorie hinzufügen | Kategorie speichern | Kategorie löschen
```

Die Kategorie-Reihenfolge bleibt dabei weiterhin die wirksame Priorität: oben gewinnt.

## Kategorie-Test / Vorschau

Im Kategorie-Tab gibt es nun unten rechts einen Bereich **Kategorie-Test / Vorschau**.

Damit kann geprüft werden, welche Kategorie bei einem bestimmten Post oder bei manuell eingegebenen Tags gewinnen würde.

### Post-ID prüfen

```text
Post-ID testen -> Post prüfen
```

Die Tags werden aus der lokalen Datenbank geladen und gegen alle Kategorien geprüft.

### Tags manuell prüfen

```text
tag1 tag2 -tag3 -> Tags prüfen
```

Positive Tags werden als vorhandene Tags getestet. Negative Tags mit `-` werden beim manuellen Test als abwesend/ignoriert behandelt.

## Ergebnisanzeige

Die Vorschau zeigt:

- Gewinner-Kategorie
- weitere passende Kategorien weiter unten
- Hinweis, dass die erste passende Kategorie gewinnt
- pro Kategorie:
  - erfüllte und fehlende globale Bedingungen
  - erfüllte und fehlende ODER-Gruppen
  - blockierende Ausschluss-Tags

Damit lässt sich nachvollziehen, warum eine Kategorie greift oder warum sie blockiert wird.
