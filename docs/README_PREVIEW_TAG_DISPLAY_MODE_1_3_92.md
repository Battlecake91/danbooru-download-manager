# 1.3.92 - Preview-Karten: Raw- oder aufgeschlüsselte Tag-Darstellung

## Ziel

Die Preview-Karten können die Tags jetzt wahlweise weiterhin roh als technische Danbooru-Tagliste anzeigen oder typisiert/lesbarer aufschlüsseln.

## Neue Konfigurationsoption

In `Konfig -> GUI -> Preview-Karten-Inhalte` gibt es eine neue Auswahl:

- `Raw: einfache Tag-Zeile`
- `Aufgeschlüsselt: Artist / Character / Copyright / …`

Gespeichert wird die Einstellung unter:

```text
gui.preview_card.tag_display_mode
```

Werte:

```text
raw
structured
```

## Raw-Modus

Der Raw-Modus entspricht dem bisherigen Verhalten. Tags werden platzsparend als technische Tag-Zeile angezeigt, z. B.:

```text
1girl animal_ears fox_tail senko_(sewayaki_kitsune_no_senko-san)
```

Die bestehenden Tagtyp-Checkboxen wirken weiterhin als Filter.

## Aufgeschlüsselter Modus

Im strukturierten Modus werden Tags nach Typ gruppiert:

```text
Artist: Magg (User Mtca8588)
Character: Senko (Sewayaki Kitsune No Senko-San)
Copyright: Sewayaki Kitsune No Senko-San
General: 1Girl, Fox Ears, Fox Tail
Meta: Commentary, Highres
```

Dabei werden:

- Unterstriche durch Leerzeichen ersetzt
- Anfangsbuchstaben über einfache Titel-Schreibweise groß geschrieben
- deaktivierte Tagtypen nicht angezeigt

## Hinweise

Die Darstellung nutzt die bereits in der DB gespeicherten typisierten Felder `tags_artist`, `tags_character`, `tags_copyright`, `tags_general` und `tags_meta`. Falls bei alten Einträgen keine typisierten Tags vorhanden sind, fällt die Karte im Zweifel auf die bisherige Raw-Anzeige zurück, sofern alle Tagtypen aktiv sind.

