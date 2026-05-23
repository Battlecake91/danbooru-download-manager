# 1.3.37 - Viewer Tagspalten kompakter

Dieses Patch-ZIP enthält nur geänderte Dateien.

## Viewer / Tags

- General- und Meta-Tags zeigen Zusatzwerte jetzt als kompakte rechte Spalten.
- Der Tagname bleibt linksbündig.
- Rechts stehen drei kurze Spalten:
  - `S:` Score
  - `✖:` Filename-Exclude (`ja` / `nein`)
  - `⌀☆:` durchschnittliches persönliches Rating
- Artist, Serie/Copyright und Character bleiben weiterhin ohne Zusatzspalten, damit die obere Tagaufteilung nicht wieder kaputtgeht.
- Durchschnittliche Sterne werden kompakter ohne `/10` angezeigt.

Beispiel:

```text
brown_eyes                         S: -5 | ✖: nein | ⌀☆: 7.5
```

Technisch wird für General/Meta pro Zeile ein kleines Widget verwendet, damit die rechten Werte sauber ausgerichtet sind und nicht per Leerzeichen-Magie herumrutschen.
