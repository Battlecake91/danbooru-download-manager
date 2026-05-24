# Patch 1.3.97 - Async Tag/Query Completion

## Problem

Nach Patch 1.3.96 startet die Anwendung schnell, aber der erste Klick in **Tags / Query** konnte die GUI blockieren. Ursache war das nachgelagerte Laden einer großen Tag-Suggestion-Liste im GUI-Thread.

## Änderung

- Das Suchfeld lädt beim Fokus keine komplette Tagliste mehr.
- Vorschläge werden erst ab mindestens 2 Zeichen angefragt.
- Die Anfrage wird per kurzem Debounce verzögert.
- Die Datenbankabfrage läuft in einem eigenen `QThread` mit eigener SQLite-Verbindung.
- Während eine Anfrage läuft, wird nur der letzte neue Token vorgemerkt.
- Alte Ergebnisse werden verworfen, wenn der Nutzer inzwischen weitergetippt hat.

## Datenbank-Optimierung

`Database.suggest_tags()` wurde für interaktive Autocomplete-Nutzung entschärft:

- kein `COUNT(DISTINCT post_id)` / `GROUP BY` mehr pro Tastendruck
- zuerst schnelle Prefix-Suche
- kleinere Contains-Fallback-Suche nur wenn nötig
- weiterhin Mischung aus Copyright, Character, Artist, Meta und General
- zusätzlicher Index `idx_post_tags_type_tag` für `tag_type, tag`

Der zusätzliche Index kann beim ersten Start nach dem Patch einmalig etwas Zeit kosten, danach sollte die Suche deutlich weniger zäh sein.

## Erwartetes Verhalten

- Programmstart bleibt schnell.
- Klick ins Feld hängt nicht mehr.
- Beim Tippen erscheinen Vorschläge asynchron.
- Falls eine Query auf einer sehr großen DB langsam ist, bleibt die GUI trotzdem bedienbar.
