# 1.3.24 - Preview-Status und Suche aufräumen

## Runtime neu anzeigen

Der Config-Button wurde in **Formular zurücksetzen** umbenannt. Er liest die aktuell im laufenden Programm vorhandene Runtime-Konfiguration wieder in die Eingabefelder ein, ohne SQL neu zu laden. Praktisch nur, wenn man ungespeicherte Änderungen im Formular verwerfen will. Der alte Name war maximal kryptisch, also weg damit.

## Preview-Statusfilter bereinigt

Die alten, nicht mehr aktiv setzbaren Workflow-Status werden im Previewer nicht mehr als Filter angeboten:

- Prüfen
- Speichern vormerken / Zum Speichern
- Automatisch aussortiert
- Akzeptiert
- Heruntergeladen/alt

Aktive Filter sind jetzt:

- Ungeprüft
- Hohes Potential
- Abgelehnt
- Bereits bekannt
- Gespeichert

Beim Datenbankstart werden alte Status migriert:

- review / selected_save -> new
- auto_rejected -> rejected
- accepted -> potential
- downloaded -> already_known

## Suche mit Ausschluss-Tags

Die Preview-Suche unterstützt jetzt Ausschluss-Tags:

```text
brown_eyes -red_hair
```

Bedeutung:

- Post muss `brown_eyes` enthalten oder über ID/Pfad dazu passen
- Post darf nicht den Tag `red_hair` enthalten

Mehrere positive und negative Begriffe sind möglich:

```text
brown_eyes solo -red_hair -ai-assisted
```

Der Statusfilter bleibt weiterhin aktiv. Wer gespeicherte Posts durchsuchen will, muss also den Status **Gespeichert** aktivieren oder die Ansicht passend setzen. Ja, Filter filtern jetzt wieder. Schockierend.
