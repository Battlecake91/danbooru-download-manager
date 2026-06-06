## 1.3.179 - Prevent queued Config saves from stalling Fetch

- Stop re-applying `PRAGMA journal_mode=WAL` whenever a worker opens a database connection.
- Read the persistent journal mode first and only change it when the database is not already using WAL.
- Prevent short-lived Configuration workers from holding the application write queue while SQLite waits for an exclusive journal-mode lock.
- Keep Configuration saves asynchronous while allowing an active Fetch to continue committing posts.

## 1.3.178 - Non-blocking configuration writes

- Moved Configuration saves off the GUI thread into a dedicated database worker.
- Queue configuration writes behind active Fetch transactions without freezing the interface.
- Use a separate SQLite connection owned by the save worker thread.
- Apply runtime settings only after the queued database transaction commits successfully.
- Prevent repeated Save clicks while a configuration write is pending.

## 1.3.177 - Central SQLite write coordination

- Added one process-wide FIFO write coordinator per database file.
- Serialize write transactions from Fetch, Importer, Configuration, Viewer actions and maintenance tools before they reach SQLite.
- Keep read-only Previewer queries concurrent while a writer is active by retaining WAL mode.
- Hold the write slot from the first mutating statement until commit or rollback.
- Release queued writers safely when a connection commits, rolls back, closes or fails.
- Route schema scripts, WAL checkpoints and VACUUM through the same coordinator.
- Retain SQLite busy-timeout retries as protection against external processes.

## 1.3.175

### Fetch resolution filtering

- Moved the advanced resolution filter from Previewer to Fetch.
- Added preset-specific minimum and maximum width and height limits.
- Posts outside the configured dimensions are skipped before database storage and thumbnail caching.
- Added resolution-excluded counts to the fetch summary.

## 1.3.174 - Preview resolution filters

- Added an **Advanced Filter** dialog to the Previewer.
- Added minimum and maximum width and height filters.
- Treat empty fields and zero as no limit.
- Apply resolution limits directly in the database query before preview cards are loaded.
- Exclude posts with unknown dimensions when a corresponding resolution limit is active.
- Mark the Advanced Filter button while resolution limits are enabled.

## 1.3.173 - Reliable initial window layout

- Recalculate nested tab and toolbar layouts after the main window receives its final screen geometry.
- Repeat the initial layout pass shortly after showing the window to accommodate delayed Windows/Qt frame sizing.
- Refresh the active tab layout after tab changes.
- Make the Preview search field flexible so Search and Clear remain visible at narrower widths.
- Clamp the initial window size to the available desktop area.

## 1.3.172 - Prominent review-to-import transition

- Replaced the small corner button with a dedicated full-width next-step panel below the candidate table.
- Enlarged the **Import process** button and made it visually prominent.
- Added a live selected-candidate summary directly above the button.
- Keep the button disabled until at least one candidate is checked for import.

## 1.3.171 - Importer status-area layout cleanup

- Moved the progress and log area into the Source step instead of displaying it below every workflow page.
- Let the scan-status area consume the remaining Source-page height, with a larger minimum log size.
- Kept the completed scan statistics in a compact single-line summary.
- Removed the progress and log area entirely from the Review step.
- Reuse the same status area in the final Import Process step while an import is running.

## 1.3.170 - Import scan summary and navigation fixes

- Enlarged the source-page scan summary and used the remaining page space for readable scan results.
- Added a prominent full-width **Review scan results** button below the completed statistics.
- Hide the review button until a scan has produced candidates and show it reliably after completion.
- Count resolution mismatches only for candidates already classified as matches.
- Improved the shared scan-status text readability.

## 1.3.169 - Three-step importer workflow

- Reorganized the importer into Source, Review and Import Process steps.
- Limited Import Source to folder, category and subfolder settings.
- Added a scan-completion summary with matched, questionable, mismatched, already-known and resolution-mismatch counts.
- Added an explicit transition from scan statistics to the candidate review list.
- Moved rename, existing-post and thumbnail actions to the final Import Process step.
- Kept candidate filtering, comparison and selection in the dedicated Review step.

## 1.3.168 - Importer row selection and comparison controls

- Changed **Mark all** to select every visible table row, matching Ctrl+A semantics without changing import checkboxes.
- Kept **Import all** as the bulk action that checks the import boxes for the current filtered view.
- Added large previous and next arrow buttons beside the comparison images.
- Added Left and Right arrow-key navigation in the comparison viewer.
- Moved the Match and Mismatch decision buttons between the local and Danbooru images.

## 1.3.167 - Importer filtered selection fixes

- Changed **Import all** to only check every candidate in the current filtered view instead of starting the import immediately.
- Fixed **Mark all** for mismatch rows by keeping all candidate checkboxes user-checkable.
- Changed comparison-viewer navigation to use the active confidence filter independently of import checkboxes.
- Allowed filtered Wrong-ID candidates to be reviewed even when they are initially unchecked.

## 1.3.166 - Importer review selection workflow

- Added a prominent Match, Mismatch or Questionable status badge between the local and Danbooru headings in the comparison viewer.
- Increased the Local file and Danbooru candidate heading sizes for faster visual orientation.
- Limited comparison-viewer navigation to checked candidates that are visible under the current confidence filters.
- Added **Mark all** for all importable candidates in the current filtered view.
- Added **Import all** to import the complete current filtered view without manually checking every row.

## 1.3.165 - Faster importer comparison decisions

- Added native maximize and minimize controls to the importer comparison viewer.
- Removed the full candidate-table rebuild from every manual match or mismatch decision.
- Refresh the importer table once after the comparison viewer closes instead.
- Make status decisions advance to the next candidate immediately, even with large scans and cached thumbnails.

## 1.3.163 - Preserve hyphenated tags during importer matching

- Preserve internal hyphens while parsing tags from imported filenames.
- Correctly recognize tags such as `one-piece_swimsuit` and `chain-link`.
- Continue treating spaced dashes as filename separators.
- Prevent false mismatch results caused by phantom tags such as `one_piece` or `link`.

## 1.3.162 - Importer thumbnail comparison layout

- Moved the resolution column directly next to the post ID.
- Added local and remote thumbnail columns to the importer candidate list.
- Removed the wide filename-tags column from the main table.
- Kept matched and missing tag evidence available through tooltips on the filename and reason cells.
- Increased candidate row height for readable side-by-side previews.

## 1.3.161

- Highlight resolution mismatches more clearly in the importer review table.
- Add a **Download best version** action when Danbooru provides a higher-resolution file.
- Download Danbooru's original file when available and replace the local candidate atomically.
- Re-evaluate the candidate after replacement and update its path, resolution, and confidence.

## 1.3.160 - Importer confidence filtering and classification

- Replaced the single confidence dropdown with independent checkboxes for high-confidence, questionable and mismatch candidates.
- Allowed any combination of the three confidence classes to be displayed.
- Relaxed high-confidence classification when all recognized filename tags match and there is sufficient positive evidence.
- Kept missing filename tags as a definite mismatch and resolution differences as a caution signal rather than automatic rejection.

## 1.3.159 - Importer candidate inspection

- Added buttons to open the selected local file and the matched remote Danbooru image.
- Double-clicking local-file columns opens the local image; double-clicking other candidate columns opens the remote image.
- Made all candidate table text cells read-only while preserving the import checkbox.

## 1.3.156

- Added filename/tag validation for post-ID imports to avoid Konachan and other booru ID collisions.
- Added an option to fetch thumbnails during existing-file imports.
- Added a rename scope for only the posts imported in the latest run.

# Changelog

## 1.3.158 - Importer review table readability

- Changed the text color of green, yellow and red importer candidate rows to black.
- Kept the normal theme text color for rows without a confidence background.

This changelog summarizes the project history by larger development milestones instead of listing every internal patch. Detailed patch notes are kept under `docs/patches/` for archaeology, blame assignment and other ancient rituals developers pretend are healthy.

---

## 1.3.155 - Shared LLM switch and parent/child scoring isolation

- Restored **Enable LLM integration** in Configuration → Scoring while keeping the same switch available in the Fetch tab.
- Removed the obsolete **Saved Searches** information row from Configuration → Fetch.
- Prevented rejected or separately rated siblings from a parent/child family from becoming negative preference signals once any post in that family has been saved.
- Applied the family isolation consistently to local tag statistics, recommendation scores, LLM preference summaries and LLM positive/negative examples.
- Kept the saved post itself as a positive signal; only the remaining posts in that family are ignored for preference learning.

## 1.3.154 - Fetch option ownership cleanup

- Renamed `rating:s` to **Sensitive** in the Fetch tab.
- Moved the global Danbooru API page limit to Configuration → Fetch.
- Kept per-run **Max posts per query** and **Max total posts** exclusively in the Fetch tab and fetch presets.
- Moved **Enable LLM integration** from Configuration → Scoring to the Fetch tab so it can be stored per preset and per run.
- Removed misleading global UI fields for per-run post limits.

## 1.3.153 - Fetch tag blacklist and rating correction

- Added a persistent **Fetch exclude** tag blacklist.
- Added Viewer and Tag tab context actions to add or remove tags from future fetches.
- Added a sortable **Fetch exclude** column to the Tag tab, including direct toggling.
- Posts containing any fetch-excluded tag are skipped before database import and thumbnail caching.
- Corrected Danbooru ratings: `general` is green and `sensitive` is yellow; `rating:s` is no longer labeled safe.

## 1.3.152 - First official release

`1.3.152` is the first official release of Danbooru Download Manager.

- Finalized the Previewer status checkbox behavior so **All** toggles all status filters consistently.
- Changed passive checkbox edits so they do not immediately reload the Previewer.
- Kept reload behavior for dropdown changes, explicit reload/search actions and Enter in the search field.
- Updated the documentation set for the first official release.
- Integrated importer guidance into the README and first-time usage documentation.
- Clarified planned follow-up work: better usage docs, Help tab tips, quality-of-life improvements and LLM tests.

## 1.3.149 - 1.3.151 - Release packaging, icon and Previewer filter polish

- Fixed release packaging so `DanbooruManagerUpdater.exe` is required and included unless explicitly disabled.
- Corrected the updater spec to build a proper portable updater executable.
- Made the main executable use `assets/app_icon.ico` through the PyInstaller spec.
- Improved Previewer filter application behavior and reduced unnecessary reloads.
- Fixed status filter edge cases around the **All** checkbox.

## 1.3.144 - 1.3.148 - Release automation and updater runtime fixes

- Reworked `make_release.py` around the last stable release script structure.
- Switched PyInstaller invocation to the active Python environment using `sys.executable -m PyInstaller`.
- Added dedicated VSCode tasks/buttons for draft and official release workflows.
- Improved updater runtime detection for packaged releases.
- Fixed viewer tag context actions that failed with ambiguous SQL column names.

## 1.3.139 - 1.3.143 - Release, Help and update workflow polish

- Added a dedicated Help tab with internal pages for About, Update and future help content.
- Moved update checking out of the top-level Help menu and into the Help / Update workflow.
- Added the portable GitHub Release updater for packaged Windows builds.
- Preserved local application data during portable updates while replacing program files.
- Finished remaining English cleanup in the viewer tag context menu.
- Fixed a category rule save regression caused by the database module split.
- Fixed lazy tab loading by importing `QApplication` in the main window module.

## 1.3.136 - 1.3.138 - Source cleanup, database split and default behavior

- Removed remaining German source text from Python files and documented the English cleanup.
- Split the oversized database module into focused `app/core/db/` modules.
- Kept the public `app.core.database` import path compatible after the split.
- Changed the preview tag display fallback from raw tags to structured tags.
- Updated release defaults and maintenance notes around the cleanup work.

## 1.3.135 - Public release candidate baseline

- Established the public release baseline after roughly 150 development patches.
- Added the local Danbooru tag catalog and first-run setup flow.
- Added the default preview sample post and hardened packaged executable paths.
- Included the main workflows: Fetch tab, Previewer, Viewer, ratings, categories, SQLite-backed configuration, importer, configurable filenames and experimental LLM support.

## 1.3.118 - 1.3.134 - English-first UI, configuration and first-run setup

- Moved visible UI text toward the shared internationalization layer.
- Converted major tabs and workflows to English-first operation.
- Improved the configuration UI, raw settings handling and database-backed defaults.
- Added startup and first-run behavior so the application can be used without manual file editing.
- Improved maintenance visibility and repository cleanup documentation.
- Polished GUI layout, colors, density and user-facing presentation.
- Improved importing, Fetch logging, category wording and tag display during the English transition.

## 1.3.105 - 1.3.117 - LLM groundwork, maintenance and importer stability

- Added experimental LLM payload generation, batch preselection and debug visibility.
- Added privacy-oriented tag aliasing and payload compaction for LLM usage.
- Added direct API key configuration for OpenAI-compatible backends.
- Improved LLM category handling and preference context support.
- Added database maintenance tools and improved SQLite locking behavior.
- Improved importer behavior for existing local files, post ID detection and local file labels.
- Improved viewer stability around LLM payload inspection.

## 1.3.87 - 1.3.104 - Preview workflow and card configuration polish

- Expanded preview card configuration for visible metadata such as ID, rating, score, parent, status, category and tag groups.
- Added raw and structured tag display modes for preview cards.
- Added structured tag colors matching the viewer tag categories.
- Improved preview sorting, filtering, loading indicators and auto reload behavior.
- Improved category detail visibility from the preview workflow.
- Improved search and autocomplete behavior in the Previewer.
- Added startup suggestions and lazy tab loading to reduce startup cost.

## 1.3.80 - 1.3.86 - Importer, credentials and tag completion

- Added and stabilized the existing file importer.
- Improved MD5 lookup, safety handling and updates for already known local files.
- Moved credentials and important runtime options into database-backed configuration.
- Improved tag completion identity handling.
- Added thumbnail presets and related configuration improvements.

## 1.3.66 - 1.3.79 - Viewer, Fetch and recommendation workflow improvements

- Improved viewer performance through image caching, UI cache work and next-image prefetching.
- Improved tag selection readability and viewer filename preview behavior.
- Added recommendation scoring, recommendation filtering and related import fixes.
- Improved Fetch progress reporting, final summaries and minimum unknown-post fetch behavior.
- Improved preview status bulk handling and statistics.
- Added clearer global category condition labels.

## 1.3.47 - 1.3.65 - Category rule editor and tag scoring tools

- Reworked category rules around grouped include/exclude expressions.
- Added category priority handling, rule polish and global conditions.
- Added category influence logic based on normalized tag information.
- Added viewer dialogs explaining category decisions and category details.
- Improved tag scoring, ignore flags, inline alias editing and direct option toggles.
- Added bulk actions for similar tags, alias maintenance and tag scoring context menus.

## 1.3.9 - 1.3.46 - Typed tags, filename patterns and viewer layout work

- Added typed Danbooru tag handling for artist, character, copyright, general and meta tags.
- Added configurable filename patterns and database-backed tag priority settings.
- Improved filename preview quality and final original-file download behavior.
- Reworked the viewer layout across multiple iterations for rating, filename preview, tag filtering and compact display.
- Added tag columns, unified tag fonts and improved metadata preview refresh behavior.
- Improved preview loading behavior, manual filtering and status synchronization.

## 1.3.0 - 1.3.8 - Fetch tab and early preview configuration

- Added the Fetch tab workflow for Danbooru metadata, thumbnails, filters, presets and progress reporting.
- Improved Fetch thread/database behavior.
- Added status checkboxes, category filters and preset configuration controls.
- Added the first configuration tab work for moving runtime settings into the GUI.

## 1.0 - 1.2.2 - Core database, tag tab and viewer actions

- Added the first Tag tab with tag display, scoring, aliases and filename-exclude behavior.
- Moved configuration into SQLite-backed storage.
- Added global GUI error logging.
- Added viewer tag actions and fixed viewer query handling.
- Added preview reload debouncing and reduced unnecessary reloads after decisions.

## 0.2 - 0.9 - Early GUI and workflow prototype

- Added the initial GUI shell, colors and thumbnail sizing.
- Added early Previewer and Viewer workflows.
- Added hotkeys, thumbnail source handling and image viewer shortcuts.
- Added manual category assignment and final save workflow.

## Unversioned notes

- Initial project setup and early startup behavior.
- Detailed historical notes remain in `docs/patches/README_*.md` files.

## 1.3.157

### Importer review workflow

- Replaced the direct folder import flow with a scan-and-review candidate list.
- Filename evidence is now strict: every recognized filename tag must exist on the fetched Danbooru post. A single generic match no longer validates an ID.
- Added confidence classes with colored rows: high confidence, questionable, and definite mismatch.
- Added filters for all three confidence classes.
- Added local-versus-Danbooru resolution comparison with match, mismatch, and unknown indicators.
- Definite mismatches are not selected for import by default; questionable candidates remain available for manual decisions.
- The candidate model is prepared for a later side-by-side local/original comparison viewer.

## 1.3.164

### Import comparison viewer

- Added an integrated side-by-side viewer for local files and the suspected Danbooru image.
- Added previous/next navigation through scanned import candidates.
- Added fit-to-window and 100% image display modes.
- Added direct manual Match and Mismatch decisions.
- Manual decisions immediately update candidate confidence and import selection.
- Kept the external remote-image action available from the comparison viewer.
