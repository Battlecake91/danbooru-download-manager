from __future__ import annotations

import copy
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "base_url": "https://danbooru.donmai.us",
    "search_tags": "order:id_desc",
    "use_saved_searches": False,
    "saved_search_labels": [],
    "saved_search_queries": [],
    "saved_search_extra_tags": "",
    "fetch_exclude_enabled": True,
    "fetch_excluded_posts_count_toward_limits": True,
    "limit": 100,
    "max_posts_per_query": 200,
    "max_total_posts": 500,
    "request_timeout_seconds": 30,
    "user_agent": "DanbooruManager/0.1",
    "ui": {
        "language": "en",
    },
    "work_dir": "./danbooru_manager_data",
    "database_file": "./danbooru_manager_data/danbooru_manager.db",
    "thumbnail_dir": "./danbooru_manager_data/thumbnails/active",
    "active_thumbnail_dir": "./danbooru_manager_data/thumbnails/active",
    "saved_thumbnail_dir": "./danbooru_manager_data/thumbnails/saved",
    "rejected_thumbnail_dir": "./danbooru_manager_data/thumbnails/rejected",
    "original_cache_dir": "./danbooru_manager_data/originals/cache",
    "default_output_dir": "./danbooru_saved",
    "history_file": "./downloaded_ids.txt",
    "thumbnail_size": 256,
    "thumbnail_format": "jpg",
    "thumbnail_download_source": "large",
    "thumbnail_redownload_existing": False,
    "viewer_download_source": "file",
    "username": None,
    "api_key": None,
    "workflow": {
        "worklist_statuses": ["new", "potential"],
        "rejected_thumbnail_retention_days": 7,
    },
    "viewer": {
        "default_view": "worklist",
        "allow_all_status_view": True,
        "open_original_post_in_browser": True,
        "fit_to_window": True,
        "auto_advance_after_save": True,
        "auto_advance_after_reject": True,
        "preview_strip_previous_count": 3,
        "preview_strip_next_count": 3,
        "preview_strip_thumbnail_size": 96,
    },
    "gui": {
        "thumbnail_size": 340,
        "thumbnail_size_min": 120,
        "thumbnail_size_max": 700,
        "thumbnail_size_step": 20,
        "card_width_extra": 100,
        "preview_sample_post_id": 11199825,
        "preview_render_batch_size": 40,
        "preview_limit": 100,
        "status_colors": {
            "new": "#666666",
            "potential": "#2e7d32",
            "rejected": "#b71c1c",
            "already_known": "#6d4c41",
            "saved": "#00838f",
        },
        "status_border_width": {
            "default": 2,
            "marked": 3,
            "saved": 4,
            "rejected": 3,
        },
    },
    "categories": [],
    "filename": {
        "pattern": "%artists%_%characters%_%general%_%postid%",
        "max_length": 180,
        "tags_count": 8,
        "hash_length": 8,
        "excluded_tags": [],
        "sort_tags_by_average_rating": False,
    },
    "scoring": {
        "use_aliases_for_scoring": True,
        "ignore_scoring_excluded_tags": True,
    },
    "tag_catalog": {
        "popular_tag_limit": 10000,
        "popular_tag_min_post_count": 50,
        "popular_tag_categories": ["general", "artist", "copyright", "character", "meta"],
    },
    "first_run": {
        "sample_post_id": 11199825,
        "fetch_sample_post": True,
        "import_popular_tags": True,
    },
    "llm": {
        "enabled": False,
        "backend": "none",
        "endpoint_url": "",
        "model": "",
        "api_key": "",
        "request_timeout_seconds": 60,
        "run_after_fetch": False,
        "after_fetch_statuses": ["new", "potential"],
        "skip_already_scored": True,
        "max_posts_per_request": 20,
        "max_tags_per_post": 80,
        "include_preference_context": True,
        "max_preference_tags": 80,
        "max_positive_examples": 8,
        "max_negative_examples": 8,
        "max_category_examples": 3,
        "max_example_tags": 30,
        "system_prompt": "",
        "tag_aliases": {},
        "tag_export_mode": "hashed_alias",
        "hash_prefix": "tag_",
        "hash_length": 12,
        "category_export_mode": "hashed",
        "category_hash_prefix": "cat_",
        "category_hash_length": 12,
        "include_category_legend": False,
        "include_tag_legend": False,
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Path | None = None, env_path: Path | None = None) -> dict[str, Any]:
    """Return the internal default runtime config.

    The GUI configuration lives in SQLite/app_settings. External YAML and .env
    files are intentionally ignored now. The optional parameters stay in the
    signature for older call sites and scripts, but they do nothing. Yes, even
    configuration files eventually have to move out of their parents' basement.
    """
    _ = config_path, env_path
    config = copy.deepcopy(DEFAULT_CONFIG)

    if not config.get("active_thumbnail_dir"):
        config["active_thumbnail_dir"] = config.get("thumbnail_dir")

    config["thumbnail_dir"] = config.get("active_thumbnail_dir", config["thumbnail_dir"])

    validate_config(config)
    return config


def flatten_config(config: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in config.items():
        dotted = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            result.update(flatten_config(value, dotted))
        else:
            result[dotted] = value
    return result


def validate_config(config: dict[str, Any]) -> None:
    required = [
        "base_url",
        "work_dir",
        "database_file",
        "thumbnail_dir",
        "active_thumbnail_dir",
        "saved_thumbnail_dir",
        "rejected_thumbnail_dir",
        "original_cache_dir",
        "default_output_dir",
    ]

    missing = [key for key in required if not config.get(key)]
    if missing:
        raise ValueError(f"Required config values are missing: {', '.join(missing)}")

    limit = int(config.get("limit", 100))
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if limit > 200:
        config["limit"] = 200

    if int(config.get("max_posts_per_query", 1)) < 1:
        raise ValueError("max_posts_per_query must be >= 1")

    if int(config.get("max_total_posts", 1)) < 1:
        raise ValueError("max_total_posts must be >= 1")

    source = str(config.get("thumbnail_download_source", "large")).lower()
    if source not in {"preview", "large", "file", "best"}:
        raise ValueError("thumbnail_download_source must be preview, large, file, or best")
    config["thumbnail_download_source"] = source

    viewer_source = str(config.get("viewer_download_source", "file")).lower()
    if viewer_source not in {"large", "file", "best"}:
        raise ValueError("viewer_download_source must be large, file, or best")
    config["viewer_download_source"] = viewer_source

    workflow = config.get("workflow", {}) or {}
    worklist_statuses = workflow.get("worklist_statuses", [])
    if not isinstance(worklist_statuses, list) or not worklist_statuses:
        raise ValueError("workflow.worklist_statuses must be a non-empty list")

    gui = config.get("gui", {}) or {}
    thumb_min = int(gui.get("thumbnail_size_min", 120))
    thumb_max = int(gui.get("thumbnail_size_max", 600))
    thumb_size = int(gui.get("thumbnail_size", 280))

    if thumb_min < 32:
        raise ValueError("gui.thumbnail_size_min must be >= 32")
    if thumb_max < thumb_min:
        raise ValueError("gui.thumbnail_size_max must be >= gui.thumbnail_size_min")
    if thumb_size < thumb_min or thumb_size > thumb_max:
        raise ValueError("gui.thumbnail_size must be between thumbnail_size_min and thumbnail_size_max")

    filename = config.get("filename", {}) or {}
    if int(filename.get("max_length", 180)) < 32:
        raise ValueError("filename.max_length must be >= 32")
    if int(filename.get("tags_count", 8)) < 0:
        raise ValueError("filename.tags_count must be >= 0")
    if int(filename.get("hash_length", 8)) < 1:
        raise ValueError("filename.hash_length must be >= 1")

    llm = config.get("llm", {}) or {}
    backend = str(llm.get("backend", "none")).lower()
    if backend not in {"none", "openai_compatible", "local"}:
        raise ValueError("llm.backend must be none, openai_compatible, or local")
    llm["backend"] = backend

    tag_export_mode = str(llm.get("tag_export_mode", "hashed_alias")).lower()
    if tag_export_mode not in {"original", "alias", "hashed_alias"}:
        raise ValueError("llm.tag_export_mode must be original, alias, or hashed_alias")
    llm["tag_export_mode"] = tag_export_mode

    if int(llm.get("hash_length", 12)) < 4:
        raise ValueError("llm.hash_length must be >= 4")

    category_export_mode = str(llm.get("category_export_mode", "hashed")).lower()
    if category_export_mode not in {"original", "hashed"}:
        raise ValueError("llm.category_export_mode must be original or hashed")
    llm["category_export_mode"] = category_export_mode

    if int(llm.get("category_hash_length", llm.get("hash_length", 12))) < 4:
        raise ValueError("llm.category_hash_length must be >= 4")
    if int(llm.get("request_timeout_seconds", 60)) < 1:
        raise ValueError("llm.request_timeout_seconds must be >= 1")
    after_fetch_statuses = llm.get("after_fetch_statuses", ["new", "potential"])
    if not isinstance(after_fetch_statuses, list):
        llm["after_fetch_statuses"] = ["new", "potential"]
    if int(llm.get("max_posts_per_request", 20)) < 1:
        raise ValueError("llm.max_posts_per_request must be >= 1")
    if int(llm.get("max_tags_per_post", 80)) < 1:
        raise ValueError("llm.max_tags_per_post must be >= 1")
    if int(llm.get("max_preference_tags", 80)) < 0:
        raise ValueError("llm.max_preference_tags must be >= 0")
    if int(llm.get("max_positive_examples", 8)) < 0:
        raise ValueError("llm.max_positive_examples must be >= 0")
    if int(llm.get("max_negative_examples", 8)) < 0:
        raise ValueError("llm.max_negative_examples must be >= 0")
    if int(llm.get("max_category_examples", 3)) < 0:
        raise ValueError("llm.max_category_examples must be >= 0")
    if int(llm.get("max_example_tags", 30)) < 1:
        raise ValueError("llm.max_example_tags must be >= 1")
