# 1.3.128 - i18n tab title fix

Fixes the Importer tab title falling back to a raw translation key.

Changes:

- Keeps the internal lazy-tab key `import` unchanged.
- Maps that internal key to the translation key `tabs.importer` for visible tab labels.
- Adds `tabs.import` as a compatibility alias in both locale files.

Validation:

```bash
python3 -m compileall -q main.py app
```
