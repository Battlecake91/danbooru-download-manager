# 1.3.58 - Kategorie-Einfluss normalisiert

Dieser Patch korrigiert die interne Kategoriebeeinflussung aus 1.3.57.

## Problem

Der erste Einfluss-Score hat rohe Trefferhäufigkeiten stark belohnt. Dadurch konnten sehr allgemeine Tags wie `1girl`, `solo` oder andere häufige Tags die Kategorie mit den meisten historischen Beispielen fast immer zur stärksten Einfluss-Kategorie machen.

Das war technisch berechenbar, aber praktisch falsch: Die größte Kategorie gewann, nicht die passendste.

## Änderung

Der Einfluss wird nun nicht mehr primär aus absoluten Treffern gebildet, sondern aus normalisierten Kennzahlen:

- Trefferanteil des Tags innerhalb der Kategorie
- globaler Trefferanteil des Tags über alle kategorisierten Beispiele
- Lift: Ist der Tag für diese Kategorie überdurchschnittlich typisch?
- Dämpfung für sehr verbreitete Tags
- gesättigte Unterstützung per `log1p(hit_count)` statt linearer Trefferzählung
- kleine Korrektur durch gespeicherte Beispiele, Rating und Tag-Score

Allgemeine Tags liefern dadurch nur noch schwache Hinweise. Spezifische Tags, die für eine Kategorie wirklich typisch sind, gewinnen stärker.

## UI-Anpassung

Im Viewer wird der Zahlenwert nicht mehr direkt in der Kategoriezeile angezeigt.

Vorher:

```text
Kategorie: Vorschlag xx | Einfluss: ll +674.000
```

Jetzt:

```text
Kategorie: Vorschlag xx | Tag-Hinweis: ll
```

Der genaue Score bleibt im Details-Dialog sichtbar.

## Geänderte Dateien

```text
app/core/category_engine.py
app/core/database.py
app/gui/image_viewer.py
docs/README_CATEGORY_INFLUENCE_NORMALIZED_1_3_58.md
```
