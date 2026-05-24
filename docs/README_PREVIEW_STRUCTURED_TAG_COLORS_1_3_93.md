# 1.3.93 - Preview: aufgeschlüsselte Taggruppen farbig

Dieser Patch verbessert die aufgeschlüsselte Tag-Darstellung in den Preview-Karten.

## Änderung

Im Modus `Aufgeschlüsselt` werden die Taggruppen jetzt farblich wie im Viewer hervorgehoben:

- Artist: Orange
- Character: Türkis
- Copyright / Serie: Rot
- General: hellgrau
- Meta: Violett

Beispiel:

```text
Artist: Magg (User Mtca8588)
Character: Senko (Sewayaki Kitsune No Senko-San)
Copyright: Sewayaki Kitsune No Senko-San
General: 1Girl, Fox Ears, Fox Tail
Meta: Commentary, Highres
```

Die Raw-Darstellung bleibt unverändert.

## Technisch

- `ThumbnailCard.update_tags_label()` erzeugt im strukturierten Modus jetzt HTML-Zeilen mit farbigen Gruppen.
- `tags_label` nutzt explizit `Qt.RichText`.
- Die Farben entsprechen den Viewer-Tagfarben.

## Prüfung

```bash
python3 -m compileall app/gui/thumbnail_grid.py
```
