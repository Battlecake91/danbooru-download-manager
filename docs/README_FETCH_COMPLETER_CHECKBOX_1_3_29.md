# 1.3.29 - Fetch: Rating-Checkbox-Text und Tag-Autocomplete

## Änderungen

### Rating-Filter

Die dreistufigen Rating-Checkboxen zeigen im Text jetzt nur noch den Namen:

- General
- Safe
- Questionable
- Explicit

Der Zustand wird ausschließlich über das Checkbox-Symbol angezeigt:

- leer = ignorieren
- Haken = einschließen
- Strich = ausschließen

Damit steht nicht mehr zusätzlich `[x]`, `[−]` oder ähnliches im Text.

### Tag-Autovervollständigung

Die Autovervollständigung der manuellen Tags arbeitet jetzt tokenbasiert:

- Tags werden durch Leerzeichen getrennt.
- Das aktuelle Token wird anhand der Cursorposition erkannt.
- Ein führendes `-` wird beim Einfügen erhalten.
- Autocomplete funktioniert auch nach dem ersten Tag weiter.

Beispiele:

```text
brown_eyes red_
```

kann `red_hair` vorschlagen und einfügen.

```text
brown_eyes -red_
```

fügt bei Auswahl `-red_hair` ein.

## Geänderte Dateien

```text
app/gui/fetch_tab.py
```
