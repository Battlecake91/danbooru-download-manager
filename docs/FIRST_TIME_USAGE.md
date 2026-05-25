# First Time Usage

This document explains the first-run setup for Danbooru Download Manager `1.3.135`.

The first start creates the local application database and prepares the most important defaults. The goal is to get a usable setup without editing config files manually, because apparently suffering through raw config on first launch is not a personality trait worth preserving.

---

## ✅ First-run checklist

1. Start the application with `python main.py` or the packaged executable.
2. Choose or confirm the local application data folder.
3. Optionally enter Danbooru credentials.
4. Decide how many popular Danbooru tags should be imported into the local tag catalog.
5. Optionally import the default sample preview post.
6. Open the Fetch tab and load your first post list.

---

## 🔐 Danbooru API credentials

A Danbooru API key is optional, but recommended.

The application can use public Danbooru API access without credentials, but authenticated access is useful for:

- saved searches,
- more reliable API access,
- account-specific Danbooru features,
- avoiding some anonymous-access limitations.

The setup can store:

- Danbooru username,
- Danbooru API key,
- base URL.

Credentials are stored locally in the application database/configuration. Do not publish your database if it contains credentials.

---

## 🏷️ Initial popular tag import

The setup can import the **X most popular Danbooru tags** into the local tag catalog. This is used for autocomplete, tag editing, alias work, scoring, and faster rule creation.

Recommended values:

| Tag count | Best for | Notes |
|---:|---|---|
| `5,000` | quick test setup | Small database, fast import, enough to verify the workflow. |
| `10,000` | normal first setup | Good default for most users. |
| `20,000` | stronger autocomplete | Better coverage while still staying reasonable. |
| `50,000+` | heavy tag maintenance | Larger DB and slower import. Useful only if you know why. |

A sensible first setup value is **10,000 to 20,000 tags**. It covers common tags well while keeping the database and first-run time reasonable.

Importing every possible Danbooru tag is usually unnecessary. It is possible in theory, but it turns the local database into a tag museum, and not even a charming one.

---

## 🖼️ Default preview sample post

Version `1.3.135` uses Danbooru post `11199825` as the default preview sample post.

When the sample import is enabled, the application fetches this post during first setup and stores it in the local database. This allows the preview card configuration to show a real example immediately.

---

## 🧭 After setup

After the first-run setup, continue with:

- [`CONFIGURATION.md`](CONFIGURATION.md) for folders, credentials, filename patterns, categories, and preview options,
- [`FETCH_WORKFLOW.md`](FETCH_WORKFLOW.md) for loading posts into the local database,
- [`TESTING.md`](TESTING.md) for release validation notes.
