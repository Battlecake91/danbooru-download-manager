# Danbooru Manager 1.3.200

## Fixed

- Fixed Importer summaries showing escaped `\n` text in the one-line status label.
- Added Danbooru API throttling and retry handling for HTTP 429 rate-limit responses.
- The MD5 lookup test and other Danbooru API lookups now pause between requests and retry after `Retry-After` when Danbooru asks the client to slow down.

