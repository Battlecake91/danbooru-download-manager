# Configuration

Danbooru Download Manager `1.3.189` stores normal runtime configuration in the local SQLite database. YAML is not the leading configuration source for everyday use.

---

## Main areas

Configuration covers:

- Danbooru connection and credentials,
- Fetch transport settings,
- Previewer and Viewer display,
- thumbnails and caches,
- filename generation,
- categories and output folders,
- scoring and optional LLM integration,
- language and update behavior,
- database maintenance.

Tag aliases, manual scores, filename exclusions and Fetch exclusions are primarily managed through the Tag tab and Viewer context menus.

---

## Credentials

Danbooru credentials are optional but recommended for authenticated features such as saved searches.

The application can store:

- username,
- API key,
- base URL.

Do not publish or commit a database containing credentials.

---

## Fetch settings

Configuration → Fetch contains global transport defaults such as the Danbooru API page limit.

Run-specific values belong to Fetch presets instead:

- Max posts per query,
- Max total posts,
- Minimum unknown posts per query,
- rating selection,
- resolution limits,
- LLM enable state.

This avoids having two different fields pretending to control the same run, a traditional source of software folklore.

### Saved-search extra tags

`saved_search_extra_tags` is appended to selected saved-search queries. In the GUI workflow, rating controls normally build the effective additional tags for the active run and preset.

---

## Previewer display

Preview cards can be configured to show selected metadata:

- post ID,
- Danbooru rating and score,
- parent state,
- local status,
- category,
- artist, character, copyright, general and meta tags.

Tags can be shown as raw Danbooru text or grouped into typed, formatted sections.

The Previewer toolbar and nested layouts are recalculated after startup and tab changes so controls remain visible at different window sizes.

---

## Filename generation

Filename patterns can use typed tag placeholders and the Danbooru post ID.

Example:

```text
%artist%_%characters%_%general%_%postid%
```

Filename behavior also considers:

- maximum filename length,
- typed tag priority,
- filesystem-safe character replacement,
- tags marked as filename exclusions,
- final filename preview in the Viewer.

---

## Categories

Categories define output folders and automatic assignment rules.

Rule groups use AND within a group and OR between groups:

```text
Group A: tag1 tag2 -tag3
Group B: tag4 tag5
```

Meaning:

```text
(tag1 AND tag2 AND NOT tag3) OR (tag4 AND tag5)
```

Category priority determines which automatic result wins first. The Viewer can override it manually and show the reason behind an automatic decision.

---

## Tag options

The Tag tab manages:

- aliases and canonical names,
- manual tag scores,
- filename exclusions,
- Fetch exclusions,
- tag type and frequency information.

**Filename exclude** prevents a tag from appearing in generated filenames.

**Fetch exclude** is stronger: any fetched post containing that tag is rejected before local storage and thumbnail caching.

---

## Scoring and parent/child isolation

Ratings, saved/rejected decisions, manual tag scores and aliases contribute to local recommendation behavior.

When one post in a parent/child family is saved, the remaining alternatives in that family are ignored as negative preference examples. Choosing one preferred variant should not teach the system that every nearly identical sibling contains undesirable tags.

The saved post remains a positive example.

---

## LLM settings

LLM integration is experimental.

Configuration → Scoring contains provider and payload settings. The shared **Enable LLM integration** switch is also shown in the Fetch tab, where its state can be stored per preset.

Payload behavior may use:

- raw or normalized tags,
- aliases,
- local recommendation scores,
- available category names,
- compact or privacy-oriented tag representations.

Manual decisions remain the source of truth.

---

## Importer settings

The importer is intentionally split into three pages rather than exposing every action before the scan:

1. Source selection,
2. candidate review,
3. final import process.

Rename behavior, existing-record updates and thumbnail fetching are chosen only in the final step. See [`IMPORTER.md`](IMPORTER.md).

---

## Database and maintenance

SQLite uses WAL mode. Writers are serialized through a FIFO coordinator while read-only Previewer queries remain concurrent.

Configuration saves use a dedicated worker connection so waiting for a Fetch transaction does not freeze the GUI.

Schema migration occurs at application startup. Worker connections do not rerun migrations whenever Fetch or Importer starts.

See [`DATABASE_ACCESS.md`](DATABASE_ACCESS.md).
