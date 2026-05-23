# 1_3_45 - Dateinamen-Tag-Priorisierung sichtbar in der Konfiguration

## Änderung

Die Dateinamen-Priorisierung ist jetzt im Config-Tab explizit als Dropdown sichtbar:

- `Konfiguration -> Dateiname -> Tag-Reihenfolge`
- `Original / bisherige Reihenfolge`
- `Nach Tag-Scoring priorisieren`

Intern wird weiterhin die vorhandene Einstellung verwendet:

- `filename.sort_tags_by_average_rating`

## Zweck

Die vorherige Checkbox war je nach Stand/Scrollbereich zu leicht zu übersehen bzw. nicht eindeutig genug. Das Dropdown macht die Funktion direkt im Dateiname-Block sichtbar.
