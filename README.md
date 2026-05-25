# Danbooru Download Manager

**Current version:** `1.3.135`  
**First public release:** `1.3.135`

Danbooru Download Manager is a desktop tool for managing local Danbooru downloads with a review-first workflow: fetch metadata and thumbnails, inspect posts in a fast preview grid, rate them, categorize them, and finally save the originals into clean local folders.

The project started as a vibe-coding experiment. That sounds casual, because apparently humans now name development methods like they are playlist moods, but the result was still real work: the first release took roughly **150 patches** to reach the current state. Vibe-coding helped with speed and iteration, but without understanding the architecture, database model, GUI flow, and the Danbooru API, this would have collapsed into spaghetti with buttons.

> This application is not affiliated with Danbooru. Use it responsibly and respect Danbooru's terms, rate limits, and content rules.

---

## Screenshots

The screenshots below are placeholders. Replace the image files in `docs/screenshots/` with actual captures before publishing the release.

### First-run setup

![First-run setup](docs/screenshots/first-run-setup.png)

### Fetch tab example

![Fetch tab](docs/screenshots/fetch-tab.png)

### Previewer

![Previewer](docs/screenshots/previewer.png)

### Viewer

![Viewer](docs/screenshots/viewer.png)

---

## Highlights

- **Local Danbooru download management** with a SQLite database for posts, tags, ratings, categories, file paths, and local state.
- **Later lookup and search** by tag, post ID, original Danbooru link, status, category, rating, and local metadata.
- **Preview-first workflow**: load post metadata and thumbnails first, download full files only when they are selected or saved.
- **Viewer workflow** with image display, keyboard-driven rating/status/category handling, final filename preview, and manual review actions.
- **Category system** with automatic assignment, dedicated output folders, category priority, include/exclude rules, and manual override.
- **Personal rating system** for preselection and future learning behavior.
- **Learning-oriented recommendation structure** based on accepted, rejected, scored, and categorized posts.
- **Experimental LLM integration** for post preselection and category assistance.
- **Local tag catalog** for autocomplete and tag maintenance, including optional import of the most popular Danbooru tags.
- **Structured tag display** for artist, character, copyright, general, and meta tags.
- **Configurable filename patterns**, including typed tag placeholders and post IDs.
- **Importer for existing local files** using Danbooru MD5 lookup where possible.
- **PyInstaller-oriented runtime path handling** for packaged Windows builds.

---

## Typical workflow

1. Start the application.
2. Complete the first-run setup.
3. Configure credentials, folders, categories, filename rules, and preview settings.
4. Use the **Fetch** tab to load posts from manual tags, saved searches, or presets.
5. Review posts in the **Previewer**.
6. Open interesting posts in the **Viewer**.
7. Rate, reject, keep, categorize, or save posts.
8. Let the application write final files into category-specific folders.
9. Search and manage local posts later by tag, post ID, status, category, rating, or original Danbooru link.

---

## First setup

On first start, the application opens a setup window. The goal is to create a usable local database without making you hand-edit config files like it is 2007 and everyone agreed pain was character-building.

### 1. Danbooru API credentials

A Danbooru API key is optional, but recommended.

You can use the application without credentials for public API access, but authenticated access is useful for:

- saved searches,
- more reliable API access,
- account-based Danbooru features,
- avoiding some anonymous-access limitations.

The setup window can store:

- Danbooru username,
- Danbooru API key,
- base URL.

Credentials are stored locally in the application database/configuration. Do not publish your database if it contains credentials.

### 2. Initial popular tag import

The setup can import the **X most popular Danbooru tags** into the local tag catalog. This is used for autocomplete, tag editing, alias work, and faster rule creation.

Recommended values:

| Tag count | Use case |
|---:|---|
| `5,000` | Fast startup, small database, enough for a first test. |
| `10,000` | Good default for normal use. |
| `20,000` | Better autocomplete coverage without getting silly. |
| `50,000+` | Useful for heavy tag work, but slower and larger. Only do this if you know why. |

A sensible first setup value is **10,000 to 20,000 tags**. It covers common tags well while keeping the database and first-run time reasonable. Importing every possible Danbooru tag is usually not necessary unless the machine exists only to suffer beautifully under tag metadata.

### 3. Default preview sample post

Version `1.3.135` uses Danbooru post `11199825` as the default preview sample post. It is fetched during first setup when the sample import is enabled, then stored in the local database so the preview card configuration can be tested immediately.

---

## Fetch tab

The **Fetch** tab is where new Danbooru posts are discovered and imported into the local database.

It does not have to download full image files immediately. In the normal workflow, it loads post metadata and thumbnails first. This keeps the review process fast and avoids filling folders with posts you will reject three seconds later, which is progress of a kind.

### Search modes

The Fetch tab supports several ways to define what should be loaded:

- **Manual tag query**: enter a Danbooru tag expression directly.
- **Presets**: save reusable fetch configurations for common searches.
- **Saved searches**: use Danbooru saved searches when credentials are configured.
- **Rating filters**: include or exclude General, Safe, Questionable, or Explicit posts.
- **Additional query constraints**: append extra tags or filters to loaded searches.

### Fetch limits

The tab can limit how much data is processed:

- maximum posts per query,
- maximum total posts,
- minimum unknown posts per query,
- thumbnail loading behavior,
- status filters for known or unknown posts.

Known posts can be skipped, updated, or reused depending on the current settings. Unknown posts are added to the database with tags, metadata, and thumbnail information.

### Results

After a fetch run, the application shows a summary such as:

- processed queries,
- checked posts,
- new posts,
- known or updated posts,
- loaded thumbnails.

Fetched posts then appear in the Previewer and can be filtered, sorted, rated, opened, rejected, or saved.

---

## Previewer

The Previewer is the fast triage area. It displays thumbnail cards and configurable metadata, such as:

- post ID,
- Danbooru rating,
- Danbooru score,
- parent information,
- local status,
- category,
- artist tags,
- character tags,
- copyright tags,
- general tags,
- meta tags.

Tags can be shown either as raw Danbooru tag text or as structured groups. Structured display can make cards much easier to read, especially when artist, character, and copyright information matter more than the usual wall of `tag_with_underscores` misery.

The Previewer also supports filters, sorting, status selection, recommendation information, and category details.

---

## Viewer

The Viewer is used for detailed review and final decisions.

Main actions include:

- inspect the full image or a larger preview,
- assign personal rating,
- set local status,
- select or override category,
- view category reasoning,
- inspect and select typed tags,
- add tags to category rules,
- exclude noisy tags from filenames,
- preview the final filename,
- save the original file into the selected category folder,
- open the original Danbooru post link.

The Viewer is designed around quick manual decisions with keyboard shortcuts and direct tag actions, because clicking through repetitive review work forever would be a bleak little punishment even software should not inflict.

---

## Categories and rules

Categories define where saved files go and how posts are automatically assigned.

A category can contain manual rules based on tags. Rules support include and exclude logic. The intended model is intuitive:

```text
Group A: tag1 tag2 -tag3
Group B: tag4 tag5
```

This means:

```text
(tag1 AND tag2 AND NOT tag3) OR (tag4 AND tag5)
```

Categories can have priority, so when multiple categories match, the preferred category can win. Manual category assignment in the Viewer remains possible.

---

## Rating and learning structure

The local rating system is separate from Danbooru's public score or content rating. It represents your own preference and review decision.

The database tracks enough information to support learning-style recommendations later:

- saved posts,
- rejected posts,
- personal ratings,
- tag scores,
- category decisions,
- aliases and normalized tags,
- local post status.

The recommendation and LLM systems can use this structure to influence preselection and category suggestions. The LLM feature is currently experimental and should be treated as assistance, not truth handed down from a silicon oracle with questionable taste.

---

## LLM integration: experimental

The LLM integration can prepare compact post payloads and ask a configured backend to help with preselection or category suggestions.

Depending on configuration, payloads can use raw tags, aliases, normalized tags, or privacy-oriented transformed tag data. The goal is to provide useful decision hints while keeping the workflow local-first and controllable.

This feature is experimental in version `1.3.135`.

---

## Installation from source

Requirements:

- Python 3.11 or newer recommended,
- Windows or Linux desktop environment,
- dependencies from `requirements.txt`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

The GUI starts by default when no CLI action is given.

---

## Building a Windows executable

The repository contains PyInstaller-oriented build support.

```powershell
.\scripts\build_windows.ps1
```

Runtime data is intended to stay next to the executable in packaged builds, so a portable release can keep its database, thumbnails, and settings together.

---

## Documentation

Additional release notes and implementation notes are stored in [`docs/`](docs/).

The generated changelog is available here:

- [`docs/CHANGELOG.md`](docs/CHANGELOG.md)

The changelog is based on the patch documentation accumulated during development. The first public release, `1.3.135`, represents the result of roughly **150 patches**.

---

## Repository layout

```text
app/
  core/          database, config, filenames, categories, paths
  danbooru/      Danbooru API and thumbnail cache
  gui/           PySide6 windows, tabs, viewer, preview grid
  i18n/          translation helpers and UI language support
  services/      fetch, import, final save, LLM payloads, tag catalog

docs/            patch notes, release notes, changelog, screenshots
scripts/         build helper scripts
main.py          application entry point
```

---

## Version

```text
1.3.135
```

This is the current version and the first public release.

---

## License

See [`LICENSE`](LICENSE).
