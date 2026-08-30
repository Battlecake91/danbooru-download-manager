# Danbooru Manager 1.3.202

## Added

- Importer matching now checks a Danbooru post ID first and verifies it against the calculated file MD5.
- When the post ID is missing, mismatched, or comes from a known foreign-board filename, the Importer falls back to calculated file-MD5 lookup.
- Exact post-ID+MD5 and file-MD5 matches are treated as high-confidence matches even when filename tags differ.

