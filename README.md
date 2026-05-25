# Danbooru Download Manager

> **First official release:** `1.3.152`  
> A local Danbooru download manager for fetching, previewing, rating, importing, categorizing and organizing Danbooru posts without turning your folders into archaeological debris.

Danbooru Download Manager is a desktop application for managing a local Danbooru-based image collection. It focuses on **metadata-first review**, **local database-backed organization**, **manual control**, and optional experimental automation through scoring and LLM-assisted preselection.

The project was created through **vibe-coding**, but not through button-mashing and wishful thinking. The first official release required roughly **150 patches** to reach this state. Every patch was checked against the workflow it touched, because without understanding the code, the data model and the GUI behavior, this would have collapsed into decorative Python confetti.

---

## ✨ Highlights

- 🗂️ **Local Danbooru library management**  
  Track downloaded, imported, saved, rejected and pending posts in a local SQLite database.

- 🔎 **Search later by tag, post ID and original link**  
  Keep metadata locally so posts can be found again by tags, Danbooru post ID, local status, category and generated original Danbooru link.

- 🧭 **Fetch workflow**  
  Load metadata and thumbnails first, review later, download originals only when needed.

- 🖼️ **Previewer and Viewer workflow**  
  Triage posts quickly in the Previewer, then rate, categorize, reject or save in the Viewer.

- 📥 **Importer for existing collections**  
  Register already downloaded files, detect post IDs from filenames where possible, keep local paths and bring older collections into the database-backed workflow.

- ⭐ **Rating system with learning structure**  
  Use local ratings, saved/rejected decisions, tag scores and manual score adjustments to improve preselection over time.

- 🧩 **Categories with auto-assignment**  
  Define categories with output folders, priorities and manual rules. Use grouped include/exclude logic for automatic assignment.

- 🏷️ **Tag tools**  
  Manage aliases, manual scores, filename exclusions, typed tags and local tag catalog data.

- 🤖 **Experimental LLM integration**  
  Build compact tag payloads for LLM-assisted preselection and category suggestions. Treat it as an assistant, not as a tiny digital judge in a robe.

- 🔄 **Portable updater foundation**  
  Release builds can check GitHub releases and update from official release assets while preserving local data.

---

## 📸 Screenshots

The screenshots below are placeholders stored under `docs/screenshots/`. Replace the image files with real captures before preparing the public release page.

### 🧭 First-time setup

![First-time setup](docs/screenshots/first-run-setup.png)

### 🔎 Fetch tab example

![Fetch tab](docs/screenshots/fetch-tab.png)

### 🖼️ Previewer

![Previewer](docs/screenshots/previewer.png)

### 👁️ Viewer

![Viewer](docs/screenshots/viewer.png)

---

## 🚀 Quick start

### From source

```bash
python main.py
```

### From release build

Download the Windows ZIP from the GitHub release, extract it, and start:

```text
DanbooruManager.exe
```

Do not run the application directly from inside the ZIP. Extract it first. Windows already has enough bad habits.

---

## 🧭 Documentation

The README gives the overview. Detailed usage is split into focused documents so this file does not become a scroll of doom.

| Document | Purpose |
|---|---|
| [`docs/FIRST_TIME_USAGE.md`](docs/FIRST_TIME_USAGE.md) | First start, Danbooru credentials, popular tag import, sample post and importer basics |
| [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) | Database-backed configuration, folders, categories, filename patterns, LLM settings |
| [`docs/FETCH_WORKFLOW.md`](docs/FETCH_WORKFLOW.md) | Fetch tab usage, queries, presets, saved searches, limits and Previewer flow |
| [`docs/IMPORTER.md`](docs/IMPORTER.md) | Detailed importer behavior for existing local files and older collections |
| [`docs/TESTING.md`](docs/TESTING.md) | How the first official release was tested through patch-based validation |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Milestone changelog generated from the patch history |

---

## 🛠️ First-time setup overview

On first start, the application creates its local data folder and database. The setup can optionally configure:

- 🔐 Danbooru username and API key
- 🌐 Danbooru base URL
- 🏷️ initial import of the most popular Danbooru tags
- 🖼️ default preview sample post
- 📥 importer workflow for existing local collections

A Danbooru API key is optional, but recommended if you want saved searches or more reliable authenticated API access.

For the popular tag import, **10,000 to 20,000 tags** is a sensible first setup range. Use `5,000` for quick tests and `50,000+` only if you actually plan to maintain a large local tag catalog. Bigger is not automatically smarter. Sometimes it is just slower with confidence.

See [`docs/FIRST_TIME_USAGE.md`](docs/FIRST_TIME_USAGE.md) for the full setup flow.

---

## 📥 Importing existing files

The importer is meant for existing Danbooru folders, older downloader output or manually sorted collections.

It can:

- scan local folders,
- register existing files in the database,
- detect Danbooru post IDs from filenames where possible,
- preserve local file paths,
- assign initial categories from folder structure,
- prepare imported posts for later metadata fetching,
- make imported posts searchable by local path, post ID, status, rating and tags when available.

This allows the manager to adopt an existing collection instead of pretending years of local files never happened, which would be rude even by software standards.

Detailed importer notes are in [`docs/IMPORTER.md`](docs/IMPORTER.md), with first-run guidance in [`docs/FIRST_TIME_USAGE.md`](docs/FIRST_TIME_USAGE.md).

---

## 🔎 Fetch workflow overview

The Fetch tab brings posts into the local database. It usually fetches metadata and thumbnails first, not full original files.

Supported workflows include:

- manual Danbooru tag queries,
- reusable presets,
- authenticated saved searches,
- rating filters,
- limits for posts per query and total posts,
- known/unknown post handling,
- thumbnail loading,
- fetch summaries.

After fetching, posts are reviewed in the Previewer and Viewer. Originals are downloaded or saved when you decide they are worth keeping.

See [`docs/FETCH_WORKFLOW.md`](docs/FETCH_WORKFLOW.md).

---

## 🧩 Categories and rules

Categories can automatically assign posts based on tag rules and can write final files into separate folders.

Rule groups use a readable include/exclude model:

```text
Group A: tag1 tag2 -tag3
Group B: tag4 tag5
```

Meaning:

```text
(tag1 AND tag2 AND NOT tag3) OR (tag4 AND tag5)
```

Category decisions can be manually overridden in the Viewer, because full automation is how collections become haunted.

---

## 🤖 Experimental LLM support

LLM integration is experimental in `1.3.152`.

The application can prepare payloads based on tags, aliases, local scores and category context. The goal is to support preselection and category suggestions, not to replace review.

Use LLM output as a suggestion. Local ratings and manual decisions remain the main source of truth.

---

## 🧪 Testing and release confidence

`1.3.152` is the **first official release**.

The release was built through roughly **150 patches**. Each patch was tested against the functionality it changed before continuing with the next patch. This included the major GUI flows, database-backed configuration, Fetch, Previewer, Viewer, importer, category rules, tag tools, packaging and release behavior.

This was practical patch-level functional testing, not a full automated test suite. The application should be treated as a usable first official release with some rough edges still expected. The changelog and patch notes provide traceability for the development history.

See [`docs/TESTING.md`](docs/TESTING.md).

---

## 🗺️ Planned improvements

Planned follow-up work includes:

- 📚 better user documentation,
- ❔ a Help tab with useful tips and explanations,
- ✨ quality-of-life improvements,
- 🤖 more LLM tests and validation.

---

## ⚠️ Notes

- Keep backups of important local collections.
- Do not publish databases that contain API credentials.
- Treat LLM suggestions as suggestions.
- Upload large release ZIP files as GitHub release assets, not as normal Git-tracked files. GitHub gets cranky, and for once it has a point.
