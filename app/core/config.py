from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
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
    "thumbnail_dir": "./danbooru_manager_data/thumbnails",
    "original_cache_dir": "./danbooru_manager_data/originals",
    "history_file": "./downloaded_ids.txt",
    "thumbnail_size": 256,
    "thumbnail_format": "jpg",
    "username": None,
    "api_key": None,
    "categories": [],
    "filename": {
        "max_length": 180,
        "tags_count": 8,
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


def load_config(config_path: Path, env_path: Path | None = None) -> dict[str, Any]:
    if env_path and env_path.exists():
        load_dotenv(env_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config nicht gefunden: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}

    config = deep_merge(DEFAULT_CONFIG, loaded)

    env_username = os.getenv("DANBOORU_USERNAME")
    env_api_key = os.getenv("DANBOORU_API_KEY")

    if env_username:
        config["username"] = env_username
    if env_api_key:
        config["api_key"] = env_api_key

    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    required = [
        "base_url",
        "work_dir",
        "database_file",
        "thumbnail_dir",
        "original_cache_dir",
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
