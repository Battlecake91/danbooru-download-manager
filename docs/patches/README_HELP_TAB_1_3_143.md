# Help Tab Structure (1.3.143)

Version 1.3.143 moves all user-facing help and update entry points into a dedicated top-level **Help** tab.

## Changes

- Removed the remaining top menu entry named **Help**.
- Added a top-level **Help** tab.
- Added internal sub-tabs inside Help:
  - **About**: application name, version and repository information.
  - **Update**: portable GitHub release update workflow.
  - **How to**: placeholder for future built-in guides.
- Fixed lazy tab loading by importing `QApplication` in `app/gui/app_window.py`.

The actual detailed setup and workflow documentation remains in the README and `/docs` until the in-app How-to pages are expanded.
