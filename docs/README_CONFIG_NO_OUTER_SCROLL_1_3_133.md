# Patch 1.3.133 - Config tab no outer scroll

The Config tab no longer wraps the complete tab widget in an outer `QScrollArea`.

## Why

Patch 1.3.132 made the Raw app_settings box expand, but because the entire config content was inside a scroll area, the main config view could start scrolling instead of adapting to the current window height.

## Changed

- Removed the outer `QScrollArea` around the Config tab content.
- The `QTabWidget` is now added directly to the main layout with stretch.
- Raw app_settings still expands inside its tab and uses the remaining vertical space.
- Reduced the Raw app_settings minimum height so it can shrink on smaller windows.
