# Danbooru Download Manager 1.3.196

Version 1.3.196 fixes Viewer cache behavior and activates retention cleanup for rejected cache files.

## Fixed

- Changed the Viewer cache default from Danbooru `file_url` to `preview_url`, so simply viewing posts no longer downloads full original files by default.
- Normalized older saved `viewer_download_source = file` settings to `preview` at startup.
- Kept final saving on the full Danbooru original path, so saved library files still use `file_url`.
- Avoided slow per-file tag-statistics refreshes during existing-file imports.

## Added

- Added automatic cleanup for cache files attached to rejected posts.
- Rejected cache cleanup removes stale files from `originals/cache` and `thumbnails/rejected` after `workflow.rejected_thumbnail_retention_days`.
- Added regression coverage for Viewer preview cache selection, legacy config normalization and rejected cache cleanup.

No database migration is required. Existing databases, saved files and thumbnails remain compatible.
