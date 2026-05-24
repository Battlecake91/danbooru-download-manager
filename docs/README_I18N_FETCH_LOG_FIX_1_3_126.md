# Patch 1.3.126 - i18n Fetch log fix

This patch fixes remaining untranslated Fetch and LLM batch output.

## Changes

- Adds missing Fetch translation keys that previously appeared as raw keys like `fetch.log.starting`.
- Translates Fetch summary labels and LLM summary lines through i18n.
- Translates LLM batch service log messages and skip reasons.
- Fixes unsafe nested f-string quoting in `fetch_tab.py`.

## Validation

```bash
python3 -m compileall -q main.py app
```
