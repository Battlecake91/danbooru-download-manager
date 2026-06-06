# Danbooru Download Manager 1.3.192

Version 1.3.192 is a focused hotfix for a Viewer freeze affecting large databases.

## Fixed

- The Viewer no longer appears to freeze while generating the final filename preview.
- Filename tag sorting now uses lightweight stored tag metadata instead of recalculating historical aggregates across the post database.
- Opening posts with many tags or a large local database now performs substantially less synchronous database work.

No database migration is required. Local databases, thumbnails, ratings and configuration remain preserved during updates.
