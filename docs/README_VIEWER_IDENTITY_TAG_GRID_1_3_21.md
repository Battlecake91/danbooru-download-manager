# 1.3.21 - Viewer: gemeinsames Identity-Tagfeld

## Änderung

Artist, Serie / Copyright und Character hängen jetzt in einem gemeinsamen Grid statt in drei unabhängigen Widgets.

Aufbau:

- Zeile 1: Überschriften Artist / Serie-Copyright / Character
- Zeile 2: drei Tagkästchen mit identischer Höhe

Wenn eine der drei Gruppen zwei sichtbare Tags enthält, werden alle drei Kästchen gemeinsam auf zwei Zeilenhöhe gesetzt. Dadurch wirkt das Layout nicht mehr schief, wenn z. B. nur Character zwei Einträge hat.

## Technisch

Geändert:

- `app/gui/tag_display.py`

Details:

- neues gemeinsames `identity_group` mit `QGridLayout`
- Labels und Listen sitzen im gleichen Grid
- gemeinsame Höhenberechnung für `artist`, `copyright`, `character`
- General und Meta bleiben darunter als eigene größere Listen

## Test

```bash
python -m compileall -f app
```

lief ohne Syntaxfehler.
