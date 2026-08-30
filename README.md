# Danbooru Download Manager

> **Current release:** `1.3.198`
> Version `1.3.195` adds Viewer preview-strip controls, Fetch-exclude workflow controls, richer Help guidance, guarded layout/statistics fixes and Linux CI runtime fixes.
> A local Danbooru collection manager for fetching, reviewing, importing, rating, categorizing and organizing posts with a database-backed workflow.

Danbooru Download Manager is a Windows-oriented desktop application for managing a local Danbooru image collection. It uses a local SQLite database to keep metadata, thumbnails, ratings, statuses, categories, tag settings and file locations together instead of scattering state across filenames and folders.

The central workflow is deliberately metadata-first:

1. Fetch post metadata and thumbnails.
2. Review candidates in the Previewer.
3. Inspect and rate posts in the Viewer.
4. Download or save only the files worth keeping.
5. Import existing collections through a separate scan-and-review workflow.

---

## Highlights

- **Database-backed local library**  
  Track pending, saved, rejected, imported and downloaded posts, including tags, ratings, categories, parent/child information and local file paths.

- **Fetch presets and saved searches**  
  Use manual Danbooru queries, reusable presets or authenticated saved searches with per-preset limits, rating selection, optional LLM processing and original-resolution limits.

- **Fetch exclusion blacklist**  
  Exclude unwanted tags before posts enter the database or thumbnail cache. Tags can be added through the Viewer or managed in the Tag tab.

- **Previewer and Viewer workflow**  
  Filter, sort and search fetched posts, then rate, categorize, reject, save or inspect them in detail.

- **Three-step importer**  
  Scan a folder, review likely matches, compare local and remote images, then choose the final import actions such as renaming and thumbnail fetching.

- **Importer identity checks**  
  Resolve files through Danbooru MD5 hashes or post IDs, validate recognized filename tags, detect likely foreign-board ID collisions and compare local versus remote resolution.

- **Side-by-side import comparison**  
  Compare local and Danbooru images directly, navigate with buttons or arrow keys, and manually mark candidates as Match or Mismatch.

- **Resolution-aware workflows**  
  Prevent unsuitable posts from entering Fetch results and replace lower-resolution imported files with Danbooru's best available version.

- **Categories and rule groups**  
  Automatically suggest categories through grouped include/exclude rules while preserving manual control in the Viewer.

- **Tag tools and scoring**  
  Manage aliases, manual scores, filename exclusions, fetch exclusions and typed tag groups. Parent/child alternatives are isolated from preference learning after one family member is saved.

- **Concurrent database access**  
  A process-wide FIFO write coordinator serializes Fetch, Importer and Configuration writes while read-only Previewer queries remain available through SQLite WAL mode.

- **Optional experimental LLM support**  
  Build compact tag-based payloads for assisted preselection and category suggestions. Manual decisions remain authoritative, because outsourcing taste entirely to a probability engine would be a rather bleak hobby.

- **Portable Windows release and updater foundation**  
  Release builds can check GitHub releases and update while preserving local application data.

---

## Screenshots

### First-time setup

![First-time setup](docs/screenshots/first-run-setup.png)

### Fetch tab

![Fetch tab](docs/screenshots/fetch-tab.png)

### Previewer

![Previewer](docs/screenshots/previewer.png)

### Viewer

![Viewer](docs/screenshots/viewer.png)

---

## Quick start

### Release build

Download the ZIP for your operating system from the GitHub release, extract it completely, then run the application from the extracted folder.

Windows builds contain:

```text
DanbooruManager.exe
```

Linux builds contain:

```text
DanbooruManager
```

Do not start the application from inside the ZIP. Operating systems already invent enough filesystem folklore without assistance.

### From source

```bash
python main.py
```

Install dependencies first:

```bash
pip install -r requirements.txt
```

### Building releases

Portable folder-style build for the current platform:

```bash
python scripts/make_release.py --allow-dirty
```

Single-executable build for the current platform:

```bash
python scripts/make_release.py --allow-dirty --onefile
```

Release ZIPs are written to `release/` and include the platform and bundle type in the filename, for example `DanbooruManager_1.3.198_win64_portable.zip` or `DanbooruManager_1.3.198_linux_x86_64_onefile.zip`.

---

## First-time setup

On first start, the application creates its local data directory and SQLite database. The setup can configure:

- Danbooru username and API key,
- Danbooru base URL,
- initial import of popular Danbooru tags,
- the default sample post,
- initial access to the existing-file importer.

Authenticated access is recommended for saved searches and account-specific API features. The default sample post is Danbooru post `11199825`.

See [`docs/FIRST_TIME_USAGE.md`](docs/FIRST_TIME_USAGE.md).

---

## Fetch workflow

The Fetch tab discovers posts and stores metadata and thumbnails before original files are downloaded.

A fetch preset can contain:

- a manual tag query or saved-search selection,
- General, Sensitive, Questionable and Explicit rating choices,
- maximum posts per query and total posts,
- minimum unknown posts per query,
- LLM enable state,
- minimum and maximum width and height.

Empty resolution fields or `0` mean unrestricted. Posts outside active limits are rejected before database insertion and thumbnail download.

The persistent **Fetch exclude** list acts as a tag blacklist. Any post containing an excluded tag is skipped before it enters the local review workflow.

See [`docs/FETCH_WORKFLOW.md`](docs/FETCH_WORKFLOW.md).

---

## Previewer and Viewer

The Previewer is the main triage view. It supports status filters, text search, sorting, configurable card information, structured tag display and category/recommendation information.

The Viewer provides the detailed decision workflow:

- inspect the image and typed tags,
- assign a personal rating,
- set status,
- choose or override a category,
- inspect category reasoning,
- edit tag aliases and scores,
- exclude tags from filenames or future fetches,
- save the final original file.

Window and toolbar layouts are recalculated after startup and tab changes to avoid controls being pushed outside the visible area.

---

## Importing existing collections

The importer uses a three-step workflow:

1. **Import Source**  
   Select folder, category and subfolder handling, then scan.
2. **Review**  
   Filter Match, Questionable and Mismatch candidates; inspect thumbnails; compare images; select rows and import checkboxes.
3. **Import Process**  
   Choose final actions such as renaming, updating existing records and fetching thumbnails.

The scanner can:

- recognize Danbooru MD5 hashes and post IDs in filenames,
- compare every recognized filename tag with the fetched Danbooru post,
- preserve hyphenated tags such as `one-piece_swimsuit` and `chain-link`,
- detect probable Konachan or other foreign-board ID collisions,
- compare local and remote image dimensions,
- show local and remote thumbnails,
- open either file externally,
- compare both images side by side,
- replace a lower-resolution local file with Danbooru's best version,
- rename only the latest import instead of an entire category,
- optionally fetch thumbnails during import.

See [`docs/IMPORTER.md`](docs/IMPORTER.md).

---

## Categories and rules

Category rules are organized as OR-connected groups. Terms inside a group are AND-connected, with `-tag` used for exclusions.

```text
Group A: tag1 tag2 -tag3
Group B: tag4 tag5
```

This means:

```text
(tag1 AND tag2 AND NOT tag3) OR (tag4 AND tag5)
```

The first matching category follows category priority, but the Viewer can override the result manually.

---

## Database behavior

SQLite runs in WAL mode. Each worker owns its own connection, while a central FIFO coordinator serializes writes from Fetch, Importer, Configuration and other mutating workflows.

Read-only Previewer requests remain concurrent. GUI settings are written through background workers where necessary, and the Preview tag identity path is intentionally read-only to prevent stale write slots between repeated Fetch runs.

See [`docs/DATABASE_ACCESS.md`](docs/DATABASE_ACCESS.md).

---

## Documentation

| Document | Purpose |
|---|---|
| [`docs/FIRST_TIME_USAGE.md`](docs/FIRST_TIME_USAGE.md) | First start and initial setup |
| [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) | Database-backed application settings |
| [`docs/FETCH_WORKFLOW.md`](docs/FETCH_WORKFLOW.md) | Queries, presets, limits, ratings, exclusions and resolution filtering |
| [`docs/IMPORTER.md`](docs/IMPORTER.md) | Existing-file scan, review, comparison and import workflow |
| [`docs/DATABASE_ACCESS.md`](docs/DATABASE_ACCESS.md) | SQLite connection and write-coordination model |
| [`docs/TESTING.md`](docs/TESTING.md) | Functional testing scope and limitations |
| [`docs/RELEASE_WORKFLOW.md`](docs/RELEASE_WORKFLOW.md) | Push, build and release workflow |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Milestone-oriented project history |
| [`docs/RELEASE_NOTES_1.3.198.md`](docs/RELEASE_NOTES_1.3.198.md) | Changes included in this release |

---

## Planned improvements

- more task-oriented user documentation,
- broader Help-tab coverage and tooltips,
- additional quality-of-life improvements,
- more LLM validation and provider testing,
- optional list-oriented library views.

---

## Notes

- Keep backups of important local collections and the application database.
- Do not publish a database containing credentials.
- Treat LLM output as a suggestion.
- The application is primarily tested on Windows.
