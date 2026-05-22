from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except Exception:  # PyYAML ist nur noch optional fuer Alt-Imports.
    yaml = None

from dotenv import load_dotenv


DEFAULT_CONFIG: dict[str, Any] = {
    "base_url": "https://danbooru.donmai.us",
    "search_tags": "order:id_desc",
    "use_saved_searches": False,
    "saved_search_labels": [],
    "saved_search_queries": [],
    "saved_search_extra_tags": "",
    "limit": 100,
    "max_posts_per_query": 200,
    "max_total_posts": 500,
    "request_timeout_seconds": 30,
    "user_agent": "DanbooruManager/0.1",
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
    },
    "gui": {
        "thumbnail_size": 340,
        "thumbnail_size_min": 120,
        "thumbnail_size_max": 700,
        "thumbnail_size_step": 20,
        "card_width_extra": 100,
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
    },
    "llm": {
        "enabled": False,
        "backend": "none",
        "tag_aliases": {},
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
    """Load runtime config.

    SQLite/app_settings is the leading configuration inside the GUI. YAML is no
    longer required; an existing YAML file is only used as an optional legacy
    import/default overlay at startup. Yes, finally, one less file pretending to
    be a database.
    """
    if env_path and env_path.exists():
        load_dotenv(env_path)

    loaded: dict[str, Any] = {}
    if config_path is not None and config_path.exists():
        if yaml is None:
            raise RuntimeError(
                f"YAML-Konfiguration gefunden ({config_path}), aber PyYAML ist nicht installiert. "
                "Installiere PyYAML oder entferne/ignoriere die YAML-Datei."
            )
        with config_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}

    config = deep_merge(copy.deepcopy(DEFAULT_CONFIG), loaded)

    env_username = os.getenv("DANBOORU_USERNAME")
    env_api_key = os.getenv("DANBOORU_API_KEY")

    if env_username:
        config["username"] = env_username
    if env_api_key:
        config["api_key"] = env_api_key

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
        raise ValueError(f"Pflichtwerte fehlen in Config: {', '.join(missing)}")

    limit = int(config.get("limit", 100))
    if limit < 1:
        raise ValueError("limit muss >= 1 sein")
    if limit > 200:
        config["limit"] = 200

    if int(config.get("max_posts_per_query", 1)) < 1:
        raise ValueError("max_posts_per_query muss >= 1 sein")

    if int(config.get("max_total_posts", 1)) < 1:
        raise ValueError("max_total_posts muss >= 1 sein")

    source = str(config.get("thumbnail_download_source", "large")).lower()
    if source not in {"preview", "large", "file", "best"}:
        raise ValueError("thumbnail_download_source muss preview, large, file oder best sein")
    config["thumbnail_download_source"] = source

    viewer_source = str(config.get("viewer_download_source", "file")).lower()
    if viewer_source not in {"large", "file", "best"}:
        raise ValueError("viewer_download_source muss large, file oder best sein")
    config["viewer_download_source"] = viewer_source

    workflow = config.get("workflow", {}) or {}
    worklist_statuses = workflow.get("worklist_statuses", [])
    if not isinstance(worklist_statuses, list) or not worklist_statuses:
        raise ValueError("workflow.worklist_statuses muss eine nicht-leere Liste sein")

    gui = config.get("gui", {}) or {}
    thumb_min = int(gui.get("thumbnail_size_min", 120))
    thumb_max = int(gui.get("thumbnail_size_max", 600))
    thumb_size = int(gui.get("thumbnail_size", 280))

    if thumb_min < 32:
        raise ValueError("gui.thumbnail_size_min muss >= 32 sein")
    if thumb_max < thumb_min:
        raise ValueError("gui.thumbnail_size_max muss >= gui.thumbnail_size_min sein")
    if thumb_size < thumb_min or thumb_size > thumb_max:
        raise ValueError("gui.thumbnail_size muss zwischen thumbnail_size_min und thumbnail_size_max liegen")

    filename = config.get("filename", {}) or {}
    if int(filename.get("max_length", 180)) < 32:
        raise ValueError("filename.max_length muss >= 32 sein")
    if int(filename.get("tags_count", 8)) < 0:
        raise ValueError("filename.tags_count muss >= 0 sein")
    if int(filename.get("hash_length", 8)) < 1:
        raise ValueError("filename.hash_length muss >= 1 sein")
