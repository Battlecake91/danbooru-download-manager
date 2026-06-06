# Release Notes — 1.3.190

Version `1.3.190` is the current release of Danbooru Download Manager. It combines the redesigned Importer, Fetch filtering improvements, database-concurrency work and the Viewer startup correction developed after version 1.3.152.

---

## New features

### Fetch tag blacklist

- Added persistent **Fetch exclude** tags.
- Added **Exclude from fetch** to Viewer tag context actions.
- Added an editable **Fetch exclude** column to the Tag tab.
- Excluded posts are rejected before database storage and thumbnail download.

### Fetch resolution limits

- Added minimum and maximum width and height to Fetch Advanced Filter.
- Empty values and `0` mean unrestricted.
- Limits are stored per Fetch preset.
- Excluded posts are counted in the Fetch summary.

### Redesigned Importer

- Rebuilt the Importer as Source → Review → Import Process.
- Added Match, Questionable and Mismatch confidence classes.
- Added local and remote thumbnails to the review table.
- Added side-by-side comparison with arrow-key and button navigation.
- Added manual Match and Mismatch decisions.
- Added filtering, row selection and bulk import selection.
- Added local-versus-remote resolution comparison.
- Added **Download best version** for lower-resolution local files.
- Added latest-import-only rename scope and optional thumbnail fetching.

### Safer post identification

- Added MD5 lookup from filenames.
- Added strict validation that every recognized filename tag exists on the fetched post.
- Added safeguards against Konachan and other booru post-ID collisions.
- Preserved internal hyphens in tags such as `one-piece_swimsuit` and `chain-link`.

---

## Workflow changes

- Import actions are selected only after source scanning and candidate review.
- Scan progress and statistics are shown before opening the review list.
- API page size is configured globally, while posts-per-query and total limits remain part of Fetch presets.
- The LLM enable switch is available in both Scoring configuration and Fetch.
- `rating:s` is correctly labeled **Sensitive**, while General remains the green rating group.
- Parent/child alternatives no longer distort preference learning after one family member is selected.

---

## Reliability fixes

- Added process-wide FIFO coordination for SQLite write transactions.
- Configuration saves use a background worker.
- Removed schema migration from short-lived Fetch and Import workers.
- Fixed repeated Fetch runs after Configuration or Previewer activity.
- Removed unintended Previewer writes during tag identity calculation.
- Added rollback and write-gate cleanup for failed batch operations.
- Prevented a second Fetch from starting before the previous worker thread exits.
- Improved initial window and toolbar layout recalculation.
- Removed temporary verbose database tracing after diagnosis was complete.

### Viewer startup correction

The Viewer previously queried every visible post individually while calculating its initial score display. Large Preview result sets could therefore freeze the GUI before the Viewer appeared.

Version `1.3.190` replaces that N+1 query pattern with a chunked aggregate query, allowing the Viewer to open normally even with large result sets.

---

## Notes

- Existing `database_trace.log` files from diagnostic builds can be deleted manually.
- LLM functionality remains experimental.
