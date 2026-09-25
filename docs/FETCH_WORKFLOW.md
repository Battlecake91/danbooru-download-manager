# Fetch Workflow

This document describes the current desktop Fetch workflow in Danbooru Download Manager.

Fetch discovers Danbooru posts and stores their metadata and thumbnails in the local database. Original files are normally downloaded later, after review. This keeps unwanted posts out of the final collection instead of downloading first and developing judgment afterward.

---

## Search sources

### Manual query

Enter a normal Danbooru tag expression:

```text
1girl smile rating:s
```

```text
artist_name ( rating:q or rating:e )
```

### Presets

Presets store reusable Fetch settings, including:

- manual query or saved-search selection,
- rating selection,
- posts-per-query and total limits,
- minimum unknown-post target,
- consecutive-known-post stop limit,
- resolution limits,
- LLM enable state.

### Saved searches

Authenticated users can load Danbooru saved searches and use them as query sources. The selected rating controls are appended to the generated search query for the run.

---

## Ratings

The Fetch tab uses Danbooru's rating groups:

- `rating:g` — **General**, shown in green,
- `rating:s` — **Sensitive**, shown in yellow,
- `rating:q` — **Questionable**,
- `rating:e` — **Explicit**.

Sensitive is not another spelling of safe. It includes material such as underwear and swimwear that is intentionally distinct from General.

---

## Fetch exclusion blacklist

The **Fetch exclude** list blocks posts that contain selected tags.

A tag can be added through:

- the Viewer tag context menu with **Exclude from fetch**,
- the Tag tab through the **Fetch exclude** column and context actions.

The Tag tab can filter and sort by this state. Excluded posts are skipped before database insertion and thumbnail caching, and the Fetch summary reports them separately.

Use this for tags that should never enter the local review queue, not merely tags that should be hidden from one Previewer search.

---

## Resolution filter

The Fetch tab provides an **Advanced Filter** for original image dimensions:

- minimum width,
- maximum width,
- minimum height,
- maximum height.

Empty fields and `0` mean unrestricted.

Examples:

```text
Minimum width: 1920
Minimum height: 1080
```

accepts images at or above 1920 × 1080, while leaving both maximum values unrestricted.

Resolution limits are stored with the preset. Posts outside the range are rejected before they are stored or cached. If a required dimension is unknown, the post is excluded because an unknown width is not secretly 4K merely because optimism is free.

---

## Limits

Per-preset limits in the Fetch tab are:

- **Max posts per query**,
- **Max total posts**,
- **Minimum unknown posts per query**,
- **Known posts in a row**.

The Danbooru API page size is a global transport setting under **Configuration → Fetch**.

These values have different purposes:

- API page size controls how many posts are requested per HTTP page.
- Max posts per query limits how many posts are examined for each generated query.
- Max total posts limits the complete run.
- Minimum unknown posts can continue pagination until enough previously unseen posts have been found, subject to the other limits.
- Known posts in a row stops only the current generated query after the configured number of consecutive existing database posts. A new post resets the counter, and `0` disables the condition.

This early-stop condition is especially useful for recurring searches ordered from newest to oldest. Once a sufficiently long uninterrupted block of already-known posts is reached, Fetch moves to the next tag query or saved search instead of walking through a large known history.

---

## Cancelling a Fetch

While a Fetch is active, the normal Fetch button is disabled and an additional **Cancel** action is shown.

Cancellation is cooperative:

- the current database operation is allowed to finish,
- an active HTTP request may run until it returns or reaches its configured timeout,
- no new API page or post is started afterward,
- completed metadata, tags and thumbnails remain stored,
- optional LLM follow-up is skipped, or stops between batches when it has already started.

The final summary identifies a cancelled run and retains the counts completed before cancellation.

---

## LLM integration

**Enable LLM integration** is shown both in Configuration → Scoring and in the Fetch tab. The Fetch value is also stored with the active preset.

When enabled and configured, new candidates can be sent through the experimental LLM preselection workflow. The Fetch summary reports input candidates, requests and saved decisions.

LLM processing is optional and does not replace manual review.

---

## Processing order

For every returned post, Fetch roughly performs this sequence:

1. Validate the post metadata.
2. Apply the persistent Fetch-exclude tag blacklist.
3. Apply minimum and maximum resolution limits.
4. Decide whether the post is new or already known.
5. Store or update metadata and tags.
6. Cache the thumbnail when required.
7. Update the consecutive-known counter and, when its limit is reached, continue with the next query.
8. Optionally include new candidates in LLM processing.

Filtering before storage prevents excluded posts from appearing in the Previewer and avoids unnecessary thumbnail downloads.

---

## Fetch summary

After a run, the summary includes values such as:

- processed queries,
- checked posts,
- new or unknown posts,
- known posts updated,
- Fetch-excluded posts,
- resolution-excluded posts,
- thumbnails loaded,
- queries stopped by the consecutive-known-post limit,
- whether the run was cancelled,
- LLM input and decisions when enabled.

---

## Repeated Fetch runs and database access

Each Fetch run owns a separate SQLite connection. Schema migration is performed only during application startup, not every time a worker opens a connection.

Writes are serialized through the process-wide database coordinator. The Previewer can continue read-only work in WAL mode, and opening the Previewer after a completed run no longer leaves a write slot that blocks the next Fetch.

The Fetch button remains disabled until the previous worker has closed its database connection and its Qt thread has fully ended.

See [`DATABASE_ACCESS.md`](DATABASE_ACCESS.md) for the full model.

---

## Review workflow

After Fetch finishes:

1. Open the Previewer.
2. Select the desired status and recommendation filters.
3. Search or sort the result set.
4. Open promising posts in the Viewer.
5. Rate, categorize, reject or save them.
6. Download originals only for posts worth keeping.

The Viewer receives all posts matching the active Previewer filters and sorting. Its Previous/Next navigation is therefore independent of the visible Preview card limit.
