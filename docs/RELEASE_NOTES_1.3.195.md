# Danbooru Download Manager 1.3.195

Version 1.3.195 is a workflow and guidance release for Fetch, Preview, Viewer and tag statistics, with a Linux CI runtime fix for release builds.

## Added

- Added a configurable Viewer preview strip below the main image.
- The Viewer strip shows previous, current and next posts from the active Viewer list and keeps the current post centered.
- Added Config controls for previous/next strip count and strip thumbnail size.
- Added Fetch-tab controls for enabling tag exclusion, opening the excluded-tag management dialog and deciding whether excluded posts consume Fetch limits.
- Added `Rejected %` to the Tag tab.
- Scoring-excluded tags are intentionally omitted from the rejected-percentage score.
- Expanded the Help tab with task-oriented pages for Quick start, Fetch, Preview & Viewer, Tags & Scoring, and Builds & Tests.
- Added contextual tooltips for advanced Config, Fetch, Preview and Category controls.

## Fixed

- Fixed a Preview/Fetch layout regression where switching tabs after fetching could grow the window wider than all connected monitors.
- Fixed Preview thumbnail layout state so thumbnails remain constrained to the visible viewport after returning from Fetch.
- Replaced fragile Tag-tab column number updates with named column constants to avoid silent column drift.
- Added Linux Qt runtime packages to the reusable Tests workflow so Ubuntu CI can import PySide6 before Release builds start.

## Changed

- Parked the optional list-oriented result view in the roadmap until the desired UX is clearer.
- Added regression and feature-guard tests for Preview layout, Viewer strip behavior, Fetch exclude controls, Tag-tab statistics and Help/tooltip guidance.

No database migration is required. Existing databases, thumbnails, ratings, configuration and saved files remain compatible.
