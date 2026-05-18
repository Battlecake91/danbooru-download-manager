# Danbooru Tag Downloader

A Python utility for downloading posts from Danbooru and sorting them into local folders based on post tags.

The script supports normal Danbooru tag searches as well as authenticated saved searches from your Danbooru account. It keeps a persistent download history, so posts are not downloaded again even if the local files are later moved or deleted.

This project was created with the help of AI and then adapted for practical use. Review the code before running it, especially when using authenticated API access.

## Features

- Download posts from Danbooru using tag queries
- Use Danbooru saved searches from your account
- Filter saved searches by label or exact query
- Add extra tags to every saved search query
- Sort downloaded files into folders based on included and excluded tags
- Skip already processed posts using a persistent history file
- Generate descriptive filenames from important Danbooru tags
- Limit posts per query and globally
- Optionally skip posts that do not match any configured category
- Use a temporary staging folder and remove files after sorting
- Supports old and new category config formats

## Requirements

- Python 3.10 or newer
- A Danbooru account if you want to use saved searches
- A Danbooru API key if authentication is required

Install dependencies:

```bash
python -m pip install requests pyyaml
```

On Windows, depending on your Python installation, use:

```powershell
py -m pip install requests pyyaml
```

## Quick Start

Copy the example configuration:

```bash
cp config.example.yaml config.yaml
```

On Windows PowerShell:

```powershell
Copy-Item .\config.example.yaml .\config.yaml
```

Edit `config.yaml` and set your Danbooru username and API key if needed.

Run the downloader:

```bash
python danbooru_downloader.py -c config.yaml
```

On Windows:

```powershell
py .\danbooru_downloader.py -c .\config.yaml
```

## Configuration Overview

The script is controlled by `config.yaml`.

### Basic Search Mode

If `use_saved_searches` is set to `false`, the script uses `search_tags` directly:

```yaml
use_saved_searches: false
search_tags: "some_copyright_tag rating:s"
```

### Saved Search Mode

If `use_saved_searches` is set to `true`, the script loads your saved searches from Danbooru:

```yaml
use_saved_searches: true
saved_search_labels:
  - "artists"
saved_search_extra_tags: "some_copyright_tag ( rating:q or rating:e )"
```

Each matching saved search query is combined with `saved_search_extra_tags`.

For example, if one saved search is:

```text
example_artist
```

and `saved_search_extra_tags` is:

```text
some_copyright_tag rating:s
```

the final Danbooru search becomes:

```text
example_artist some_copyright_tag rating:s
```

### Filtering Saved Searches

Use `saved_search_labels` to only use saved searches with specific Danbooru labels:

```yaml
saved_search_labels:
  - "artists"
```

Use `saved_search_queries` to only use exact saved search queries:

```yaml
saved_search_queries:
  - "example_artist"
  - "another_artist"
```

Leave either list empty to disable that filter.

## Ratings

Danbooru rating tags can be used in `search_tags` or `saved_search_extra_tags`.

Common rating tags:

```text
rating:g  general
rating:s  sensitive
rating:q  questionable
rating:e  explicit
```

To search for multiple ratings, use an OR expression:

```yaml
saved_search_extra_tags: "some_copyright_tag ( rating:q or rating:e )"
```

Do not use this:

```text
rating:q rating:e
```

A single post cannot have both ratings at once.

## Categories

Categories define where posts are sorted after download.

The recommended format supports include and exclude rules:

```yaml
categories:
  character_a:
    include:
      - "character_a_tag"
    exclude:
      - "comic"
      - "manga"

  character_b:
    include:
      - "character_b_tag"
    exclude: []
```

A post matches a category if:

1. It contains at least one tag from `include`
2. It contains no tag from `exclude`

The old short format is also supported:

```yaml
categories:
  character_a:
    - "character_a_tag"
```

This is equivalent to:

```yaml
categories:
  character_a:
    include:
      - "character_a_tag"
    exclude: []
```

## Sorting Behavior

If `multi_match_mode` is set to `first`, a post is sorted into the first matching category based on the order in the YAML file.

```yaml
multi_match_mode: "first"
```

If `multi_match_mode` is set to `copy_all`, the post is placed into all matching categories.

```yaml
multi_match_mode: "copy_all"
```

The script first attempts to use hard links to avoid duplicate storage. If hard links are not possible, it copies the file.

## Unmatched Posts

If a post does not match any category, the default behavior is to place it into the folder defined by `unmatched_folder`.

```yaml
unmatched_folder: "_unsorted"
```

To skip unmatched posts entirely, enable:

```yaml
download_only_matching_categories: true
```

When this option is enabled, unmatched posts are not downloaded and are not written to the history file.

## Download History

The script stores processed post IDs in the configured history file:

```yaml
history_file: "./downloaded_ids.txt"
```

Each successful download is written to this file. Before downloading a post, the script checks whether the post ID already exists in the history file.

This prevents repeated downloads even if local files are later moved, deleted, or manually reorganized.

## Limits

`limit` controls the Danbooru API page size. It does not mean total downloads.

```yaml
limit: 100
```

To limit how many posts are checked per search query:

```yaml
max_posts_per_query: 100
```

To limit how many posts are checked across all queries:

```yaml
max_total_posts: 500
```

Set either value to `0` to disable that limit.

## Filenames

The script can generate descriptive filenames based on important tags.

```yaml
filename_tags_count: 10
filename_max_length: 180
filename_excluded_tags:
  - "1girl"
  - "1boy"
  - "solo"
  - "looking_at_viewer"
```

The filename includes:

- Danbooru post ID
- Important tags
- Short hash
- Original file extension

Example:

```text
1234567_example_series_example_character_school_uniform_ab12cd34.jpg
```

Tag priority for filenames:

1. Copyright tags
2. Character tags
3. Artist tags
4. General tags
5. Meta tags

## Temporary Download Folder

Files are first downloaded into:

```text
_downloads
```

If this option is enabled, the temporary file is removed after sorting:

```yaml
delete_staging_file_after_sort: true
```

The sorted file remains in the target category folder.

Add a license file if you intend to publish or share the project.
