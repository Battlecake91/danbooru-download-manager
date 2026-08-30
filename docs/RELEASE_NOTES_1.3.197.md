# Danbooru Manager 1.3.197

## Fixed

- Moved rejected-cache cleanup out of the synchronous application startup path.
- The GUI now schedules rejected-cache cleanup in a background worker after startup, so slow disks, network paths or many rejected rows no longer delay the first window.
- Added a regression guard to keep rejected-cache purging out of `main.py` startup.

