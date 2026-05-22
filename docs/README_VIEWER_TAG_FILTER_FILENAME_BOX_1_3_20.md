# 1.3.20 - Viewer: Zielpfad-Kasten und Tagfilter

Änderungen:

- Zielpfad-Kasten im Viewer ist nicht mehr hell ausgefüllt, sondern transparent mit weißer Umrandung.
- Taggruppen sind enger zusammengefasst: Die Überschriften kleben direkt über den jeweiligen Listen statt irgendwo im GUI-Nirwana herumzuschweben.
- Der Filename-Exclude-Filter gilt jetzt für alle Taggruppen, nicht nur für General.
- Die Filteroption steht unter dem gesamten Tagfeld und heißt jetzt: `Nur nicht ausgeschlossene Filename-Tags anzeigen`.

Technisch geändert:

- `app/gui/image_viewer.py`
- `app/gui/tag_display.py`
