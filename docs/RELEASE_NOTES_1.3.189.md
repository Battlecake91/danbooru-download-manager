# Release Notes — 1.3.189

> [!WARNING]
> **Historical notice:** Version `1.3.189` was withdrawn because of a Viewer startup freeze. The corrected and current release is [`1.3.190`](RELEASE_NOTES_1.3.190.md).


Version `1.3.189` packages the importer redesign, Fetch filtering improvements and database-concurrency fixes developed after the original 1.3.152 release.

---

## New features

### Fetch tag blacklist

- Added persistent **Fetch exclude** tags.
- Added **Exclude from fetch** to Viewer tag context actions.
- Added a sortable and editable **Fetch exclude** column to the Tag tab.
- Excluded posts are rejected before database storage and thumbnail download.

### Fetch resolution limits

- Added minimum and maximum width and height to Fetch Advanced Filter.
- Empty values and `0` mean unrestricted.
- Limits are stored per preset.
- Excluded posts are counted in the Fetch summary.

### Importer review workflow

- Rebuilt Importer as Source → Review → Import Process.
- Added confidence classes for Match, Questionable and Mismatch.
- Added local and remote thumbnails.
- Added side-by-side comparison with keyboard and button navigation.
- Added manual Match and Mismatch decisions.
- Added filtering and bulk row/import selection.
- Added local-versus-remote resolution comparison.
- Added **Download best version** for lower-resolution local files.
- Added latest-import-only rename scope and optional thumbnail fetching.

### Safer post identification

- Added MD5 lookup from filenames.
- Added strict validation that every recognized filename tag exists on the fetched post.
- Added safeguards against Konachan and other booru post-ID collisions.
- Preserved internal hyphens in real tags such as `one-piece_swimsuit` and `chain-link`.

---

## Workflow changes

- Import actions no longer clutter the source-selection page.
- Scan status and statistics are shown before opening the review list.
- The final import options are chosen only after candidate review.
- Global API page size remains in Configuration; per-run limits remain in Fetch presets.
- The LLM enable switch is available in both Scoring configuration and Fetch.
- `rating:s` is correctly labeled **Sensitive**, while General is the green rating group.

---

## Reliability fixes

- Added a process-wide FIFO SQLite write coordinator.
- Configuration saves use a background worker and no longer freeze the GUI while waiting.
- Removed schema migration from short-lived Fetch and Import workers.
- Fixed repeated Fetch runs after opening the Previewer.
- Removed an unintended Previewer write from tag identity calculation.
- Added rollback and gate cleanup for failed batch writes.
- Prevented a second Fetch from starting before the previous worker thread fully exits.
- Improved initial window and toolbar layout recalculation.

---

## Scoring correction

Once one post from a Danbooru parent/child family is saved, rejected or separately rated siblings are ignored as negative preference examples. This prevents a chosen image from being undermined by rejected near-duplicates.

---

## Notes

- Temporary verbose database tracing used during deadlock diagnosis has been removed.
- Existing `database_trace.log` files can be deleted manually; new entries are no longer generated.
- LLM functionality remains experimental.
