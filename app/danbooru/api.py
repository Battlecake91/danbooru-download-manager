from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DanbooruSearchPage:
    posts: list[dict[str, Any]]
    next_page: str | None


class DanbooruApi:
    def __init__(self, config: dict[str, Any]) -> None:
        self.base_url = str(config["base_url"]).rstrip("/") + "/"
        self.timeout = int(config.get("request_timeout_seconds", 30))

        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": str(config.get("user_agent", "DanbooruManager/0.1"))}
        )

        username = config.get("username")
        api_key = config.get("api_key")
        if username and api_key:
            self.session.auth = (username, api_key)

    def get_posts(self, tags: str, limit: int, page: str | None = None) -> DanbooruSearchPage:
        url = urljoin(self.base_url, "posts.json")
        params: dict[str, Any] = {
            "tags": ensure_stable_order(tags),
            "limit": min(int(limit), 200),
        }
        if page:
            params["page"] = page

        LOGGER.debug("Danbooru GET %s params=%s", url, params)
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()

        posts = response.json()
        if not isinstance(posts, list):
            raise RuntimeError(f"Unerwartete Danbooru-Antwort: {posts!r}")

        next_page = None
        if posts:
            last_id = posts[-1].get("id")
            if last_id:
                next_page = f"b{last_id}"

        return DanbooruSearchPage(posts=posts, next_page=next_page)

    def get_post(self, post_id: int) -> dict[str, Any]:
        url = urljoin(self.base_url, f"posts/{int(post_id)}.json")
        LOGGER.debug("Danbooru GET %s", url)
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()

        post = response.json()
        if not isinstance(post, dict):
            raise RuntimeError(f"Unerwartete Danbooru-Post-Antwort: {post!r}")
        return post

    def get_saved_searches(self) -> list[dict[str, Any]]:
        url = urljoin(self.base_url, "saved_searches.json")
        LOGGER.debug("Danbooru GET %s", url)
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError(f"Unerwartete Saved-Search-Antwort: {data!r}")
        return data


def ensure_stable_order(tags: str) -> str:
    tags = (tags or "").strip()
    if "order:" in tags:
        return tags
    if tags:
        return f"{tags} order:id_desc"
    return "order:id_desc"


def build_search_queries(config: dict[str, Any], api: DanbooruApi) -> list[str]:
    if not config.get("use_saved_searches"):
        return [str(config.get("search_tags", "")).strip()]

    saved_searches = api.get_saved_searches()
    wanted_labels = set(config.get("saved_search_labels", []) or [])
    wanted_queries = set(config.get("saved_search_queries", []) or [])
    extra_tags = str(config.get("saved_search_extra_tags", "") or "").strip()

    queries: list[str] = []

    for saved in saved_searches:
        query = str(saved.get("query", "")).strip()
        raw_labels = saved.get("labels", []) or saved.get("label_list", []) or []
        if isinstance(raw_labels, str):
            labels = {part.strip() for part in raw_labels.replace(",", " ").split() if part.strip()}
        else:
            labels = {str(label).strip() for label in raw_labels if str(label).strip()}

        if wanted_labels and not labels.intersection(wanted_labels):
            continue

        if wanted_queries and query not in wanted_queries:
            continue

        full_query = query
        if extra_tags:
            full_query = f"{full_query} {extra_tags}".strip()

        if full_query and full_query not in queries:
            queries.append(full_query)

    return queries
