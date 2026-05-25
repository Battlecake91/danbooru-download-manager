# English Source Cleanup 1.3.136

## Summary

This patch removes remaining German user-facing text, log messages, exception messages, and comments from Python source files.

## Changed areas

- Translated configuration validation errors to English.
- Translated Danbooru API, thumbnail, import, download, final-save, and LLM error messages to English.
- Translated category explanation and tag metadata text to English.
- Translated remaining German comments in GUI, database, preview, thumbnail, and import code.
- Updated the release script default version from `1.3.135` to `1.3.136`.

## Validation

- Ran a Python compile check over `app`, `main.py`, and `scripts/make_release.py`.
- Ran a repository text scan for common remaining German source fragments in Python files.

## Notes

The patch intentionally contains only changed source and documentation files. Generated caches, build artifacts, and full repository copies are not included.
