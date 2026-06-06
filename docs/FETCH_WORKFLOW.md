# Fetch Workflow

The Fetch tab is where new Danbooru posts are discovered and imported into the local database.

In Danbooru Download Manager `1.3.152`, Fetch normally loads post metadata and thumbnails first. Full image files do not have to be downloaded immediately. This keeps review fast and avoids filling folders with posts that are rejected five seconds later, which is the closest software gets to basic hygiene.

---


### Advanced resolution filter

The Previewer provides an **Advanced Filter** for image dimensions. You can set minimum and maximum width and height values in pixels. A blank field or `0` disables that individual limit. Posts without known dimensions are hidden when the corresponding dimension filter is active.

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

Presets store reusable fetch configurations. They are useful for repeated searches with the same tags, rating filters or saved-search settings.

### Saved searches

When Danbooru credentials are configured, the application can load Danbooru saved searches and use them as query sources.

### Rating filters

The Fetch tab can include or exclude Danbooru rating groups. `rating:g` is **General**, while `rating:s` is **Sensitive**, not safe.

The Fetch tab also contains **Enable LLM integration**. Its state is stored with the current fetch preset so LLM processing can be enabled per run.

---

## 📏 Fetch limits

Fetch runs can be limited so the application does not process too much at once.

The Fetch tab stores these per-run values in each fetch preset:

- maximum posts per query,
- maximum total posts,
- minimum unknown posts per query.

The Danbooru API page limit is a global transport setting under **Configuration → Fetch** and is not stored in fetch presets.

Known posts can be skipped, updated or reused depending on the current settings. Unknown posts are added to the local database with tags, metadata and thumbnail information.

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

## 📥 Relation to imported files

The Fetch workflow can complement the importer.

Imported local files may already have a local path and an optional detected post ID, but they may still need metadata. When a Danbooru post ID is known, metadata fetching can enrich imported entries with:

- tags,
- rating,
- score,
- parent/child information,
- preview/thumbnail data,
- original Danbooru link generation.

In short: the importer tells the database that local files exist; Fetch can help teach those files who they are. Very dramatic, very database.

---

## 🖼️ Relation to Previewer and Viewer

The Fetch tab only brings posts into the local review workflow. Decisions are usually made later:

1. Fetch metadata and thumbnails.
2. Triage posts in the Previewer.
3. Open promising posts in the Viewer.
4. Rate, reject, keep, categorize or save.
5. Download and store originals only when needed.

This keeps the local collection cleaner and makes the review process faster.
