# Danbooru Manager 1.3.205

Version `1.3.205` completes the large-result Viewer performance correction and expands performance diagnostics.

## Performance fixes

- Removed the per-post recommendation metadata query loop that remained when category or recommendation filtering was active.
- Shared scoring metadata is loaded in bounded batches and reused across the complete filtered result set.
- A synthetic 10,000-post run now completes navigation, compact analysis and recommendation enrichment in approximately `0.277 s` on the release development system.
- Preview rendering exposes a small first card batch immediately, including installations that retain an older, larger general render-batch setting.

## Diagnostics

- `[PERF][viewer-open]` records result construction and Viewer initialization from the Preview card click until the window is shown.
- `[PERF][viewer]` continues to measure individual post changes inside the Viewer.
- `[PERF][preview]` records Preview queries, filtering, detail hydration and card rendering.
- The Viewer Perf toggle now updates the shared setting so subsequent Viewer openings and Preview reloads are captured automatically.

## Validation

- Added a bulk recommendation performance regression test covering thousands of posts.
- The automated test suite passes with 62 tests.
