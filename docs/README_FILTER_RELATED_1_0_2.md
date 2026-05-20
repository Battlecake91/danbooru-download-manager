# Danbooru Manager 1.0.2 - Statusfilter fix und Parent/Child-Anzeige

## Fix: Statusfilter

Problem:

In der Ansicht `Arbeitsliste` war `Status: Abgelehnt` leer, weil intern beides kombiniert wurde:

```sql
status IN ('new', 'potential', 'review', 'selected_save')
AND status = 'rejected'
```

Das ist logisch korrekt, aber für die GUI dumm.

Neue Logik:

Wenn ein konkreter Statusfilter gesetzt ist, gilt dieser global.
Also:

- `Status: Abgelehnt` zeigt abgelehnte Posts
- `Status: Gespeichert` zeigt gespeicherte Posts
- unabhängig davon, ob vorher `Arbeitsliste` aktiv war

## Parent/Child-Anzeige

Neu:

- Preview-Karte zeigt:
  - `Parent lokal`
  - `N Child(s) lokal`
- Viewer zeigt eine Parent/Child-Liste
- Doppelklick auf einen Parent/Child-Eintrag öffnet den Danbooru-Originalpost

## Einschränkung

Danbooru liefert in den normalen Postdaten meist nur:

- `parent_id`
- `has_children`

Die konkreten Child-IDs kennen wir nur, wenn diese Child-Posts bereits in der lokalen DB gelandet sind.
Unbekannte Childs können erst angezeigt werden, wenn sie über Fetch/Suche in die DB kamen.
