# 1.3.41 - Tag-Alias Privacy Layer / Canonical Tags

Dieser Patch legt die empfohlene Alias-/Privacy-Schicht fuer spaetere LLM-Auswertung an.

## Neue Tag-Ebenen

Tags koennen jetzt intern so abgebildet werden:

```text
Original-Tag -> Canonical/Alias -> LLM-Token
```

Beispiel:

```text
red_shirt      -> shirt -> tag_ab12cd34...
blue_shirt     -> shirt -> tag_ab12cd34...
striped_shirt  -> shirt -> tag_ab12cd34...
```

Wenn ein Alias gesetzt ist, wird dieser Alias als Canonical-Tag und Hash-Basis verwendet. Damit landen aehnliche Tags spaeter nicht als 27 einzelne Shirt-Varianten im LLM-Kontext. Software mit weniger Rauschen, was fuer ein dekadenter Luxus.

## Datenschutz

Neu ist ein lokaler Salt in `app_settings`:

```text
llm.hash_salt
```

Damit werden LLM-Tokens als Salted Hash erzeugt. Das ist deutlich besser als nacktes `sha256(tag)`, weil ein externer Dienst nicht einfach die bekannte Danbooru-Tagliste durchhashen kann.

Wichtig: Das ist Pseudonymisierung, keine absolute Anonymisierung. Wenn spaeter Bewertungen, Mengen und Muster mitgeschickt werden, koennen trotzdem Rueckschluesse entstehen. Magie bleibt weiterhin ausverkauft.

## Neue Config-Werte

```text
scoring.use_aliases_for_scoring = true
scoring.ignore_scoring_excluded_tags = true
llm.tag_export_mode = "hashed_alias"
llm.hash_prefix = "tag_"
llm.hash_length = 12
llm.include_tag_legend = false
```

`llm.tag_export_mode` kann sein:

```text
original      Klartext-Originaltags
alias         Klartext-Alias/Canonical-Tags
hashed_alias  Salted Hash auf Canonical-Tags
```

## Datenbank

Neue Tabelle:

```text
tag_identity_cache
```

Sie cached:

```text
original_tag
canonical_tag
llm_token
```

Der Cache wird bei Alias-Aenderungen automatisch geleert und bei Bedarf neu aufgebaut.

## Viewer

General/Meta-Tooltips zeigen jetzt zusaetzlich:

```text
Canonical/Alias
LLM-Token
```

Die sichtbare Tag-Zeile bleibt unveraendert, damit das Layout nicht wieder eine kleine Tragödie auffuehrt.

## Config-Tab

Neuer Bereich:

```text
Scoring / LLM-Tag-Privacy
```

Dort koennen Alias-Scoring und LLM-Exportmodus eingestellt werden.
