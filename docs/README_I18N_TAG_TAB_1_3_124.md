# Patch 1.3.124 - Tag tab i18n

This patch migrates the tag overview/configuration tab to the shared i18n layer.

## Changed

- `app/gui/tag_tab.py`
  - hard-coded visible German UI strings were replaced with `tr(...)`/`self.t(...)`
  - toolbar labels, placeholder, reload button, table headers and hint text now use locale keys
  - context menu entries for category rules, filename exclusions, scoring/usage flags, alias actions, similar-tag search and clipboard/search actions now use locale keys
  - dialogs for alias editing, similar tag bulk actions, manual score editing and validation warnings now use locale keys
  - yes/flag cells now use a localized `common.yes` text

- `app/i18n/locales/en.json`
  - added tag-tab keys

- `app/i18n/locales/de.json`
  - added matching fallback keys, currently English to keep the UI English-first during migration

## Notes

The next visible tabs still worth migrating are importer, maintenance, category and the remaining config areas.
