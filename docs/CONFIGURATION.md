# Configuration Setup

Danbooru Download Manager `1.3.152` stores runtime configuration in the local database. YAML files are no longer the main configuration source for normal use.

The application is designed around GUI-managed settings, because repeatedly hand-editing config files is how projects slowly become rituals.

---

## ⚙️ Main configuration areas

Important configuration areas include:

- 🔐 Danbooru credentials and base URL
- 📁 output folders and local runtime data paths
- 🖼️ thumbnail and preview behavior
- 📝 filename pattern and tag priority
- 🧩 categories, category priority and output folders
- 🏷️ tag aliases, scores and filename exclusions
- 📥 importer behavior and local file handling
- 🤖 optional LLM provider settings
- 🌐 UI language and translated labels
- 🔄 update/release behavior for packaged builds

---

## 🔐 Credentials

Danbooru credentials are optional.

Store them only if you want to use authenticated Danbooru API features such as saved searches or account-specific access.

The application may store:

- username,
- API key,
- base URL.

Do not commit or publish a database that contains credentials.

---

## 📁 Local data and output folders

The application tracks local posts, thumbnails, tags and configuration in a local SQLite database.

Typical runtime data includes:

- database file,
- thumbnail cache,
- local post metadata,
- saved/rejected state,
- category decisions,
- user ratings,
- imported file references,
- update downloads.

Final saved files can be written into category-specific folders. This allows each category to behave like its own managed local collection.

---

## 📥 Importer configuration

The importer can register existing local files in the database. Import-related behavior may depend on configured paths, supported file extensions and category/folder mapping.

Importer-related decisions include:

- which folder should be scanned,
- whether folder names should be used as category hints,
- whether detected Danbooru post IDs should be used for metadata fetching,
- how existing local paths should be preserved,
- how imported posts should be labeled or reviewed later.

See [`IMPORTER.md`](IMPORTER.md) for detailed importer behavior.

---

## 📝 Filename patterns

Filename generation can use patterns with placeholders.

Example:

```text
%artist%_%characters%_%general%_%postid%
```

Useful placeholders include typed tag groups and the Danbooru post ID. The exact available placeholders depend on the current application version and configuration UI.

Filename-related options include:

- typed tag priority,
- excluded filename tags,
- maximum filename length,
- replacement of unsafe filesystem characters,
- final filename preview in the Viewer.

---

## 🧩 Categories and rules

Categories define where saved files go and how posts are automatically assigned.

A category can contain rule groups. The intended rule model is:

```text
Group A: tag1 tag2 -tag3
Group B: tag4 tag5
```

This means:

```text
(tag1 AND tag2 AND NOT tag3) OR (tag4 AND tag5)
```

Category behavior includes:

- automatic assignment,
- manual override in the Viewer,
- custom output folder per category,
- category priority,
- rule reasoning dialog,
- include and exclude terms.

---

## 🖼️ Preview and Viewer display

Preview cards can be configured to show selected information, such as:

- post ID,
- Danbooru rating,
- Danbooru score,
- parent state,
- local status,
- category,
- artist tags,
- character tags,
- copyright tags,
- general tags,
- meta tags.

Tags can be displayed as raw Danbooru text or as structured tag groups.

---

### Fetch configuration ownership

The global **API page limit** is configured under **Configuration → Fetch**. Per-run limits such as **Max posts per query** and **Max total posts** belong only to the Fetch tab and its presets; they are intentionally not duplicated as global configuration fields.

## 🤖 LLM settings

LLM integration is experimental. Provider settings and payload behavior remain under **Configuration → Scoring**. The actual **Enable LLM integration** switch is in the Fetch tab and is stored per fetch preset/run.

The configuration can control provider settings and payload behavior. Depending on the setup, payloads may use:

- raw tags,
- aliases,
- normalized tags,
- compacted payloads,
- privacy-oriented transformed tag data.

LLM output should be treated as a suggestion, not as a final decision. Tiny machine oracle, tiny trust budget.

## Saved-search extra tags

`saved_search_extra_tags` is appended to every selected Danbooru saved-search query. It was originally intended for global additions such as a rating filter. In the current GUI workflow, the Fetch tab builds this value from the selected rating checkboxes for each run and preset, so the global default is normally overwritten.

The **Enable LLM integration** master switch is shown both in Configuration → Scoring and in the Fetch tab. Both controls write the same `llm.enabled` setting; the Fetch-tab value is additionally stored with the selected fetch preset.

## Parent/child preference isolation

When one post from a Danbooru parent/child family is saved, the remaining posts in that family no longer count as rejected or separately rated preference examples. This prevents near-duplicate alternatives from creating false negative tag signals merely because one preferred variant was chosen. The saved post itself remains a positive signal.
