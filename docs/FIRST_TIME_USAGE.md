# First Time Usage

This document explains the first-run setup for Danbooru Download Manager `1.3.152`.

`1.3.152` is the **first official release**. The first start creates the local application database and prepares the most important defaults. The goal is to make the application usable without hand-editing config files, because raw config files are tools, not initiation rites.

---

## ✅ First-run checklist

1. Start the application with `python main.py` or the packaged `DanbooruManager.exe`.
2. Choose or confirm the local application data folder.
3. Optionally enter Danbooru credentials.
4. Decide how many popular Danbooru tags should be imported into the local tag catalog.
5. Optionally import the default sample preview post.
6. Optionally import an existing local collection.
7. Open the Fetch tab and load your first post list.
8. Review posts in the Previewer and Viewer.

---

## 🔐 Danbooru API credentials

A Danbooru API key is optional, but recommended.

The application can use public Danbooru API access without credentials, but authenticated access is useful for:

- saved searches,
- more reliable API access,
- account-specific Danbooru features,
- avoiding some anonymous-access limitations.

The setup can store:

- Danbooru username,
- Danbooru API key,
- base URL.

Credentials are stored locally in the application database/configuration. Do not publish your database if it contains credentials.

---

## 🏷️ Initial popular tag import

The setup can import the **X most popular Danbooru tags** into the local tag catalog. This is used for autocomplete, tag editing, alias work, scoring, filename exclusions and faster rule creation.

Recommended values:

| Tag count | Best for | Notes |
|---:|---|---|
| `5,000` | quick test setup | Small database, fast import, enough to verify the workflow. |
| `10,000` | normal first setup | Good default for most users. |
| `20,000` | stronger autocomplete | Better coverage while still staying reasonable. |
| `50,000+` | heavy tag maintenance | Larger DB and slower import. Useful only if you know why. |

A sensible first setup value is **10,000 to 20,000 tags**. It covers common tags well while keeping the database and first-run time reasonable.

Importing every possible Danbooru tag is usually unnecessary. It is possible in theory, but it turns the local database into a tag museum. Museums are nice; startup delays are not.

---

## 🖼️ Default preview sample post

Version `1.3.152` uses Danbooru post `11199825` as the default preview sample post.

When the sample import is enabled, the application fetches this post during first setup and stores it in the local database. This gives the preview card configuration a real example immediately.

---

## 📥 Importing an existing collection

If you already have a local Danbooru collection, use the importer instead of downloading everything again.

The importer is useful for:

- existing Danbooru download folders,
- older versions of the downloader,
- manually sorted collections,
- files that should be registered in the database without being moved immediately.

During import, the application can:

- scan a selected folder,
- detect supported image and media files,
- extract Danbooru post IDs from filenames where possible,
- store local file paths,
- assign an initial category based on folder structure,
- mark files as imported/local,
- prepare files for later metadata fetching.

After import, files can be managed by local path, post ID, category, status, rating and tags when metadata is available. If a post ID is known, the application can also generate the original Danbooru link.

A good first importer workflow is:

1. Import a small test folder first.
2. Check detected post IDs and categories.
3. Fetch missing metadata for imported posts where possible.
4. Open the imported posts in the Previewer/Viewer.
5. Only then import larger folders.

This avoids turning one old messy folder into a new database-shaped messy folder. Progress, but not the fake kind.

For full importer details, see [`IMPORTER.md`](IMPORTER.md).

---

## 🧭 After setup

After the first-run setup, continue with:

- [`CONFIGURATION.md`](CONFIGURATION.md) for folders, credentials, filename patterns, categories and preview options,
- [`FETCH_WORKFLOW.md`](FETCH_WORKFLOW.md) for loading posts into the local database,
- [`IMPORTER.md`](IMPORTER.md) for existing local collections,
- [`TESTING.md`](TESTING.md) for release validation notes.
