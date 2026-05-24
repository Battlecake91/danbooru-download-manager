# 1.3.119 - SQLite-only configuration

The application no longer reads `config.yaml`, `config.example.yaml`, `.env`, or environment variables during normal startup.

## Changed

- `main.py` no longer exposes `--config` or `--env-file`.
- `app/core/config.py` now returns internal defaults only; SQLite `app_settings` remains the leading runtime configuration.
- Danbooru credentials and LLM API keys must be stored through the GUI configuration, which writes to SQLite.
- LLM OpenAI-compatible requests no longer read `LLM_API_KEY`, `OPENAI_API_KEY`, or any other environment fallback.
- Fetch no longer performs the old non-destructive YAML static config import.
- `python-dotenv` was removed from `requirements.txt`.

## Repo cleanup

`config.example.yaml` is obsolete for the GUI/EXE target and should be removed from the repository root. If an old YAML reference is still useful, keep it only as historical documentation under `docs/legacy/`.

`.env` and `.env.example` are no longer part of the application workflow. The database configuration is enough. Humanity may recover from this simplification eventually.
