# Danbooru Download Manager 1.3.191

Version 1.3.191 fixes the portable Windows updater.

## Fixed

- Windows process detection now parses the PID column from `tasklist /FO CSV` exactly.
- The updater no longer mistakes unrelated memory values or other text for the application PID.
- Update activity and failures are written to `danbooru_manager_data/updates/updater.log`.
- The application detects when the updater helper exits immediately instead of silently closing.
- The updater is launched as a detached process so it survives the GUI shutdown.

Local databases, thumbnails, ratings and configuration remain preserved during updates.
