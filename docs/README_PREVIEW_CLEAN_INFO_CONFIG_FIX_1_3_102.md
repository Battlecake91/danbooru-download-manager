# Patch 1.3.102 - Preview entschlacken und Config-Lazy-Crash beheben

## Inhalt

- `ConfigTab.on_thumbnail_preset_changed()` ist robuster, wenn `thumbnail_size` nicht mehr direkt im alten `gui_form` liegt.
- Der Crash beim Öffnen des lazy geladenen Konfigurations-Tabs wurde behoben:
  - vorher: `self.gui_form.labelForField(self.thumbnail_size_spin)` konnte `None` liefern
  - jetzt: erst wird im echten Preview-Layout gesucht, danach im alten FormLayout, danach wird sauber nichts getan
- Der Previewer zeigt weniger redundante Informationen:
  - keine Wiederholung von Ansicht, Status, Kategorie, Vorauswahl-Filter, Sortierung oder Thumbnailgröße in der Statistik
  - keine Anzeige von `Basis-Treffer`
  - Statistik reduziert auf `Angezeigt: x/y` und `Best | Worst | Average`
- Mehrere Toolbar-Beschriftungen wurden entfernt und durch Tooltips ersetzt:
  - Ansicht
  - Status
  - Kategorie
  - Vorauswahl
  - Sortierung
  - Thumbnailgröße

## Hinweise

`Limit:` bleibt sichtbar, weil der Zahlenwert allein sonst zu unklar ist. Die restlichen Elemente zeigen ihren Zustand direkt über ComboBox, Checkbox oder SpinBox und brauchen keine doppelte Beschriftung.
