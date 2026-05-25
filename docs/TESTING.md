# Testing Notes for Release 1.3.152

Danbooru Download Manager `1.3.152` is the **first official release**.

The release was developed and tested through patch-based iteration. The first official release required roughly **150 patches**. Each patch was tested for the feature, fix or refactor it introduced before the next patch was added.

This does not mean the software is perfect. It means the release was built through repeated functional validation instead of one giant unverified rewrite, which is usually how applications become bug terrariums.

---

## ✅ Patch-based testing approach

The development process followed this pattern:

1. Implement a small feature, fix or UI change.
2. Run the affected workflow manually.
3. Verify that the new behavior works.
4. Check that the surrounding workflow still behaves correctly.
5. Document the patch in `docs/patches/` or the changelog.
6. Continue with the next patch.

This produced a long patch history and a generated milestone changelog.

---

## 🧪 Tested functional areas

Testing focused on the workflows most likely to break during active development.

### Startup and setup

- GUI startup from source
- first-run setup behavior
- database initialization
- default configuration creation
- default preview sample post handling
- packaged executable startup behavior

### Database and configuration

- SQLite-backed configuration
- migration-related behavior
- DB-only configuration handling
- raw settings view
- credential storage paths
- runtime path behavior in packaged builds

### Fetch tab

- manual tag queries
- presets
- saved-search based fetching
- rating filters
- query limits
- fetch summaries
- known/unknown post handling
- thumbnail loading
- UI responsiveness during fetch operations

### Previewer

- thumbnail card loading
- preview card display options
- structured tag display
- tag color grouping
- status filters
- All/status checkbox behavior
- sorting
- search/autocomplete behavior
- recommendation indicators
- category details display
- repaint and reload behavior

### Viewer

- image loading
- navigation
- rating assignment
- status updates
- category assignment and override
- category reasoning dialog
- final filename preview
- save flow
- tag selection and tag actions
- alias and manual score editing from tag context menus
- filename exclusion behavior
- cache/performance behavior

### Categories and rules

- include and exclude rule terms
- grouped category rules
- category priority
- automatic category assignment
- manual category override
- category explanation dialogs
- category tab UI behavior

### Tags and scoring

- local tag catalog import
- tag autocomplete
- aliases
- tag scores
- filename exclusions
- bulk tag actions
- saved/rejected scoring influence
- structured tag categories such as artist, character, copyright, general and meta

### Import and local files

- existing file importer
- Danbooru MD5 lookup where possible
- local file labels
- repair/update behavior
- safeguards against accidental overwrite or duplicate save paths
- post ID detection from filenames

### LLM workflow

- payload creation
- payload compaction
- batch preselection payloads
- provider configuration UI
- debug payload viewer
- category suggestion payload behavior

The LLM functionality remains experimental and was tested as an assistance workflow, not as a fully trusted automatic decision system.

### Packaging, update and release behavior

- PyInstaller path handling
- packaged Windows runtime behavior
- local data paths in packaged builds
- tag catalog behavior after packaging
- release ZIP creation outside the Git repository
- portable updater packaging
- GitHub release asset workflow
- official release visibility for update checks

---

## ⚠️ Known testing limits

The release was tested through practical GUI workflows and patch-level validation. It was not tested with a full automated test suite.

Areas that may still need more validation:

- very large local databases,
- unusual Danbooru API responses,
- network interruptions during long fetches,
- extremely large tag catalogs,
- unusual filename pattern combinations,
- non-Windows packaged builds,
- all possible LLM provider configurations,
- updater behavior across unusual installation folders.

---

## 📌 Release confidence

`1.3.152` should be treated as a functional first official release, not as a final polished enterprise product. The core workflows were repeatedly tested during development, and the patch documentation provides a traceable development history.

Use the application with a normal amount of caution: keep backups of important local collections, avoid publishing credential-containing databases, and do not treat experimental LLM suggestions as final truth.
