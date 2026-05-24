# 1.3.84 - Autovervollständigung für Serien/Charaktere/Artist repariert

## Problem

Die Suchfelder/Felder mit Tag-Autovervollständigung haben ihre Vorschlagsliste aus den häufigsten Tags aufgebaut. Dadurch wurden die begrenzten Vorschlagsplätze fast vollständig von sehr häufigen General-Tags belegt.

Folge: Character-, Copyright-/Serien- und Artist-Tags waren zwar in der Datenbank vorhanden, wurden aber oft nicht vorgeschlagen.

## Änderung

`Database.suggest_tags()` reserviert die Vorschläge jetzt nach Tagtyp:

- Copyright / Serie
- Character
- Artist
- Meta
- General

Die Liste wird weiterhin nach Häufigkeit sortiert, aber General-Tags dürfen die Vorschlagsliste nicht mehr komplett verdrängen.

Zusätzlich nutzt der Kategorie-Tab jetzt ebenfalls `suggest_tags()` statt `fetch_tag_overview(limit=5000)`, damit Include-Regeln und globale Bedingungen dieselbe bessere Vorschlagsbasis bekommen.

## Betroffene Stellen

- Fetch-Suche / manuelle Query
- Preview-Suche
- Kategorie-Tab Tagfelder

## Keine Änderung

- keine Änderung am Datenbankschema
- keine Änderung an gespeicherten Tags
- keine Änderung an Fetch- oder Kategorie-Logik
