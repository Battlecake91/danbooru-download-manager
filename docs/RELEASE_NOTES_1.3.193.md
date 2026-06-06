# Danbooru Download Manager 1.3.193

Version 1.3.193 is a critical hotfix for Viewer responsiveness and portable-updater safety.

## Fixed

- Fixed the portable updater crashing while waiting for the running application to exit.
- Replaced fragile and localized `tasklist` parsing with direct Windows process detection.
- Prevented updates from deleting `danbooru_saved`, application data, databases, thumbnails, logs or unrelated user folders.
- Allowed the updater target to be provided as either the installation directory or the application executable path.
- Fixed long delays when opening the Manual Score dialog for a tag in the Viewer.
- Prevented Save, Reject and rating changes from freezing the Viewer while tag statistics are updated.
- Retained the lightweight filename-tag metadata path so final filename previews remain responsive on large databases.

## Release workflow

- Draft and official publishing now automatically select `docs/RELEASE_NOTES_<current version>.md`.
- Publishing stops with a clear error if the matching release-notes file is missing.

## Update safety

This release should be used for all future portable updates. Earlier updater builds could remove user-created content from the installation directory. Before updating from an affected build, keep a backup of `danbooru_saved` and `danbooru_manager_data`.

No database migration is required. Existing databases, thumbnails, ratings, configuration and saved files remain compatible.
