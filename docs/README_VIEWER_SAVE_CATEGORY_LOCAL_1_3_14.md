# 1.3.14 - Viewer Save/Overwrite, Kategorie-Persistenz, lokale Parent/Child-Anzeige

## Fixes

### Parent/Child-Hinweis im Viewer

Der Viewer zählt jetzt getrennt:

- bekannte Parent/Child-Posts in der lokalen DB
- davon wirklich lokal final gespeicherte Dateien

Eine Warnung vor lokalen Varianten-Duplikaten erscheint nur noch, wenn eine finale Datei tatsächlich existiert. Reine DB-/Remote-/Thumbnail-Einträge werden als bekannte Parent/Child-Einträge angezeigt, aber nicht mehr als lokale Version verkauft.

### Final speichern überschreibt jetzt nach Rückfrage

Der separate Button `Final überschreiben` wurde entfernt.

Wenn ein Post bereits einen `final_file_path` besitzt, fragt `Final speichern (F)` jetzt nach:

- existiert die Datei lokal: Original erneut laden und final ersetzen/neu speichern
- fehlt die Datei lokal: Original erneut laden und den Zielpfad reparieren

Dabei wird für final gespeicherte Dateien weiterhin Danbooru `file_url` verwendet, nicht Thumbnail, Preview oder Sample.

### Kategorieauswahl im Viewer bleibt erhalten

Eine im Viewer ausgewählte Kategorie wird sofort als manuelle Kategorie in `post_categories` gespeichert. Beim Wechsel zum nächsten Bild und zurück wird diese Kategorie wieder geladen, statt erneut stumpf der automatische Vorschlag zu werden. Bahnbrechend: Auswahl bleibt Auswahl.

### Lokales Bild öffnen

Neben `Zielordner öffnen` gibt es jetzt `Lokales Bild öffnen`. Der Button ist nur aktiv, wenn die finale lokale Datei wirklich existiert.

### Suche findet auch gespeicherte/lokale Bilder

Bei aktiver Text-/Tag-Suche sucht die Preview jetzt über alle Status. Damit tauchen auch bereits gespeicherte lokale Bilder auf, wenn nach Tags gesucht wird. Ohne Suchtext bleiben die Statusfilter unverändert wirksam.

### Preview-Badges

Die Thumbnail-Karten zeigen bei Parent/Child-Beziehungen nicht mehr `lokal`, sondern `bekannt`, weil die Preview ohne Dateisystemprüfung sonst wieder schummelt.
