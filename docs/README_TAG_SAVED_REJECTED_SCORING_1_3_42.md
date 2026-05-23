# 1.3.42 - Tag-Scoring mit gespeichert/abgelehnt-Statistik

Dieser Patch erweitert das automatische Tag-Scoring um die vorhandene Statistik aus gespeicherten und abgelehnten Posts.

## Verhalten

Für jeden Tag wird nun zusätzlich ausgewertet:

- wie oft der Tag in gespeicherten Posts vorkommt
- wie oft der Tag in abgelehnten Posts vorkommt
- welche durchschnittliche persönliche Bewertung Posts mit diesem Tag haben
- ob der Tag vom Scoring ausgeschlossen wurde

Der effektive Score folgt der Priorität:

1. Scoring-Exclude aktiv -> Score 0 / ignoriert
2. manueller Score vorhanden -> manueller Score gewinnt
3. sonst automatisch berechneter Score aus Stern-Durchschnitt + gespeichert/abgelehnt-Verhältnis

## Dämpfung für allgemeine Tags

Sehr häufige Tags mit vielen gespeicherten und vielen abgelehnten Beispielen werden gedämpft. Dadurch wird ein generischer Tag wie `1girl` nicht plötzlich hart negativ bewertet, nur weil er in sehr vielen abgelehnten Posts vorkommt.

## Viewer

Die Tag-Tooltips bei General/Meta zeigen jetzt zusätzlich:

- Gespeichert/Abgelehnt
- Anzahl bekannter Posts mit diesem Tag

Die sichtbare Tag-Zeile bleibt kompakt.

## Datenbank

Beim ersten Start nach diesem Patch werden die vorhandenen Tag-Statistiken einmalig neu berechnet und in `tag_scores` aktualisiert.

Danach werden betroffene Tags automatisch aktualisiert, wenn:

- ein Post-Status geändert wird
- eine persönliche Bewertung gesetzt wird
- ein Scoring-Ausschluss gesetzt oder entfernt wird
