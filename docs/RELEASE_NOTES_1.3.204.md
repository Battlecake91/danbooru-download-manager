# Danbooru Manager 1.3.204

Version `1.3.204` is a focused performance release for the Previewer and Viewer.

## Viewer performance

- Viewer navigation now loads only post IDs and parent relationships when no category or recommendation calculation is required.
- Category and recommendation filters use a compact analysis query instead of loading complete Preview card data for every matching post.
- The Viewer still navigates across every post matching the active filters and sorting.

## Preview performance

- Full card metadata and typed tag groups are loaded only for the posts that will actually be displayed.
- Tag groups are aggregated in one database pass instead of several correlated queries per post.
- Thumbnail files are decoded near their display size, reducing image decoding work and memory use.
- The first batch of Preview cards becomes visible while the remaining cards continue rendering.

## Validation

- Added performance regression tests for lightweight Viewer navigation and batched Preview detail loading.
- The automated test suite passes with 61 tests.
- A synthetic 10,000-post benchmark completed Viewer navigation in approximately `0.005 s`, compact filter analysis in approximately `0.035 s`, and detail loading for 100 Preview cards in approximately `0.002 s` on the release development system.
