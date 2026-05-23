# 1.3.57 - Interne Kategoriebeeinflussung

Diese Version ergänzt eine weiche Kategoriebeeinflussung neben den harten Kategorie-Regeln.

## Verhalten

- Harte Kategorie-Regeln bleiben führend.
- Die neue Einflusswertung ersetzt noch keine Kategorie-Regel.
- Der Viewer zeigt beim Kategorie-Label und in der Kategorie-Combo den stärksten Einfluss an.
- Der Details-Dialog zeigt die Top-Einflüsse mit Score, Anzahl passender Tags und Beispieltreffern.

## Datenbasis

Die Bewertung nutzt:

- gespeicherte bzw. zugewiesene Kategoriebeispiele aus `post_categories`
- Tags dieser Beispielposts
- Alias-/Canonical-Tags, damit z. B. `red_hairband`, `blue_hairband` und `green_hairband` gemeinsam als `hairband` wirken können
- bestehende Tag-Scores und persönliche Ratings als leichte Verstärkung oder Dämpfung

## Absicht

Das ist die Grundlage für spätere LLM- oder interne Tag-Konstellationslogik. Erst sichtbar und erklärbar, danach kann entschieden werden, ob und wann der Einfluss wirklich automatisch Kategorien setzen darf.
