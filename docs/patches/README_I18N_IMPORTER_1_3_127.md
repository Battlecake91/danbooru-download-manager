# 1.3.127 - I18N Importer

## Summary

Improves importing existing local Danbooru files into the SQLite database using metadata lookup and safer file handling.

## Scope

**Area:** Import workflow

- Existing files can be connected to database records.
- The importer avoids blind overwrites and reports skipped files.
- Imported posts can participate in scoring and category workflows.

## Release context

This note is part of the accumulated development documentation for Danbooru Download Manager. The first public release is version `1.3.135`, after roughly 150 patches.

## Source note

Original patch note file: `README_I18N_IMPORTER_1_3_127.md`
