# 1.3.78 Fetch: minimale unbekannte Posts pro Query

## Ziel

Der Fetcher kann nun nicht nur eine maximale Anzahl geprüfter Posts pro Query verwenden, sondern optional auch ein Ziel für neue/unbekannte Posts pro Query.

## Neue Option

Im Fetch-Tab:

- `Min unbekannte pro Query`

Verhalten:

- `0` deaktiviert den neuen Modus.
- Bei einem Wert größer `0` blättert jede Query weiter, bis so viele neue/unbekannte Posts gefunden wurden.
- Bereits bekannte Posts zählen dann nicht gegen dieses Ziel.
- Der Fetch stoppt trotzdem bei `Max Posts gesamt` oder wenn Danbooru keine weiteren Seiten für die Query liefert.

Beispiel:

- `Min unbekannte pro Query = 50`

Dann wird jede Query weiter durchsucht, bis 50 neue Posts gefunden wurden oder ein Stop-Kriterium erreicht ist.

## Fortschritt

Im Fortschritt wird im neuen Modus angezeigt:

- Query X / X
- Unbekannt Query: X / Ziel
- geprüft gesamt
- bekannt
- neu
- Thumbnails

Der Fortschrittsbalken orientiert sich im neuen Modus am Ziel für neue/unbekannte Posts statt an der Zahl der nur geprüften Posts.

## Presets

Die neue Option wird in Fetch-Presets und in der letzten Fetch-Konfiguration gespeichert.
