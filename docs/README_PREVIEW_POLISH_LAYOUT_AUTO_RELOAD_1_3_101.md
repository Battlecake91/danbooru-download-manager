# 1.3.101 - Preview-Polish: Toolbar, Statistik, Auto-Reload

## Konfiguration / GUI

- Der Bereich `Preview-Karten-Inhalte` steht im GUI-Konfigurationstab jetzt neben der echten Preview-Karte statt darunter.
- Die Preview-Einstellungen und die Karteninhalt-Checkboxen sind damit auf breiten Displays deutlich besser nutzbar.

## Previewer

- Die bisher zu breite obere Werkzeugleiste wurde in drei Toolbars aufgeteilt:
  1. Aktionen: `Neu laden`, `Thumbnail neu laden`, `Speichern`
  2. Filter: Ansicht, Status, Kategorie, Vorauswahl und Suche
  3. Sortierung: Sortierung, Limit und Thumbnail-Größe
- `Final speichern (F)` heißt in der Leiste jetzt kurz `Speichern`, der Hotkey-Hinweis steht im Tooltip.

## Statistik

- Die Infozeile zeigt jetzt übersichtlicher:
  - `Angezeigt: X/Y`
  - `Basis-Treffer`
  - Ansicht, Status, Kategorie, Vorauswahlfilter, Sortierung und Thumbnailgröße
  - Vorauswahl-Statistik als `Best`, `Worst`, `Average`
- Bei Python-seitig berechneten Filtern wie Kategorie oder Vorauswahl wird bis zu einer internen Obergrenze analysiert. Falls mehr Treffer existieren, wird ein `+` an der Trefferzahl angezeigt.

## Automatisches Nachladen

Der Previewer lädt jetzt automatisch neu bei Änderungen an:

- Ansicht
- Status-Checkboxen
- Kategorie
- Vorauswahlfilter
- Sortierung
- Limit

Suche kann weiterhin über Enter oder den Button `Suchen` gestartet werden, damit nicht bei jedem getippten Zeichen sofort die Datenbank gequält wird. Die hat auch Gefühle, vermutlich schlechte.
