# Importer

This document describes the existing-file importer in Danbooru Download Manager `1.3.189`.

The importer brings an existing local collection into the database-backed workflow without blindly moving, renaming or accepting every file. It first scans and evaluates candidates, then lets the user review the evidence before any final import action is selected.

---

## Three-step workflow

### 1. Import Source

The first page contains only source-related settings:

- source folder,
- target category,
- include subfolders,
- scan action.

During the scan, the status area uses most of the page. When the scan finishes, a compact summary reports values such as:

- scanned files,
- Match,
- Questionable,
- Mismatch,
- already known,
- resolution mismatch among confirmed matches.

**Review scan results** opens the next step.

### 2. Review candidates

The Review page contains the candidate table, confidence filters, thumbnails and comparison actions.

The status log from the Source page is not shown here, leaving the available space for the actual review work.

### 3. Import Process

After selecting import candidates, the large **Import process** button opens the final page.

This page controls what happens during import:

- rename imported files,
- limit renaming to the latest import or use category-wide handling,
- update already-known database records,
- fetch and cache thumbnails.

No import action is started merely by marking rows or checking import boxes.

---

## Candidate identification

The importer requires either:

- a Danbooru post ID in the filename, or
- a 32-character MD5 hash in the filename.

Examples:

```text
1234567.png
1234567_artist_character.png
danbooru_1234567.jpg
9f86d081884c7d659a2feaa0c55ad015.jpg
artist_character_9f86d081884c7d659a2feaa0c55ad015.png
```

MD5 matches are treated as the strongest evidence because they identify the file itself rather than merely reusing a numeric ID.

---

## Foreign-board ID collisions

Other booru sites can use numeric post IDs that overlap with Danbooru. Konachan filenames often contain `Konachan.com -`, but that prefix is not guaranteed.

For numeric-ID candidates, the importer therefore extracts recognizable Danbooru tags from the filename and verifies that **every recognized tag** exists on the fetched Danbooru post.

For example, a filename containing:

```text
smile_1girl_blue_hair
```

is rejected as a mismatch if even one of those recognized tags is absent from the candidate post. A single generic match such as `smile` is not enough to bless the entire ID with false confidence.

Internal hyphens are preserved in real tags:

```text
one-piece_swimsuit
chain-link
```

They are not converted into phantom tags such as `one_piece` or `link`. Spaced dashes used as filename separators remain ignored.

---

## Confidence classes

Candidates are classified as:

- **Match** — strong positive evidence such as exact MD5, matching dimensions with valid tags, or multiple filename tags that all match.
- **Questionable** — insufficient evidence, only one reliable tag, unknown details or a dimension difference that needs review.
- **Mismatch** — missing Danbooru post, foreign-board marker or at least one recognized filename tag absent from the fetched post.

Rows are color-coded and use black text on colored backgrounds for readability.

The three confidence classes are controlled with independent checkboxes, so any combination can be shown.

---

## Candidate table

The important columns are kept together:

```text
Import | Confidence | Post ID | Resolution | Local | Remote | Filename | Reason | Path
```

The table provides:

- local thumbnail,
- remote Danbooru thumbnail,
- local and remote resolution,
- filename and local path,
- classification reason,
- import checkbox.

Candidate text is read-only. Recognized and missing filename-tag evidence is available through tooltips instead of occupying a permanently wide tag column.

Double-clicking the local thumbnail, filename or path opens the local file. Double-clicking the remote thumbnail opens the Danbooru candidate.

---

## Resolution comparison

Resolution indicators distinguish:

- matching dimensions,
- a larger remote original,
- another dimension mismatch,
- unknown dimensions.

The scan summary counts resolution mismatch only for candidates already classified as Match. A mismatched ID does not provide meaningful evidence about whether the local file merely needs a larger version.

### Download best version

When Danbooru provides a larger original, **Download best version** can replace the local file.

The replacement is:

1. downloaded to a temporary `.part` file,
2. validated before replacement,
3. moved into place atomically,
4. renamed if the original uses a different extension,
5. re-evaluated in the candidate list.

A local file is not replaced when the remote candidate is not actually larger.

---

## Side-by-side comparison viewer

**Compare images** opens a dedicated viewer with:

- local image on the left,
- Danbooru candidate on the right,
- large Local File and Danbooru Candidate headings,
- Match, Questionable or Mismatch status between them,
- both resolutions,
- fit-to-window and 100% display modes.

Navigation is available through:

- large left and right arrow buttons,
- Previous and Next controls,
- keyboard Left and Right arrows.

The central **Mark match** and **Mark mismatch** buttons update the candidate immediately and advance to the next visible candidate. The full table is refreshed only when the viewer closes, avoiding a complete thumbnail rebuild after every decision.

The viewer follows the active confidence filters. Import checkboxes do not prevent filtered Mismatch candidates from being reviewed.

---

## Selection actions

The Review page distinguishes row selection from import selection:

- **Mark all** selects every visible table row, equivalent to Ctrl+A for the filtered list.
- **Import all** checks the import boxes for every visible candidate.
- Neither action starts the import.

The final **Import selected** action remains separate.

---

## Supported files

Typical supported formats include:

- `.jpg`
- `.jpeg`
- `.png`
- `.gif`
- `.webp`
- `.mp4`
- `.webm`

Exact support depends on the application and viewer capabilities.

---

## Recommended workflow

1. Back up important local files.
2. Scan a small representative folder.
3. Review Mismatch candidates first.
4. Compare Questionable candidates visually.
5. Check resolution upgrades for confirmed matches.
6. Select the candidates to import.
7. Open Import Process and choose rename/update/thumbnail actions.
8. Import a larger collection only after the small run behaves correctly.

---

## Safety notes

- Do not import from removable paths that will later disappear unless that is intentional.
- Moving files manually after import can invalidate stored local paths.
- A numeric post ID is not proof of identity by itself.
- MD5 is the safest automatic match when present.
- Category-wide rename remains available, but latest-import-only scope avoids renaming thousands of unrelated existing files.

---

## Related documentation

- [`FIRST_TIME_USAGE.md`](FIRST_TIME_USAGE.md)
- [`CONFIGURATION.md`](CONFIGURATION.md)
- [`FETCH_WORKFLOW.md`](FETCH_WORKFLOW.md)
