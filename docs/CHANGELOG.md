# Changelog

This changelog groups development into user-facing milestones instead of preserving every internal patch as a separate archaeological layer.

## 1.3.190 — Viewer startup hotfix candidate

### Fixed

- Replaced the Viewer startup N+1 query loop with a chunked aggregate score query.
- Prevented the GUI from appearing frozen while opening the Viewer with a large Preview result set.

### Release status

- `1.3.189` has been withdrawn and must not be published as a stable release.
- `1.3.190` is a corrective development build and requires validation before a replacement release is published.

---

## 1.3.189 — Withdrawn release candidate

### Added

- Persistent Fetch-exclude tag blacklist with Viewer and Tag-tab actions.
- Fetch Advanced Filter for minimum and maximum width and height.
- Three-step importer: Source, Review and Import Process.
- Import confidence classification: Match, Questionable and Mismatch.
- Local and remote thumbnails in the importer candidate list.
- Side-by-side importer comparison viewer with arrow-key navigation.
- Manual Match/Mismatch decisions and filtered bulk selection.
- Resolution comparison and best-version replacement for imported files.
- Optional thumbnail fetching during import.
- Rename scope for the latest import only.

### Changed

- Corrected `rating:s` to Sensitive and kept General as the green rating group.
- Moved global API page size to Configuration → Fetch.
- Kept posts-per-query and total limits in Fetch presets.
- Exposed the shared LLM enable switch in both Scoring configuration and Fetch.
- Isolated parent/child alternatives from negative preference learning after one family member is saved.
- Reorganized Importer options so actions are selected only after candidate review.
- Improved initial window and toolbar layout recalculation.

### Fixed

- Foreign-board post-ID collisions through MD5 and strict filename-tag validation.
- False importer mismatches caused by hyphenated Danbooru tags.
- Importer table readability and accidental editable cells.
- Slow importer status changes caused by rebuilding all thumbnails after every decision.
- Repeated Fetch runs hanging after Configuration or Previewer activity.
- SQLite write conflicts through FIFO write coordination and asynchronous settings saves.
- Worker schema migration and lifecycle races.
- Leaked write slots after failed SQL and batch operations.
- Unintended Previewer writes during tag identity calculation.

See [`RELEASE_NOTES_1.3.189.md`](RELEASE_NOTES_1.3.189.md) for the release-focused summary.

---

## 1.3.152 — First official release

The first official release introduced the database-backed desktop application and its primary workflows:

- first-run setup,
- Fetch presets and saved searches,
- metadata-first Previewer,
- detailed Viewer with ratings, statuses and category selection,
- category rule groups and priorities,
- typed tags, aliases, scores and filename exclusions,
- configurable filename patterns,
- existing-file importer,
- SQLite-backed configuration,
- experimental LLM payload and preselection support,
- Windows packaging and portable updater foundation,
- English/German interface support.

Earlier patch-level notes remain in `docs/patches/`.
