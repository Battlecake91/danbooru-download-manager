# 1.3.76 Viewer: markierte General-/Meta-Tags besser lesbar

## Problem

Im Viewer wurden markierte General- und Meta-Tags mit einem farbigen Auswahlhintergrund angezeigt, aber die eingebetteten Label-Zeilen behielten ihre normale Schriftfarbe.

Dadurch konnte bei markierten General-/Meta-Tags die Schrift nahezu dieselbe Farbe wie der Auswahlhintergrund haben.
Artist, Serie/Copyright und Character waren nicht betroffen, weil diese Gruppen normale `QListWidgetItem`-Texte verwenden und die Stylesheet-Regel für `QListWidget::item:selected` dort sauber greift.

## Änderung

- Für General- und Meta-Zeilen wird bei Auswahl die Schriftfarbe der eingebetteten Labels auf Schwarz gesetzt.
- Beim Abwählen wird die normale Farbe wiederhergestellt:
  - Tag-Name: jeweilige Typfarbe
  - Detailspalten: hellgrau
- Artist, Serie/Copyright und Character bleiben unverändert.

## Technische Notiz

General und Meta nutzen `setItemWidget()` mit eigenen `QLabel`-Widgets. Qt übernimmt die `QListWidget::item:selected`-Textfarbe nicht automatisch auf eingebettete Widgets. Deshalb synchronisiert `TypedTagListWidget` die Label-Farben jetzt über `itemSelectionChanged`.

## Geänderte Dateien

- `app/gui/tag_display.py`
