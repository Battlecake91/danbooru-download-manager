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

The container runs as UID/GID `1000:1000` by default. Make sure both bind-mounted directories are writable by that account:

```bash
sudo chown -R 1000:1000 danbooru_manager_data danbooru_saved
```

For a server using another account, set `PUID` and `PGID` before starting Compose.

It binds port 8765 to localhost only. Put an authenticated reverse proxy in front of the container before exposing it to another machine or the internet.

## Shared database

The desktop and web applications use the same SQLite schema. SQLite WAL mode and the existing write coordinator keep access orderly inside each process. For the first deployment, avoid running Fetch or maintenance writes in both applications at the same time. Read-only Preview and Viewer access can coexist with a Fetch.

Container paths override path values stored by a desktop installation. This allows a Windows-created database to be mounted into the Linux container while media remains under `/data` and `/archive`.
Stored Windows thumbnail paths are matched by their portable filename inside the active, saved and rejected thumbnail mounts.
Viewer media prefers local originals and archived files, then Danbooru's large/original URL. Grid thumbnails are used in the Viewer only as a final fallback.
With **Fit** enabled, Viewer media is contained within both the available width and height. Disabling **Fit** shows the native image size in a scrollable area.

## Current web scope

- Manual Fetch with progress and cooperative cancellation.
- Shared Fetch presets with load, save, delete and execution support for tag queries and Danbooru saved searches.
- Automatic Fetch with a configurable interval.
- Consecutive-known-post stopping through the shared Fetch service.
- Endless Preview loading with a configurable batch size.
- Viewer navigation across all posts matching the active status, search and sorting.
- Desktop-style Viewer with the surrounding-post thumbnail strip, typed tag panels, tag metadata, status actions, rating and category controls.
- Desktop Viewer shortcuts: arrow keys for navigation, `1`-`5` for rating, `H`/`N`/`Delete` for status, `O` for the original post, `F` for the real final-save workflow and `Esc` to return.
- Final saving through the shared desktop service, including category selection, filename rules, original download and the mounted archive directory.
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
| `PUID` / `PGID` | `1000` / `1000` | Runtime UID/GID used by Docker Compose |
