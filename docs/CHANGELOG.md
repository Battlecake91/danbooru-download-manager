# Changelog

This changelog groups development into user-facing milestones instead of preserving every internal patch as a separate archaeological layer.

## Unreleased

### Added

- Added an independent FastAPI web application with its own source entry point and dependency set; the desktop application remains a separate selectable runtime.
- Added a Docker image and Compose setup with persistent SQLite/cache and archive mounts.
- Added manual and scheduled Fetch execution, cooperative cancellation and shared consecutive-known-post stopping.
- Added an endless-loading Preview feed with configurable batches and a dedicated Viewer route that navigates the complete active result set.
- Added the desktop-style web Viewer layout with typed tag columns, tag scoring metadata, status actions, star rating, category assignment and a clickable previous/current/next thumbnail strip.
- Added desktop-style tag context actions to the web Viewer and Tags tab for filename/fetch exclusions, manual and legacy scores, category influence, preselection and LLM usage.
- Added web management and execution of the same Fetch presets stored by the desktop application, including Danbooru saved-search presets.
- Added initial web tabs and APIs for tags, categories, configuration and maintenance.
- Added the desktop Viewer keyboard shortcuts to the web Viewer, including real final saving with `F` through the shared archive service.
- Added a persistent web Viewer option to advance to the next filtered post after any successful status change.
- Added the complete desktop Preview sort set to the web app, including live Preselection best/worst ordering and a Best/Worst/Average summary.
- Added persisted web Preview controls for 50-200 posts per endless-scroll batch and 120-600 px thumbnail sizing.

### Changed

- Container runtime paths now override desktop-specific absolute paths stored in SQLite so one database can move between Windows and Linux mounts.
- The Docker container now runs as UID/GID `1000:1000` by default, with optional `PUID` and `PGID` overrides in Compose.
- The web Viewer now follows the compact working layout of the desktop Manager instead of using a generic details sidebar.
- Web tag changes use the same database settings as the desktop application, including the filename-allowed display filter and visible scoring/usage markers.
- Renamed the ambiguous web Recommendation sort to Preselection and calculate it from current tag scores just like the desktop Manager.

### Fixed

- Web media lookup now recognizes Windows paths stored in SQLite when the same thumbnail files are mounted into a Linux container.
- The web Viewer no longer selects a cached grid thumbnail when a local full image or larger Danbooru image is available.
- The web Viewer Fit mode now constrains portrait and landscape images by both the available width and height, preventing tall images from being clipped below the viewport.
- Viewer shortcuts remain active after using Fit and filename-filter checkboxes instead of being suppressed by the retained checkbox focus.
- Recently reviewed posts remain reachable in the web Viewer after a status change removes them from the active filter, allowing accidental rejection to be corrected.
- Web request database connections now tolerate FastAPI worker-thread handoffs, preventing intermittent HTTP 500 responses during parallel thumbnail loading.
- Web Preview and Viewer category controls now show desktop-compatible automatic rule suggestions and persist manual selections by category ID.
- Thumbnail and Viewer media requests now use a lightweight post query and direct filename checks instead of full tag/detail aggregation and repeated directory scans.
- Web Preselection sorting now loads only score-relevant tags and caches the complete filtered ranking for scrolling and Viewer navigation. Status and save actions update affected cached rankings incrementally, while Fetch and tag-setting changes invalidate them completely.
- The Fetch page now persists and displays the start, finish and result of the latest automatic Fetch.
- Preview cards now support checkbox selection, Shift range selection and transactional bulk status changes, including direct rejection and removal from the active result.

## 1.3.205 - Current release

### Fixed

- Removed the per-post recommendation metadata query loop used while opening the Viewer with category or recommendation filtering. Shared tag metadata is now loaded in batches and reused across the complete result set.
- Preview rendering now exposes a small first batch immediately even when an older configuration still specifies a large general render batch.

### Changed

- Performance logging now records the complete Preview-to-Viewer opening path as `[PERF][viewer-open]` and Preview preparation/rendering as `[PERF][preview]`.
- Added a bulk recommendation performance regression test covering thousands of posts.

See [`RELEASE_NOTES_1.3.205.md`](RELEASE_NOTES_1.3.205.md) for the complete release summary.

---

## 1.3.204

### Changed

- Viewer startup now builds its navigation from lightweight post IDs instead of loading full Preview card details for every matching post.
- Category and recommendation filtering use a compact analysis query; full tag groups and card metadata are loaded only for visible Preview cards.
- Preview thumbnails are decoded near their display size, and the first card batch becomes visible while the remaining cards continue rendering.
- Added performance regression coverage for full-result Viewer navigation and batched Preview detail loading.

See [`RELEASE_NOTES_1.3.204.md`](RELEASE_NOTES_1.3.204.md) for the complete release summary.

---

## 1.3.203

### Added

- Added a Fetch cancellation action that stops cooperatively after the current network or database operation and preserves completed work.
- Added a per-preset **Known posts in a row** limit. Reaching the configured consecutive-known count stops the current query and continues with the next one; finding a new post resets the counter.
- Added progress and summary information for cancellation and queries stopped by the known-post limit.
- Added regression coverage for Fetch cancellation, consecutive-known handling and full-result Viewer construction.

### Changed

- Viewer navigation now uses every post matching the active Previewer filters and sorting instead of only the currently rendered Preview cards.
- Fetch cancellation is propagated into optional LLM follow-up processing between batches.

See [`RELEASE_NOTES_1.3.203.md`](RELEASE_NOTES_1.3.203.md) for the complete release summary.

---

## 1.3.202

### Added

- Importer matching now prefers Danbooru post IDs, verifies them with the calculated file MD5, and falls back to calculated file-MD5 lookup when the post ID is missing, mismatched, or comes from a known foreign-board filename.
- Exact post-ID+MD5 and file-MD5 matches now ignore filename tag mismatches.

See [`RELEASE_NOTES_1.3.202.md`](RELEASE_NOTES_1.3.202.md) for the complete release summary.

---

## 1.3.201

### Added

- The calculated MD5 lookup test now opens its matches in the Importer review flow with local/remote comparison candidates.
- Selected MD5-test candidates can be imported even when the local filename has no embedded MD5 or Danbooru post ID.

See [`RELEASE_NOTES_1.3.201.md`](RELEASE_NOTES_1.3.201.md) for the complete release summary.

---

## 1.3.200

### Fixed

- Fixed escaped newline text appearing in the Importer status summary after completed imports.
- Added Danbooru API throttling and retry handling for HTTP 429 rate-limit responses.

See [`RELEASE_NOTES_1.3.200.md`](RELEASE_NOTES_1.3.200.md) for the complete release summary.

---

## 1.3.199

### Added

- Added an Importer test mode that calculates each local file's MD5 and checks Danbooru for exact matches without importing.

### Fixed

- Passed selected replacement file/post data into the Importer worker for the existing **Download best version** action.

See [`RELEASE_NOTES_1.3.199.md`](RELEASE_NOTES_1.3.199.md) for the complete release summary.

---

## 1.3.198

### Fixed

- Added an Importer action for starting another folder import after a completed run.
- Reset Importer scan/progress state when starting the next folder import so the manager does not need to be restarted.

See [`RELEASE_NOTES_1.3.198.md`](RELEASE_NOTES_1.3.198.md) for the complete release summary.

---

## 1.3.197

### Fixed

- Moved rejected-cache cleanup into a background GUI worker so application startup is no longer blocked by cache purging.
- Added a startup regression guard that keeps rejected-cache cleanup out of the synchronous `main.py` path.

See [`RELEASE_NOTES_1.3.197.md`](RELEASE_NOTES_1.3.197.md) for the complete release summary.

---

## 1.3.196

### Fixed

- Changed Viewer caching so opening a post caches preview-sized media by default instead of the full original file.
- Normalized older saved `viewer_download_source = file` settings to the safer preview behavior.
- Avoided slow per-file tag-statistics refreshes during existing-file imports.

### Added

- Added startup cleanup for rejected cache files older than `workflow.rejected_thumbnail_retention_days`.
- Added regression tests for Viewer cache selection and rejected cache retention.

See [`RELEASE_NOTES_1.3.196.md`](RELEASE_NOTES_1.3.196.md) for the complete release summary.

---

## 1.3.195

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
