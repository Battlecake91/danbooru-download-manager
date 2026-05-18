# Danbooru Tag Sorter Wiki

## Purpose

Danbooru Tag Sorter is a local archiving tool for downloading posts from Danbooru and organizing them into folders based on their tags.

It is designed for users who want repeatable downloads, persistent skip history, and category-based sorting without manually checking every post.

## Core Workflow

The script follows this process:

1. Load `config.yaml`
2. Load the persistent download history
3. Build one or more Danbooru search queries
4. Fetch posts through the Danbooru API
5. Skip posts already listed in the history file
6. Read post tags from the API response
7. Match posts against configured categories
8. Download matching files
9. Sort files into category folders
10. Write successful post IDs to the history file

## Search Modes

### Direct Tag Search

Direct search mode uses the `search_tags` value from the config file.

Example:

```yaml
use_saved_searches: false
search_tags: "example_copyright_tag rating:s"
```

This mode is useful for one-off searches or simple archive jobs.

### Saved Search Mode

Saved search mode loads saved searches from the authenticated Danbooru account.

Example:

```yaml
use_saved_searches: true
saved_search_labels:
  - "artists"
saved_search_extra_tags: "example_copyright_tag rating:s"
```

The script retrieves saved searches from:

```text
/saved_searches.json
```

Each saved search provides a `query` field. The script combines that query with `saved_search_extra_tags`.

Example:

```text
Saved search query: example_artist
Extra tags:         example_copyright_tag rating:s
Final query:        example_artist example_copyright_tag rating:s
```

## Saved Search Filtering

Saved searches can be filtered in two ways.

### Label Filter

```yaml
saved_search_labels:
  - "artists"
```

Only saved searches with at least one matching label are used.

An empty list disables label filtering:

```yaml
saved_search_labels: []
```

### Exact Query Filter

```yaml
saved_search_queries:
  - "example_artist"
  - "another_artist"
```

Only saved searches whose query exactly matches one of the entries are used.

An empty list disables exact query filtering:

```yaml
saved_search_queries: []
```

## Category Rules

Categories decide where downloaded posts are placed.

The recommended format is:

```yaml
categories:
  category_name:
    include:
      - "required_tag"
    exclude:
      - "blocked_tag"
```

A post matches a category when it contains at least one `include` tag and contains no `exclude` tag.

### Example

```yaml
categories:
  character_a:
    include:
      - "example_character_a"
    exclude:
      - "comic"
      - "manga"
```

A post with these tags matches:

```text
example_character_a school_uniform smile
```

A post with these tags does not match:

```text
example_character_a comic
```

## Legacy Category Format

The script also supports the older shorthand format:

```yaml
categories:
  character_a:
    - "example_character_a"
```

This is treated as:

```yaml
categories:
  character_a:
    include:
      - "example_character_a"
    exclude: []
```

## Matching and Sorting

### First Match

```yaml
multi_match_mode: "first"
```

The post is placed into the first matching category based on YAML order.

This is useful when categories are intended to be mutually exclusive.

### Copy All Matches

```yaml
multi_match_mode: "copy_all"
```

The post is placed into every matching category.

The script attempts to use hard links first. If hard links fail, it copies the file.

## Unmatched Posts

If no category matches, the script can either place the file in an unmatched folder or skip it entirely.

### Store Unmatched Posts

```yaml
download_only_matching_categories: false
unmatched_folder: "_unsorted"
```

### Skip Unmatched Posts

```yaml
download_only_matching_categories: true
```

When enabled, unmatched posts are not downloaded and are not written to the history file.

## Download History

The history file stores processed Danbooru post IDs:

```yaml
history_file: "./downloaded_ids.txt"
```

Each line contains a post ID and the generated filename.

Example:

```text
1234567    1234567_example_tag_ab12cd34.jpg
```

The script checks this file before downloading. This means a post is not downloaded again even if the file was deleted, moved, or sorted elsewhere later.

## Limits

### API Page Size

```yaml
limit: 100
```

This controls how many posts are requested per API call. It is not a total limit.

### Per Query Limit

```yaml
max_posts_per_query: 100
```

This limits how many posts are checked for each search query.

### Global Limit

```yaml
max_total_posts: 500
```

This limits how many posts are checked across all queries.

A value of `0` disables the limit.

## Rating Filters

Danbooru rating tags can be used in direct searches and saved search extra tags.

Common ratings:

```text
rating:g  general
rating:s  sensitive
rating:q  questionable
rating:e  explicit
```

To search multiple ratings, use an OR expression:

```yaml
saved_search_extra_tags: "example_copyright_tag ( rating:q or rating:e )"
```

Do not write:

```text
rating:q rating:e
```

That requires both ratings at once, which cannot match a normal Danbooru post.

## Filename Generation

The script generates filenames using important Danbooru tags.

Relevant options:

```yaml
filename_tags_count: 10
filename_max_length: 180
filename_excluded_tags:
  - "1girl"
  - "solo"
```

Filename tag priority:

1. Copyright tags
2. Character tags
3. Artist tags
4. General tags
5. Meta tags

Example output:

```text
1234567_example_series_example_character_school_uniform_ab12cd34.jpg
```

The post ID and short hash are included to reduce filename collisions and make posts easier to trace.

## Temporary Downloads

Files are downloaded into a staging folder first:

```text
_downloads
```

If enabled, the staging file is deleted after sorting:

```yaml
delete_staging_file_after_sort: true
```

This keeps the staging folder from becoming a permanent cache.

## Recommended Repository Layout

```text
.
├── danbooru_downloader.py
├── config.example.yaml
├── README.md
├── .gitignore
└── docs/
    └── wiki.md
```

Recommended `.gitignore`:

```gitignore
config.yaml
downloaded_ids.txt
danbooru_downloads/
*.part
```

## Troubleshooting

### The script downloads too many unrelated posts

Check `saved_search_extra_tags`.

If your saved searches are artist tags, the script will download all posts for those artists unless you add additional filters.

Example:

```yaml
saved_search_extra_tags: "example_copyright_tag rating:s"
```

### The script ignores my total limit

`limit` only controls API page size. Use:

```yaml
max_posts_per_query: 100
max_total_posts: 500
```

### The script downloads unmatched posts

Enable:

```yaml
download_only_matching_categories: true
```

### YAML encoding error

Save `config.yaml` as UTF-8.

### Saved searches are not loaded

Check that:

```yaml
use_saved_searches: true
username: "YOUR_USERNAME"
api_key: "YOUR_API_KEY"
```

are set correctly.

## Operational Notes

Use conservative delays and avoid aggressive scraping behavior. The script is intended for personal archiving and organization, not high-volume mirroring.

Review the generated search queries printed by the script before running large downloads.
