# 1.3.117 - Wartungs-Tab sichtbar registrieren

Dieser Mini-Patch stellt sicher, dass der Wartungs-/DB-Tab wirklich in der Hauptnavigation erscheint.

Änderungen:

- `AppWindow` registriert den Wartungs-Tab jetzt über eine eigene Sicherungsfunktion.
- `_add_lazy_tab()` ist idempotent und legt denselben Lazy-Tab nicht doppelt an.
- `_rebuild_tab_indices()` prüft ebenfalls, ob der Wartungs-Tab vorhanden ist.
- Der Tab heißt sichtbar `Wartung / DB`.

Damit soll auch ein Stand repariert werden, bei dem `maintenance_tab.py` vorhanden war, aber der Tab nicht angezeigt wurde.
