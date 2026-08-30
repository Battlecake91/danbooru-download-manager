# Danbooru Manager 1.3.201

## Added

- The calculated MD5 lookup test now produces Importer review candidates so matches can be reviewed with the same local/remote comparison view used after a normal scan.
- Importing selected MD5-test candidates now recalculates the file MD5 when the filename does not contain a Danbooru ID or MD5.
- Importer matching now checks a Danbooru post ID first, verifies it against the calculated file MD5, and only then falls back to a calculated file-MD5 Danbooru lookup when needed.
- Exact post-ID+MD5 and file-MD5 matches are treated as high-confidence matches even when filename tags differ.
