# Category Rule Save Fix 1.3.139

Version 1.3.139 fixes a regression from the database module split.

## Problem

Saving category rule groups could fail with:

```text
DatabaseCategoryMixin.parse_category_group_expression() takes 1 positional argument but 2 were given
```

The parser was moved into `app/core/db/categories.py` during the split, but it remained a plain class function. Calling it through `self` caused Python to pass the database instance as an implicit first argument.

## Fix

`parse_category_group_expression()` is now explicitly marked as `@staticmethod`, because it does not use database state. Existing calls through `self.parse_category_group_expression(...)` now work as intended.

## Changed files

- `app/core/db/categories.py`
- `scripts/make_release.py`
- `docs/CHANGELOG.md`
- `docs/README_CATEGORY_RULE_SAVE_FIX_1_3_139.md`
