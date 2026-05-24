# Patch 1.3.131 - Config raw app_settings cleanup

This patch fixes the diagnostic Raw app_settings area in the Config tab.

Changes:

- Enlarges the Raw app_settings text area so the diagnostic view is usable.
- Adds a short hint explaining that the area is only a diagnostic view.
- Collapses large debug/settings values instead of dumping their full content into the raw view:
  - `llm.system_prompt`
  - `llm.last_fetch_payloads`
  - `llm.last_fetch_payload_summary`
  - `fetch.last_payload`
- Keeps secret settings masked as before.
- Truncates other unexpectedly large values to a short one-line preview.

The actual settings are not removed or changed. Only their raw diagnostic display is made less ridiculous.
