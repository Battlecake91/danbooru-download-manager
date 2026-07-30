# Changelog

This changelog groups development into user-facing milestones instead of preserving every internal patch as a separate archaeological layer.

## 1.3.195 - Current release

### Fixed

- Added Linux Qt runtime libraries to the reusable test workflow so tag-pushed releases can pass the Ubuntu PySide6 import tests before building binaries.

### Changed

- Versioned the workflow/UI improvements from 1.3.194 as the published 1.3.195 release after the Linux CI pre-release failure.

See [`RELEASE_NOTES_1.3.195.md`](RELEASE_NOTES_1.3.195.md) for the complete release summary.

---

## 1.3.194

### Added

- Added a configurable Viewer preview strip below the main image, centered on the active post.
- Added Fetch-tab controls for enabling fetch-excluded tags and editing the excluded-tag list in a dialog.
- Added an option for whether fetch-excluded posts count toward Fetch limits.
- Added `Rejected %` in the Tag tab while keeping scoring-excluded tags out of that percentage.
- Expanded the Help tab with task-oriented Quick start, Fetch, Preview & Viewer, Tags & Scoring, and Builds & Tests pages.
- Added contextual tooltips for advanced Config, Fetch, Preview and Category controls.

### Fixed

- Fixed Preview/Fetch layout state that could make the window grow wider than all monitors after switching tabs.
- Kept Preview thumbnails constrained to the viewport after returning from Fetch.
- Guarded Tag-tab column updates with named column constants to avoid silent UI-column drift.

### Changed

- Updated the active roadmap to park the optional list-oriented view until the intended UX is clearer.
- Added regression and feature-guard tests for Fetch exclude controls, Viewer strip behavior, Tag-tab statistics, Help/tooltip guidance and Preview layout.

See [`RELEASE_NOTES_1.3.194.md`](RELEASE_NOTES_1.3.194.md) for the complete release summary.

---

## 1.3.193

### Fixed

- Fixed the portable updater failing while waiting for the application process because Windows process output could be missing.
- Replaced localized `tasklist` parsing with direct Windows process detection.
- Prevented the portable updater from deleting `danbooru_saved`, application data, databases, thumbnails, logs or unrelated user files.
- Made updater target handling accept both an installation directory and the application executable path.
- Fixed slow Manual Score editing for Viewer tags by avoiding the full historical tag overview query.
- Prevented Save, Reject and rating actions from blocking the Viewer while tag statistics are recalculated.
- Kept filename preview generation on the lightweight stored tag metadata path introduced in 1.3.192.

### Changed

- Official and draft publishing now automatically use `docs/RELEASE_NOTES_<version>.md` for the current application version.
- Publishing aborts with a clear error when the matching release-notes file is missing.

See [`RELEASE_NOTES_1.3.193.md`](RELEASE_NOTES_1.3.193.md) for the complete release summary.

---

## 1.3.192

### Fixed

- Fixed the Viewer freezing while generating the final filename preview on large databases.
- Replaced expensive historical tag-metadata aggregation with lightweight stored tag metadata for filename sorting.
- Reduced synchronous database work performed while opening a post in the Viewer.

See [`RELEASE_NOTES_1.3.192.md`](RELEASE_NOTES_1.3.192.md) for the complete release summary.

---

## 1.3.191

### Fixed

- Fixed the portable updater waiting forever for an already closed application because the PID was matched as a loose substring in `tasklist` output.
- Added exact Windows PID parsing and a persistent `danbooru_manager_data/updates/updater.log`.
- Added immediate updater-process failure detection and detached helper startup.

---

## 1.3.190

### Added

- Persistent Fetch-exclude tag blacklist with Viewer and Tag-tab actions.
- Fetch Advanced Filter for minimum and maximum width and height.
- Three-step importer: Source, Review and Import Process.
- Import confidence classification with local and remote thumbnails.
- Side-by-side importer comparison viewer with keyboard navigation.
- Resolution comparison and best-version replacement for imported files.

### Changed

- Corrected `rating:s` to Sensitive and kept General as the green rating group.
- Reorganized Fetch, Configuration and Importer controls around the current workflow.
- Added coordinated SQLite writes and asynchronous settings persistence.
- Improved repeated Fetch execution and worker lifecycle handling.

### Fixed

- Replaced the Viewer startup N+1 query loop with a chunked aggregate score query.
- Prevented the GUI from appearing frozen while opening the Viewer with a large Preview result set.
- Fixed database write-gate leaks triggered by Preview tag identity calculation.
- Fixed repeated Fetch runs after Configuration or Previewer activity.
- Fixed importer ID validation, hyphenated tags and resolution comparison behavior.

See [`RELEASE_NOTES_1.3.190.md`](RELEASE_NOTES_1.3.190.md) for the complete release summary.

---

## 1.3.189 — Withdrawn intermediate build

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

The changes from this intermediate build were corrected and released as `1.3.190`.

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
