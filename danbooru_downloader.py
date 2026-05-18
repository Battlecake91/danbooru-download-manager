#!/usr/bin/env python3

"""
Danbooru Tag Sorter

Downloads posts from Danbooru and sorts them into local folders based on post tags.

Supported features:
- Direct Danbooru tag searches
- Authenticated Danbooru saved searches
- Saved search filtering by labels or exact query names
- Persistent download history by post ID
- Category include/exclude rules
- Optional skipping of posts that match no category
- Descriptive filenames based on important Danbooru tags
- Per-query and global post limits
- Temporary staging folder cleanup after sorting
"""

import argparse
import hashlib
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import urlparse

import requests
import yaml


def load_config(path: Path) -> Dict[str, Any]:
    """
    Load the YAML configuration file.

    UTF-8 is recommended. UTF-8 with BOM and Windows-1252 are supported as fallbacks
    to avoid common Windows encoding issues.
    """

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    last_error: Optional[Exception] = None
    config: Dict[str, Any] = {}

    for encoding in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            with path.open("r", encoding=encoding) as f:
                config = yaml.safe_load(f) or {}

            print(f"[INFO] Configuration loaded using encoding: {encoding}")
            break

        except UnicodeDecodeError as e:
            last_error = e
    else:
        raise RuntimeError(
            f"Configuration file could not be read. Last encoding error: {last_error}"
        )

    required = [
        "base_url",
        "search_tags",
        "output_dir",
        "history_file",
        "categories",
    ]

    missing = [key for key in required if key not in config]

    if missing:
        raise ValueError(f"Missing required configuration values: {', '.join(missing)}")

    config.setdefault("username", "")
    config.setdefault("api_key", "")

    config.setdefault("use_saved_searches", False)
    config.setdefault("saved_search_labels", [])
    config.setdefault("saved_search_queries", [])
    config.setdefault("saved_search_extra_tags", "")

    config.setdefault("limit", 200)
    config.setdefault("delay_seconds", 1.0)

    config.setdefault("max_posts_per_query", 0)
    config.setdefault("max_total_posts", 0)

    config.setdefault("multi_match_mode", "first")
    config.setdefault("unmatched_folder", "_unsorted")
    config.setdefault("download_only_matching_categories", False)
    config.setdefault("delete_staging_file_after_sort", True)

    config.setdefault("filename_tags_count", 10)
    config.setdefault("filename_max_length", 180)
    config.setdefault("filename_excluded_tags", [])

    return config


def load_history(path: Path) -> Set[int]:
    """
    Load already processed Danbooru post IDs from the history file.
    """

    if not path.exists():
        return set()

    ids: Set[int] = set()

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            first_part = line.split()[0]

            try:
                ids.add(int(first_part))
            except ValueError:
                continue

    return ids


def append_history(path: Path, post_id: int, filename: str) -> None:
    """
    Append a successfully processed post ID to the history file.
    """

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(f"{post_id}\t{filename}\n")


def safe_folder_name(name: str) -> str:
    """
    Convert a category name into a filesystem-safe folder name.
    """

    bad_chars = '<>:"/\\|?*'
    cleaned = "".join("_" if c in bad_chars else c for c in name)
    cleaned = cleaned.strip().strip(".")
    return cleaned or "_invalid"


def safe_filename_part(value: str) -> str:
    """
    Convert a tag into a safe filename component.
    """

    value = value.strip().lower()
    value = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value)
    value = value.strip("._-")

    return value or "tag"


def normalize_string_list(value: Any, field_name: str) -> List[str]:
    """
    Validate and normalize a configuration value that must be a list of strings.
    """

    if value is None:
        return []

    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list.")

    return [str(item).strip() for item in value if str(item).strip()]


def normalize_category_rule(rule: Any, folder: str) -> Dict[str, Set[str]]:
    """
    Normalize a category rule.

    Supported formats:

    Short format:
      category_name:
        - "included_tag"

    Full format:
      category_name:
        include:
          - "included_tag"
        exclude:
          - "excluded_tag"
    """

    if isinstance(rule, list):
        return {
            "include": {
                str(tag).strip()
                for tag in rule
                if str(tag).strip()
            },
            "exclude": set(),
        }

    if isinstance(rule, dict):
        include_raw = rule.get("include", [])
        exclude_raw = rule.get("exclude", [])

        if not isinstance(include_raw, list):
            raise ValueError(f"categories.{folder}.include must be a list.")

        if not isinstance(exclude_raw, list):
            raise ValueError(f"categories.{folder}.exclude must be a list.")

        return {
            "include": {
                str(tag).strip()
                for tag in include_raw
                if str(tag).strip()
            },
            "exclude": {
                str(tag).strip()
                for tag in exclude_raw
                if str(tag).strip()
            },
        }

    raise ValueError(
        f"categories.{folder} must be either a list or a mapping with include/exclude."
    )


def get_tag_list_from_field(post: Dict[str, Any], field: str) -> List[str]:
    """
    Extract a list of tags from a Danbooru tag string field.
    """

    value = post.get(field)

    if not isinstance(value, str):
        return []

    return [tag for tag in value.split() if tag]


def get_post_tags(post: Dict[str, Any]) -> Set[str]:
    """
    Collect all relevant tag fields from a Danbooru post into one set.
    """

    tags: Set[str] = set()

    fields = [
        "tag_string",
        "tag_string_general",
        "tag_string_character",
        "tag_string_copyright",
        "tag_string_artist",
        "tag_string_meta",
    ]

    for field in fields:
        tags.update(get_tag_list_from_field(post, field))

    return tags


def get_filename_priority_tags(
    post: Dict[str, Any],
    max_count: int,
    excluded_tags: Set[str],
) -> List[str]:
    """
    Select tags for descriptive filenames.

    Priority order:
    1. Copyright tags
    2. Character tags
    3. Artist tags
    4. General tags
    5. Meta tags
    """

    ordered_fields = [
        "tag_string_copyright",
        "tag_string_character",
        "tag_string_artist",
        "tag_string_general",
        "tag_string_meta",
    ]

    result: List[str] = []
    seen: Set[str] = set()

    for field in ordered_fields:
        for tag in get_tag_list_from_field(post, field):
            normalized = tag.strip().lower()

            if not normalized:
                continue

            if normalized in excluded_tags:
                continue

            if normalized in seen:
                continue

            seen.add(normalized)
            result.append(normalized)

            if len(result) >= max_count:
                return result

    return result


def matching_categories(
    post_tags: Set[str],
    categories: Dict[str, Any],
) -> List[str]:
    """
    Return all category names that match a post's tags.

    A category matches when:
    - at least one include tag is present
    - no exclude tag is present
    """

    matches: List[str] = []

    for folder, rule in categories.items():
        normalized = normalize_category_rule(rule, folder)

        include_tags = normalized["include"]
        exclude_tags = normalized["exclude"]

        has_include = bool(post_tags & include_tags)
        has_exclude = bool(post_tags & exclude_tags)

        if has_include and not has_exclude:
            matches.append(folder)

    return matches


def choose_file_url(post: Dict[str, Any]) -> Optional[str]:
    """
    Select the best available downloadable file URL from a Danbooru post.
    """

    for key in ["file_url", "large_file_url"]:
        value = post.get(key)

        if isinstance(value, str) and value.startswith("http"):
            return value

    media_asset = post.get("media_asset")

    if isinstance(media_asset, dict):
        variants = media_asset.get("variants")

        if isinstance(variants, list):
            for variant in variants:
                if not isinstance(variant, dict):
                    continue

                url = variant.get("url")

                if isinstance(url, str) and url.startswith("http"):
                    return url

    return None


def extension_from_post_or_url(post: Dict[str, Any], url: str) -> str:
    """
    Determine the file extension from the post metadata or URL.
    """

    ext = post.get("file_ext")

    if isinstance(ext, str) and ext:
        return "." + ext.lower().lstrip(".")

    path = urlparse(url).path
    suffix = Path(path).suffix

    if suffix:
        return suffix.lower()

    return ".bin"


def build_filename(
    post: Dict[str, Any],
    url: str,
    filename_tags_count: int,
    filename_max_length: int,
    excluded_tags: Set[str],
) -> str:
    """
    Build a descriptive and collision-resistant filename for a Danbooru post.
    """

    post_id = post["id"]
    md5 = post.get("md5")

    if isinstance(md5, str) and md5:
        digest = md5[:8]
    else:
        digest = hashlib.sha256(str(post).encode("utf-8")).hexdigest()[:8]

    ext = extension_from_post_or_url(post, url)

    priority_tags = get_filename_priority_tags(
        post=post,
        max_count=filename_tags_count,
        excluded_tags=excluded_tags,
    )

    safe_tags = [safe_filename_part(tag) for tag in priority_tags]

    if safe_tags:
        tag_part = "_".join(safe_tags)
        filename = f"{post_id}_{tag_part}_{digest}{ext}"
    else:
        filename = f"{post_id}_{digest}{ext}"

    if len(filename) <= filename_max_length:
        return filename

    suffix = f"_{digest}{ext}"
    prefix = f"{post_id}_"
    available = filename_max_length - len(prefix) - len(suffix)

    if available <= 0:
        return f"{post_id}_{digest}{ext}"

    shortened_tag_part = "_".join(safe_tags)

    if len(shortened_tag_part) > available:
        shortened_tag_part = shortened_tag_part[:available].rstrip("._-")

    if not shortened_tag_part:
        return f"{post_id}_{digest}{ext}"

    return f"{prefix}{shortened_tag_part}{suffix}"


def download_file(
    session: requests.Session,
    url: str,
    destination: Path,
    delay_seconds: float,
) -> bool:
    """
    Download one file to the destination path using a temporary partial file.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        return True

    temp_path = destination.with_suffix(destination.suffix + ".part")

    try:
        with session.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()

            with temp_path.open("wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

        temp_path.replace(destination)
        time.sleep(delay_seconds)
        return True

    except requests.RequestException as e:
        print(f"[ERROR] Download failed: {url} -> {e}", file=sys.stderr)

    except OSError as e:
        print(
            f"[ERROR] Could not write file: {destination} -> {e}",
            file=sys.stderr,
        )

    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

    return False


def fetch_posts(
    session: requests.Session,
    base_url: str,
    search_tags: str,
    limit: int,
    page: Optional[str],
) -> List[Dict[str, Any]]:
    """
    Fetch one page of posts from Danbooru.
    """

    url = base_url.rstrip("/") + "/posts.json"

    params: Dict[str, Any] = {
        "tags": search_tags,
        "limit": min(int(limit), 200),
    }

    if page:
        params["page"] = page

    response = session.get(url, params=params, timeout=60)
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(f"Unexpected API response: {data}")

    return data


def fetch_saved_searches(
    session: requests.Session,
    base_url: str,
) -> List[Dict[str, Any]]:
    """
    Fetch saved searches for the authenticated Danbooru account.
    """

    url = base_url.rstrip("/") + "/saved_searches.json"

    response = session.get(url, timeout=60)
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(f"Unexpected saved search response: {data}")

    return data


def saved_search_matches_labels(
    item: Dict[str, Any],
    wanted_labels: Set[str],
) -> bool:
    """
    Check whether a saved search matches at least one requested label.
    """

    if not wanted_labels:
        return True

    labels = item.get("labels")

    if not isinstance(labels, list):
        return False

    actual_labels = {
        str(label).strip()
        for label in labels
        if str(label).strip()
    }

    return bool(actual_labels & wanted_labels)


def build_search_queries_from_saved_searches(
    saved_searches: List[Dict[str, Any]],
    wanted_labels: Set[str],
    wanted_queries: Set[str],
    extra_tags: str,
) -> List[str]:
    """
    Build final Danbooru search queries from saved searches.
    """

    queries: List[str] = []
    seen: Set[str] = set()

    extra_tags = extra_tags.strip()

    for item in saved_searches:
        query = str(item.get("query") or "").strip()

        if not query:
            continue

        if wanted_queries and query not in wanted_queries:
            continue

        if not saved_search_matches_labels(item, wanted_labels):
            continue

        full_query = query

        if extra_tags:
            full_query = f"{query} {extra_tags}"

        if full_query in seen:
            continue

        seen.add(full_query)
        queries.append(full_query)

    return queries


def copy_or_link_to_categories(
    source_file: Path,
    output_dir: Path,
    filename: str,
    category_folders: Iterable[str],
) -> None:
    """
    Place a downloaded file into one or more category folders.

    The function attempts to use hard links first to avoid duplicate storage.
    If hard links are not supported, it falls back to copying.
    """

    for folder in category_folders:
        target_dir = output_dir / safe_folder_name(folder)
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / filename

        if target_file.exists():
            continue

        try:
            os.link(source_file, target_file)
        except OSError:
            shutil.copy2(source_file, target_file)


def cleanup_staging_file(path: Path) -> None:
    """
    Remove the temporary staging file after sorting.
    """

    try:
        if path.exists():
            path.unlink()
    except OSError as e:
        print(
            f"[WARNING] Could not remove temporary file: {path} -> {e}",
            file=sys.stderr,
        )


def validate_config(config: Dict[str, Any]) -> None:
    """
    Validate configuration values before starting any downloads.
    """

    categories = config["categories"]

    if not isinstance(categories, dict):
        raise ValueError("categories must be a mapping: folder name -> rule.")

    for folder, rule in categories.items():
        if not isinstance(folder, str):
            raise ValueError("All category names must be strings.")

        normalize_category_rule(rule, folder)

    multi_match_mode = str(config["multi_match_mode"])

    if multi_match_mode not in {"first", "copy_all"}:
        raise ValueError("multi_match_mode must be either 'first' or 'copy_all'.")

    filename_tags_count = int(config["filename_tags_count"])

    if filename_tags_count < 0:
        raise ValueError("filename_tags_count must not be negative.")

    filename_max_length = int(config["filename_max_length"])

    if filename_max_length < 32:
        raise ValueError("filename_max_length is too small. Use at least 32.")

    limit = int(config["limit"])

    if limit < 1:
        raise ValueError("limit must be at least 1.")

    if limit > 200:
        print("[WARNING] limit is greater than 200. Danbooru will be capped at 200.")

    delay_seconds = float(config["delay_seconds"])

    if delay_seconds < 0:
        raise ValueError("delay_seconds must not be negative.")

    max_posts_per_query = int(config["max_posts_per_query"])

    if max_posts_per_query < 0:
        raise ValueError("max_posts_per_query must not be negative.")

    max_total_posts = int(config["max_total_posts"])

    if max_total_posts < 0:
        raise ValueError("max_total_posts must not be negative.")

    normalize_string_list(
        config.get("filename_excluded_tags", []),
        "filename_excluded_tags",
    )

    normalize_string_list(
        config.get("saved_search_labels", []),
        "saved_search_labels",
    )

    normalize_string_list(
        config.get("saved_search_queries", []),
        "saved_search_queries",
    )


def prepare_search_queries(
    session: requests.Session,
    config: Dict[str, Any],
) -> List[str]:
    """
    Prepare the list of final Danbooru search queries.
    """

    base_url = str(config["base_url"])
    search_tags = str(config["search_tags"]).strip()

    use_saved_searches = bool(config["use_saved_searches"])
    username = str(config.get("username") or "").strip()
    api_key = str(config.get("api_key") or "").strip()

    if not use_saved_searches:
        if not search_tags:
            raise ValueError("search_tags must not be empty when saved searches are disabled.")

        return [search_tags]

    if not username or not api_key:
        raise ValueError("use_saved_searches requires username and api_key.")

    saved_search_labels_raw = normalize_string_list(
        config.get("saved_search_labels", []),
        "saved_search_labels",
    )

    saved_search_queries_raw = normalize_string_list(
        config.get("saved_search_queries", []),
        "saved_search_queries",
    )

    saved_search_labels = set(saved_search_labels_raw)
    saved_search_queries = set(saved_search_queries_raw)
    saved_search_extra_tags = str(config.get("saved_search_extra_tags") or "")

    saved_searches = fetch_saved_searches(
        session=session,
        base_url=base_url,
    )

    search_queries = build_search_queries_from_saved_searches(
        saved_searches=saved_searches,
        wanted_labels=saved_search_labels,
        wanted_queries=saved_search_queries,
        extra_tags=saved_search_extra_tags,
    )

    if not search_queries:
        raise ValueError("No matching saved searches were found.")

    print(f"[INFO] Saved searches loaded: {len(saved_searches)}")
    print(f"[INFO] Matching search queries: {len(search_queries)}")

    for query in search_queries:
        print(f"[INFO] Using search query: {query}")

    return search_queries


def process_post(
    post: Dict[str, Any],
    session: requests.Session,
    config: Dict[str, Any],
    downloaded_ids: Set[int],
) -> str:
    """
    Process one Danbooru post.

    Return values:
    - "downloaded"
    - "skipped"
    - "failed"
    """

    post_id = post.get("id")

    if not isinstance(post_id, int):
        return "failed"

    if post_id in downloaded_ids:
        print(f"[SKIP] {post_id} is already listed in the history file.")
        return "skipped"

    output_dir = Path(config["output_dir"])
    history_file = Path(config["history_file"])
    categories = config["categories"]

    delay_seconds = float(config["delay_seconds"])
    multi_match_mode = str(config["multi_match_mode"])
    unmatched_folder = str(config["unmatched_folder"])
    delete_staging_file_after_sort = bool(config["delete_staging_file_after_sort"])
    download_only_matching_categories = bool(config["download_only_matching_categories"])

    filename_tags_count = int(config["filename_tags_count"])
    filename_max_length = int(config["filename_max_length"])

    excluded_tags_raw = normalize_string_list(
        config.get("filename_excluded_tags", []),
        "filename_excluded_tags",
    )

    filename_excluded_tags = {
        tag.strip().lower()
        for tag in excluded_tags_raw
        if tag.strip()
    }

    post_tags = get_post_tags(post)
    matches = matching_categories(post_tags, categories)

    if not matches:
        if download_only_matching_categories:
            print(f"[SKIP] {post_id} does not match any configured category.")
            return "skipped"

        matches = [unmatched_folder]

    if multi_match_mode == "first":
        target_categories = [matches[0]]
    else:
        target_categories = matches

    file_url = choose_file_url(post)

    if not file_url:
        print(f"[SKIP] {post_id} has no downloadable file URL.")
        return "skipped"

    filename = build_filename(
        post=post,
        url=file_url,
        filename_tags_count=filename_tags_count,
        filename_max_length=filename_max_length,
        excluded_tags=filename_excluded_tags,
    )

    staging_dir = output_dir / "_downloads"
    staging_dir.mkdir(parents=True, exist_ok=True)

    staging_file = staging_dir / filename

    ok = download_file(
        session=session,
        url=file_url,
        destination=staging_file,
        delay_seconds=delay_seconds,
    )

    if not ok:
        return "failed"

    copy_or_link_to_categories(
        source_file=staging_file,
        output_dir=output_dir,
        filename=filename,
        category_folders=target_categories,
    )

    if delete_staging_file_after_sort:
        cleanup_staging_file(staging_file)

    append_history(history_file, post_id, filename)
    downloaded_ids.add(post_id)

    print(f"[OK] {post_id} -> {', '.join(target_categories)} / {filename}")

    return "downloaded"


def run_downloader(config: Dict[str, Any]) -> int:
    """
    Run the downloader using the loaded configuration.
    """

    validate_config(config)

    base_url = str(config["base_url"])
    output_dir = Path(config["output_dir"])
    history_file = Path(config["history_file"])
    limit = int(config["limit"])

    max_posts_per_query = int(config.get("max_posts_per_query", 0))
    max_total_posts = int(config.get("max_total_posts", 0))

    output_dir.mkdir(parents=True, exist_ok=True)
    history_file.parent.mkdir(parents=True, exist_ok=True)

    downloaded_ids = load_history(history_file)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "danbooru-tag-sorter/1.5; personal archive script",
        }
    )

    username = str(config.get("username") or "").strip()
    api_key = str(config.get("api_key") or "").strip()

    if username and api_key:
        session.auth = (username, api_key)

    search_queries = prepare_search_queries(
        session=session,
        config=config,
    )

    total_seen = 0
    total_downloaded = 0
    total_skipped = 0
    total_failed = 0

    stop_all = False

    for current_search_tags in search_queries:
        if stop_all:
            break

        page: Optional[str] = None
        query_seen = 0

        if "order:" not in current_search_tags:
            current_search_tags = f"{current_search_tags} order:id_desc"

        print()
        print(f"[INFO] Search: {current_search_tags}")

        while True:
            if max_posts_per_query and query_seen >= max_posts_per_query:
                print(f"[INFO] Per-query limit reached: {max_posts_per_query}")
                break

            if max_total_posts and total_seen >= max_total_posts:
                print(f"[INFO] Global post limit reached: {max_total_posts}")
                stop_all = True
                break

            remaining_query = None
            remaining_total = None

            if max_posts_per_query:
                remaining_query = max_posts_per_query - query_seen

            if max_total_posts:
                remaining_total = max_total_posts - total_seen

            effective_limit = limit

            if remaining_query is not None:
                effective_limit = min(effective_limit, remaining_query)

            if remaining_total is not None:
                effective_limit = min(effective_limit, remaining_total)

            if effective_limit <= 0:
                break

            try:
                posts = fetch_posts(
                    session=session,
                    base_url=base_url,
                    search_tags=current_search_tags,
                    limit=effective_limit,
                    page=page,
                )
            except requests.RequestException as e:
                print(
                    f"[ERROR] API request failed for '{current_search_tags}': {e}",
                    file=sys.stderr,
                )
                total_failed += 1
                break

            if not posts:
                break

            for post in posts:
                if max_posts_per_query and query_seen >= max_posts_per_query:
                    break

                if max_total_posts and total_seen >= max_total_posts:
                    stop_all = True
                    break

                total_seen += 1
                query_seen += 1

                result = process_post(
                    post=post,
                    session=session,
                    config=config,
                    downloaded_ids=downloaded_ids,
                )

                if result == "downloaded":
                    total_downloaded += 1
                elif result == "skipped":
                    total_skipped += 1
                else:
                    total_failed += 1

            if stop_all:
                break

            last_id = posts[-1].get("id")

            if not isinstance(last_id, int):
                break

            page = f"b{last_id}"

    print()
    print("Done.")
    print(f"Posts checked:       {total_seen}")
    print(f"Downloaded:          {total_downloaded}")
    print(f"Skipped:             {total_skipped}")
    print(f"Failed:              {total_failed}")
    print(f"History file:        {history_file}")

    return 0


def main() -> int:
    """
    Command-line entry point.
    """

    parser = argparse.ArgumentParser(
        description="Download Danbooru posts and sort them by tags."
    )

    parser.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Path to the YAML configuration file.",
    )

    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)

    return run_downloader(config)


if __name__ == "__main__":
    raise SystemExit(main())
