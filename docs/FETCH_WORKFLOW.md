# Fetch Workflow

The Fetch tab is where new Danbooru posts are discovered and imported into the local database.

It does not have to download full image files immediately. The normal workflow loads post metadata and thumbnails first. This keeps review fast and avoids filling folders with posts that are rejected five seconds later, which is the closest software gets to basic hygiene.

---

## 🔎 Search modes

The Fetch tab supports several ways to define what should be loaded.

### Manual tag query

Enter a Danbooru tag expression directly.

Examples:

```text
1girl smile rating:s
```

```text
artist_name ( rating:q or rating:e )
```

### Presets

Presets store reusable fetch configurations. They are useful for repeated searches with the same tags, rating filters, or saved-search settings.

### Saved searches

When Danbooru credentials are configured, the application can load Danbooru saved searches and use them as query sources.

### Rating filters

The Fetch tab can include or exclude rating groups depending on the current configuration.

Supported Danbooru rating classes depend on the Danbooru API data returned for each post.

---

## 📏 Fetch limits

Fetch runs can be limited so the application does not process too much at once.

Common limits include:

- maximum posts per query,
- maximum total posts,
- minimum unknown posts per query,
- thumbnail loading behavior,
- known/unknown post handling,
- status filters.

Known posts can be skipped, updated, or reused depending on the current settings. Unknown posts are added to the local database with tags, metadata, and thumbnail information.

---

## 🧾 Fetch result summary

After a fetch run, the application shows a summary with information such as:

- processed queries,
- checked posts,
- new posts,
- known posts,
- updated posts,
- loaded thumbnails,
- errors or skipped entries.

Fetched posts then appear in the Previewer.

---

## 🖼️ Relation to Previewer and Viewer

The Fetch tab only brings posts into the local review workflow. Decisions are usually made later:

1. Fetch metadata and thumbnails.
2. Triage posts in the Previewer.
3. Open promising posts in the Viewer.
4. Rate, reject, keep, categorize, or save.
5. Download and store originals only when needed.

This keeps the local collection cleaner and makes the review process faster.
