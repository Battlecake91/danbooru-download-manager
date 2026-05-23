# 1_3_47 Kategorie-Tab poliert

Dieses Patch-ZIP enthält nur die geänderten Dateien.

## geändert

- `app/gui/category_tab.py`

## neu im Kategorie-Tab

- linke Seite zeigt eine kompaktere Kategorie-Liste
- rechte Seite ist in Bereiche aufgeteilt:
  - Kategorie
  - Regeln schnell bearbeiten
  - Regeln dieser Kategorie
- ID- und technische Spalten sind ausgeblendet
- Zielpfad und Sortierung sind als erweiterte Felder ein-/ausblendbar
- Regeln können schneller gesetzt werden:
  - Tag(s) eingeben
  - `+ Muss enthalten`
  - `+ Ausschließen`
- mehrere Tags können gleichzeitig eingefügt werden, getrennt durch Leerzeichen, Komma oder Semikolon
- Tag-Eingabefeld hat Autovervollständigung aus lokal bekannten Tags
- Regeln werden verständlicher angezeigt:
  - `include` -> `Muss enthalten`
  - `exclude` -> `Darf nicht enthalten`
- mehrere Regeln können markiert und zusammen gelöscht werden
- alle Regeln einer Kategorie können per Button gelöscht werden
- Tabellenköpfe sind sortierbar

## unverändert

Die Datenbankstruktur bleibt gleich. Bestehende Kategorien und Regeln werden nicht migriert oder verändert.
