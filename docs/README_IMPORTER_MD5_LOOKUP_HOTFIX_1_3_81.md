# 1.3.81 Importer MD5-Lookup Hotfix

## Problem

Der bestehende Datei-Importer rief `DanbooruApi.get_post_by_md5()` auf, aber diese Methode war im Patch 1.3.80 nicht im ausgelieferten Patch-ZIP enthalten. Dadurch konnte der Importer mit folgendem Fehler abbrechen:

```text
'DanbooruApi' object has no attribute 'get_post_by_md5'
```

## Fix

`app/danbooru/api.py` enthält jetzt die Methode:

```python
def get_post_by_md5(self, md5_hash: str) -> dict[str, Any] | None:
```

Die Methode validiert den 32-stelligen MD5-Hash und sucht den Post über die normale Danbooru-Postsuche:

```text
/posts.json?tags=md5:<hash>&limit=1
```

Wenn kein Post gefunden wird, gibt sie `None` zurück.

## Betroffene Dateien

```text
app/danbooru/api.py
docs/README_IMPORTER_MD5_LOOKUP_HOTFIX_1_3_81.md
```
