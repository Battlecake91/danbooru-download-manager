# 1.3.19 - Viewer-Seitenpanel kompakter

Änderungen:

- Status-Chips im Viewer sind jetzt fest und flach skaliert.
- Reihenfolge im rechten Panel angepasst:
  1. Status
  2. Parent/Child-Hinweis
  3. aufklappbare Parent/Child-Liste
  4. Zielpfad
  5. Tags
- Parent/Child-Liste öffnet sich jetzt direkt unter dem Hinweis, nicht mehr oberhalb des Status.
- Zielpfad wird in einem hellen, eingerahmten Kasten angezeigt und in der Höhe begrenzt.
- Überschrift `Tags nach Danbooru-Typ` entfernt.
- General-Tagliste bekommt deutlich mehr Platz.
- Artist / Serie-Copyright / Character bleiben kompakt nebeneinander.

Syntaxcheck:

```bash
python -m compileall -f app
```
