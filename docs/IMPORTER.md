# Importer

The importer allows Danbooru Download Manager `1.3.156` to take existing local image collections and register them inside the local database.

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
- optionally fetch and cache thumbnails immediately,
- rename only files from the latest import run or all saved files of a category.

The importer requires either a Danbooru post ID or a 32-character MD5 hash in the filename. Files without either identifier are skipped.

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

If a post ID is detected, the importer fetches the matching Danbooru post. Because other booru sites can reuse the same numeric IDs, the importer checks recognizable filename tags against the fetched Danbooru tags. Files prefixed with `Konachan.com -` or files whose meaningful filename tags do not match are skipped.

MD5 matches are treated as authoritative because the hash identifies the actual file rather than merely reusing a numeric ID.

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
5. Enable thumbnail fetching during import when the preview should be ready immediately.
6. Review the imported posts in the Previewer and Viewer.
7. Use “rename latest import only” before considering a category-wide rename.
8. Import larger folders only after the small test behaves correctly.

This avoids large-scale cleanup after a wrong assumption. Databases are very good at remembering mistakes, the little goblins.

---

## ⚠️ Safety notes

- Keep a backup of important local collections before large imports.
- Do not import directly from unstable removable drives unless you know the paths will remain valid.
- Avoid moving imported files manually after import unless you also update or repair their paths in the application.
- Files are registered in the database; they are not automatically re-downloaded just because they were imported.
- A valid post ID improves metadata quality, original link generation and tag-based search.
- A Danbooru MD5 hash in the filename provides the safest match.
- Numeric post IDs are checked against filename tags to reduce collisions with Konachan and other boards.
- Category-wide renaming remains available, but the latest-import-only scope avoids needlessly renaming thousands of older files.

---

## 🔗 Related docs

- [`FIRST_TIME_USAGE.md`](FIRST_TIME_USAGE.md) for the first-run importer overview.
- [`CONFIGURATION.md`](CONFIGURATION.md) for folders and output settings.
- [`FETCH_WORKFLOW.md`](FETCH_WORKFLOW.md) for fetching metadata and thumbnails after import.
