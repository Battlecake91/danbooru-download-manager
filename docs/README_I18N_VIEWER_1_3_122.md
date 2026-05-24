# Patch 1.3.122 - Viewer i18n pass

## Goal

Continue the English UI migration by moving the main image viewer to the i18n layer.

## Changed files

- `app/gui/image_viewer.py`
- `app/i18n/locales/en.json`
- `app/i18n/locales/de.json`

## What changed

- Viewer window title and post-specific title are translated.
- Toolbar labels and tooltips are translated.
- Personal rating label and navigation controls are translated.
- Category label, category details button and category status text are translated.
- Parent/child warning, list text and context menu are translated.
- Tag loading messages and filename-exclude messages are translated.
- Filename preview text is translated.
- Save, refetch, delete-local-file and remove-from-database dialogs are translated.
- Tag context menu actions inside the viewer are translated.
- Local image/folder warnings are translated.

## Notes

This patch intentionally focuses on the viewer tab/window. Other tabs still contain German UI strings and should be migrated in separate, smaller patches.
