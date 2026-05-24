# Patch 1.3.132 - Raw app_settings stretches to the bottom

This patch adjusts the Config tab layout so the `Raw app_settings` diagnostic area grows with the available vertical space instead of keeping a mostly fixed height.

Changes:

- The Config tab widget now uses an expanding size policy.
- The Config tab widget is added to its parent layout with stretch.
- Individual tab pages use an expanding size policy.
- The `Raw app_settings` group is added to the Custom tab with stretch.
- The unused bottom stretch in the Custom tab was removed so the raw settings editor consumes the remaining space.
- The raw settings editor keeps a smaller minimum height but expands down to the bottom of the visible area.

The value collapsing/masking behavior from 1.3.131 remains unchanged.
