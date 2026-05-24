# 1.3.123 - Viewer tag filter i18n and wider tag panel

Changes:

- Translated the remaining filename-tag filter checkbox in the viewer tag panel.
- Added i18n keys for the checkbox and tooltip.
- Increased the viewer side panel width so typed tags, especially character tags, are easier to read.
- Gave the Character column more stretch than Artist/Copyright inside the identity tag row.

Validation:

```bash
python3 -m compileall -q main.py app
```
