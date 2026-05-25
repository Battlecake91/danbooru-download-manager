# Database Split 1.3.137

## Summary

Refactors the oversized `app/core/database.py` module into a small compatibility facade plus focused database operation modules under `app/core/db/`.

## Changed files

- `app/core/database.py` now re-exports the public `Database` API and helper functions for backward compatibility.
- `app/core/db/common.py` contains shared constants and helper functions.
- `app/core/db/connection.py` contains connection management, retry-safe execution, and commit helpers.
- `app/core/db/schema.py` contains schema creation, migrations, and index setup.
- `app/core/db/categories.py` contains category and category-rule operations.
- `app/core/db/posts.py` contains preview/post browsing, review status, file paths, and assignment operations.
- `app/core/db/tags.py` contains tag catalog, alias, filename exclude, scoring, and autocomplete operations.
- `app/core/db/llm.py` contains LLM export, anonymization, preference summary, example, and decision persistence operations.
- `app/core/db/maintenance.py` contains database maintenance and size analysis helpers.
- `app/core/db/settings.py` contains app settings and fetch preset persistence.
- `scripts/make_release.py` default version was bumped to `1.3.137`.

## Compatibility

Existing imports such as `from app.core.database import Database` continue to work. Helper imports such as `clamp_number` and `normalize_categories` also remain available from `app.core.database`.

## Validation

- Ran Python compile checks for the refactored database modules.
- Ran a full application compile check over `app`, `main.py`, and `scripts/make_release.py`.
- Verified that `Database`, `clamp_number`, and `normalize_categories` can still be imported through `app.core.database`.
