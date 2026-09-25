# Web application

The web interface is a separate application entry point. It reuses the database and service layer but does not start, embed or remotely control the Qt desktop application.

## Choose a runtime

Desktop application:

```bash
python main.py
```

Web application:

```bash
pip install -r requirements-web.txt
python web_main.py
```

The default address is `http://127.0.0.1:8765`.

## Docker Compose

```bash
docker compose up --build
```

Compose mounts these directories:

- `./danbooru_manager_data` as `/data` for SQLite, thumbnails and cached originals.
- `./danbooru_saved` as `/archive` for saved files.

It binds port 8765 to localhost only. Put an authenticated reverse proxy in front of the container before exposing it to another machine or the internet.

## Shared database

The desktop and web applications use the same SQLite schema. SQLite WAL mode and the existing write coordinator keep access orderly inside each process. For the first deployment, avoid running Fetch or maintenance writes in both applications at the same time. Read-only Preview and Viewer access can coexist with a Fetch.

Container paths override path values stored by a desktop installation. This allows a Windows-created database to be mounted into the Linux container while media remains under `/data` and `/archive`.

## Current web scope

- Manual Fetch with progress and cooperative cancellation.
- Automatic Fetch with a configurable interval.
- Consecutive-known-post stopping through the shared Fetch service.
- Endless Preview loading with a configurable batch size.
- Viewer navigation across all posts matching the active status, search and sorting.
- Desktop-style Viewer with the surrounding-post thumbnail strip, typed tag panels, tag metadata, status actions, rating and category controls.
- Right-click tag actions in the Viewer and Tags tab for filename and Fetch exclusions, manual scores, legacy scoring and all automatic scoring usage flags.
- Post status, rating and category changes.
- Tag aliases, manual scores and exclusion flags.
- Category creation and deletion.
- Basic configuration and database maintenance status.

The existing-file importer remains desktop-only in this first web milestone. A later web importer will scan explicitly mounted server directories, so it operates on data already present on the server instead of depending on browser filesystem selection.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `DANBOORU_WEB_HOST` | `127.0.0.1` | Listen address outside Docker |
| `DANBOORU_WEB_PORT` | `8765` | HTTP port |
| `DANBOORU_DATA_DIR` | `./danbooru_manager_data` | Database and cache root |
| `DANBOORU_DATABASE_FILE` | `<data>/danbooru_manager.db` | Optional explicit SQLite path |
| `DANBOORU_OUTPUT_DIR` | `./danbooru_saved` | Saved-file root |
