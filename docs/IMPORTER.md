# Importer

The importer allows Danbooru Download Manager `1.3.152` to take existing local image collections and register them inside the local database.

This is useful when images were downloaded before using the manager, when files were sorted manually, or when an older downloader setup should be migrated into the new workflow without losing the existing collection structure.

The importer does not blindly move everything into the application. It scans local folders, extracts useful information from filenames and paths, matches known Danbooru post IDs where possible, and stores the results in the local database for later review, search, rating, categorization and sorting.

---

## 🎯 Purpose

The importer is designed for three main use cases:

- 📁 importing an existing Danbooru download folder,
- 🔄 migrating files from an older downloader version,
- 🧹 registering manually sorted images inside the local database.

After import, files can be searched and managed by:

- post ID,
- local file path,
- category,
- status,
- rating,
- tags, if known or fetched later,
- original Danbooru link, if a post ID is available.

The importer is especially useful when a collection already exists and should not be downloaded again just because the database does not know about it yet. Software pretending your files do not exist is rude; the importer tries not to be.

---

## ⚙️ What the importer does

During an import run, the application scans the selected source folder and tries to identify supported image and media files.

Depending on the available information, the importer can:

- detect existing files,
- extract Danbooru post IDs from filenames,
- recognize Danbooru MD5 hashes in filenames when no post ID is available,
- assign an initial category based on the folder structure,
- register the local file path in the database,
- mark imported files with an import/local status,
- avoid importing the same file multiple times,
- preserve the existing directory structure unless explicitly changed later,
- prepare imported posts for later metadata fetching.

The importer does not require every file to have a valid Danbooru post ID. Files without a detected ID can still be registered as local files, but Danbooru-specific features only become available after the post can be matched to Danbooru metadata.

---

## 🖼️ Supported files

The importer is intended for common image and media files used by Danbooru posts.

Typical supported formats include:

- `.jpg`
- `.jpeg`
- `.png`
- `.gif`
- `.webp`
- `.mp4`
- `.webm`

The exact supported formats may depend on the current application configuration and viewer support.

---

## 🔢 Post ID detection

The importer tries to detect Danbooru post IDs from filenames. If no post ID is available, filenames containing a Danbooru-style MD5 hash can also be useful for matching or later metadata repair. Tiny mercy from the hash gremlins.

Examples of useful filenames:

```text
1234567.png
1234567_artist_character.png
danbooru_1234567.jpg
post_1234567.webp
9f86d081884c7d659a2feaa0c55ad015.jpg
artist_character_9f86d081884c7d659a2feaa0c55ad015.png
```

If a post ID is detected, the application can later fetch metadata from Danbooru and generate the original post link from the configured base URL. If only an MD5 hash is detected, the file can still be registered and may be matched later against known or fetched Danbooru metadata.

Files without a detected post ID can still be tracked locally, but they may remain metadata-limited until manually matched or enriched later.

---

## 🧩 Category handling

The importer can use folder structure as a hint for categories. For example, importing from a folder named after a category can help assign an initial category or local label.

This is intentionally a starting point, not a final verdict. Categories can still be changed in the Viewer, and automatic category rules can later refine the result.

---

## ✅ Recommended workflow

Use the importer carefully the first time:

1. Start with a small folder.
2. Check how many files were detected.
3. Check whether post IDs were detected correctly.
4. Verify local paths and category hints.
5. Fetch missing metadata where possible.
6. Review the imported posts in the Previewer and Viewer.
7. Import larger folders only after the small test behaves correctly.

This avoids large-scale cleanup after a wrong assumption. Databases are very good at remembering mistakes, the little goblins.

---

## ⚠️ Safety notes

- Keep a backup of important local collections before large imports.
- Do not import directly from unstable removable drives unless you know the paths will remain valid.
- Avoid moving imported files manually after import unless you also update or repair their paths in the application.
- Files are registered in the database; they are not automatically re-downloaded just because they were imported.
- A valid post ID improves metadata quality, original link generation and tag-based search.
- A Danbooru MD5 hash in the filename can help identify files that no longer have a post ID in their filename.

---

## 🔗 Related docs

- [`FIRST_TIME_USAGE.md`](FIRST_TIME_USAGE.md) for the first-run importer overview.
- [`CONFIGURATION.md`](CONFIGURATION.md) for folders and output settings.
- [`FETCH_WORKFLOW.md`](FETCH_WORKFLOW.md) for fetching metadata and thumbnails after import.
