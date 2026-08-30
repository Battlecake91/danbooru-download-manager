# Danbooru Manager 1.3.199

## Added

- Added an Importer test mode that calculates the real MD5 hash of each local file and checks Danbooru for exact `md5:<hash>` matches.
- The test mode reports matches, misses and errors without importing posts or modifying files.

## Fixed

- Forwarded the existing replacement target parameters into the Importer worker so the **Download best version** action receives its selected file/post context.

