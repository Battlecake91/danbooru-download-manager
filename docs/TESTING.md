# Testing Notes for Release 1.3.189

Danbooru Download Manager `1.3.189` was developed through incremental patches and manual functional validation of the affected workflows.

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
- repeated Fetch runs,
- Fetch followed by Previewer opening and another Fetch.

### Previewer and Viewer

- status filters, search and sorting,
- structured tags and configurable card data,
- image loading and navigation,
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
- unusual Danbooru API errors,
- non-Windows packaged builds,
- every possible LLM provider configuration,
- updater behavior in unusual installation locations.

Keep backups of important files and the SQLite database before large imports or maintenance operations.
