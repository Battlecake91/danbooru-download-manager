# Testing

Danbooru Download Manager has both automated checks and manual functional validation.

Run the automated tests from the repository root:

```bash
python -m pytest
```

For a dependency-free smoke run in environments where `pytest` is not installed yet:

```bash
python -m unittest discover -v
```

The automated suite does not require live network access or a visible GUI. It covers core parsing/scoring helpers, database bootstrap, selected fetch/update helpers, release-asset selection, and SQLite performance guardrails.

Fetch-control regression tests additionally verify:

- cancellation before the next post is processed,
- reset and activation of the consecutive-known-post limit,
- Viewer result construction using the full filtered count instead of the visible Preview limit.

## Performance diagnostics

Database performance tests live in `tests/test_database_performance.py`.

They combine two checks:

- `EXPLAIN QUERY PLAN` assertions for important indexes, so regressions identify whether SQLite stopped using a hot-path index.
- bounded runtime checks on a synthetic medium-size dataset, so unexpectedly expensive preview, tag completion, category influence, and tag-statistics paths fail early.

If a performance test fails, inspect the failure message first. Query-plan failures print the plan SQLite chose; timing failures name the method that exceeded its budget.

These tests are not a replacement for profiling a very large personal collection, but they give the project a repeatable tripwire for the DB paths that have historically hurt responsiveness.

---

## Manual validation notes

Danbooru Download Manager is developed through incremental patches and manual functional validation of affected workflows.

This is not a claim of mathematical perfection. It means the important paths were repeatedly exercised instead of being assembled in one majestic, untested rewrite.

---

## Tested areas

### Startup and layout

- source and packaged startup paths,
- first-run database initialization,
- nested tab and toolbar resizing,
- repeated tab changes and maximized-window layout.

### Fetch

- manual queries, presets and saved searches,
- rating selection,
- API page size and per-preset limits,
- Fetch-exclude tags,
- resolution filters,
- known-post updates and thumbnail loading,
- cancellation with completed work retained,
- stopping each query after a configured consecutive-known-post sequence,
- repeated Fetch runs,
- Fetch followed by Previewer opening and another Fetch.

### Previewer and Viewer

- status filters, search and sorting,
- structured tags and configurable card data,
- image loading and navigation,
- navigation across the complete filtered/sorted result set beyond the Preview card limit,
- ratings, statuses and category decisions,
- tag aliases, scores, filename exclusions and Fetch exclusions.

### Importer

- Source → Review → Import Process navigation,
- MD5 and post-ID detection,
- filename-tag validation,
- hyphenated tags,
- confidence filters,
- local and remote thumbnails,
- side-by-side comparison,
- Match/Mismatch decisions,
- resolution upgrades,
- selected-only import actions,
- latest-import rename scope,
- thumbnail fetching.

### Database concurrency

- Fetch writes while saving Configuration,
- queued settings writes,
- concurrent Previewer reads under WAL,
- repeated workers with separate connections,
- failed write rollback and gate cleanup,
- `executemany()` cleanup,
- worker close and thread termination before restart.

### Packaging and updates

- PyInstaller runtime paths,
- release ZIP structure,
- persistent local data paths,
- updater asset workflow.

---

## Known limits

Testing remains primarily manual and Windows-focused. More validation is still useful for:

- very large databases and collections,
- interrupted or unstable network connections,
- cancellation timing during unusually slow individual HTTP responses,
- unusual Danbooru API errors,
- non-Windows packaged builds,
- every possible LLM provider configuration,
- updater behavior in unusual installation locations.

Keep backups of important files and the SQLite database before large imports or maintenance operations.
