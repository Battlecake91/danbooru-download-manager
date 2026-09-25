# Danbooru Manager 1.3.203

## Added

- Added an **Abbrechen / Cancel** action for active Fetch runs. Completed database work is retained, and optional LLM follow-up stops between batches.
- Added the per-preset **Known posts in a row** limit. It stops the current query after the configured number of consecutive known posts and then continues with the next query.
- Added Fetch progress and summary information for cancellation and queries stopped by the known-post limit.

## Changed

- Viewer navigation now covers every post matching the active Previewer statuses, search, category filter, recommendation threshold and sorting instead of only the currently rendered Preview cards.

## Validation

- Added regression tests for Fetch cancellation, consecutive-known-post handling and full-result Viewer construction.
- Verified the complete automated suite with 59 passing tests and a headless Qt smoke test of the Fetch tab.

The planned web application is not included in this release.
