# Portable GitHub Release Updater 1.3.141

This patch adds the first portable self-update workflow for packaged Windows builds.

## What changed

- Added the first packaged-app update workflow. In 1.3.142 the user-facing update check moved into the dedicated **Updates / Help** tab.
- Added GitHub Release lookup through the public GitHub API.
- Added automatic selection of the latest Windows ZIP release asset.
- Added update download into `danbooru_manager_data/updates/`.
- Added a separate portable updater executable: `DanbooruManagerUpdater.exe`.
- Added safe ZIP extraction with path traversal protection.
- Added a preservation list so local user data is not overwritten.
- Updated the release build script so the updater is built and included in the release ZIP.

## Preserved local data

The updater does not overwrite these local paths or file types:

- `danbooru_manager_data/`
- `logs/`
- `updates/`
- `*.db`
- `*.db-wal`
- `*.db-shm`
- `*.log`

This keeps the local database, ratings, categories, thumbnails, logs and update cache intact.

## Release asset expectation

The updater expects the latest GitHub release to contain a Windows ZIP asset, for example:

```text
DanbooruManager_1.3.142_win64.zip
```

The ZIP should contain the packaged application folder, including:

```text
DanbooruManager.exe
DanbooruManagerUpdater.exe
```

## Development mode

The updater is intentionally disabled when the application is started from source code.
Portable self-updates only run in a frozen PyInstaller build, because replacing a source checkout from a release ZIP would be a very creative way to ruin a working tree.
