# Danbooru Manager 1.3.4 - Parent/Child lokal hervorheben und öffnen

## Problem

Wenn zu einem Post bereits ein lokaler Parent oder Child existierte, wurde das zwar angezeigt, aber zu unauffällig.

Außerdem öffnete Doppelklick auf Parent/Child bisher den Remote-Danbooru-Link.
Gewünscht ist:

- klar farblich hervorheben
- Doppelklick bevorzugt lokale Datei öffnen
- Rechtsklick mit Lokal/Remote-Auswahl

## Neu im Viewer

### Warnbox

Wenn Parent/Child-Posts lokal bekannt sind, erscheint rechts eine auffällige Warnbox:

```text
⚠ Es existiert bereits mindestens eine lokale Parent/Child-Version
```

### Related-Liste farbig

Einträge in der Parent/Child-Liste sind jetzt farblich hervorgehoben:

- lokale Datei vorhanden: gelb/orange hervorgehoben
- nur DB/Remote bekannt: ebenfalls markiert, aber anders

### Doppelklick

Doppelklick auf einen Parent/Child-Eintrag:

```text
lokale Datei vorhanden → lokale Datei öffnen
sonst → Remote Originalpost öffnen
```

### Rechtsklick

Rechtsklick auf einen Parent/Child-Eintrag:

```text
Lokal öffnen
Lokalen Ordner öffnen
Remote Originalpost öffnen
Remote-Link kopieren
Lokalen Pfad kopieren
```

Lokale Aktionen sind deaktiviert, wenn keine lokale Datei gefunden wurde.

## Lokale Pfadprüfung

Gesucht wird in dieser Reihenfolge:

```text
final_file_path
original_cache_path
original_path
thumbnail_path
rejected_thumbnail_path
```

## Geänderte Datei

```text
app/gui/image_viewer.py
```
