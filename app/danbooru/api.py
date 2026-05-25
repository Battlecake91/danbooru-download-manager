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


TAG_CATEGORY_NAMES = {
    0: "general",
    1: "artist",
    3: "copyright",
    4: "character",
    5: "meta",
}
TAG_CATEGORY_VALUES = {value: key for key, value in TAG_CATEGORY_NAMES.items()}


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
            raise RuntimeError(f"Unexpected Danbooru response: {posts!r}")

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
            raise RuntimeError(f"Unexpected Danbooru post response: {post!r}")
        return post

    def get_post_by_md5(self, md5_hash: str) -> dict[str, Any] | None:
        clean_hash = str(md5_hash or "").strip().lower()
        if len(clean_hash) != 32 or any(char not in "0123456789abcdef" for char in clean_hash):
            raise ValueError(f"Invalid MD5 hash: {md5_hash!r}")

        page = self.get_posts(f"md5:{clean_hash}", limit=1)
        if not page.posts:
            return None
        post = page.posts[0]
        if not isinstance(post, dict):
            raise RuntimeError(f"Unexpected Danbooru post response: {post!r}")
        return post


    def get_tags_page(
        self,
        *,
        limit: int = 200,
        page: int = 1,
        order: str = "count",
        name_matches: str | None = None,
        category: str | int | None = None,
        min_post_count: int | None = None,
    ) -> list[dict[str, Any]]:
        url = urljoin(self.base_url, "tags.json")
        params: dict[str, Any] = {
            "limit": min(max(int(limit), 1), 200),
            "page": max(int(page), 1),
            "search[order]": order,
        }
        if name_matches:
            params["search[name_matches]"] = str(name_matches)
        if category not in {None, "", "all"}:
            category_value = category
            if isinstance(category, str) and not category.isdigit():
                category_value = TAG_CATEGORY_VALUES.get(category.strip().lower())
            if category_value is not None:
                params["search[category]"] = int(category_value)
        if min_post_count is not None and int(min_post_count) > 0:
            params["search[post_count_gte]"] = int(min_post_count)

        LOGGER.debug("Danbooru GET %s params=%s", url, params)
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected Danbooru tags response: {data!r}")
        return [item for item in data if isinstance(item, dict)]

    def get_popular_tags(
        self,
        *,
        total_limit: int,
        min_post_count: int = 0,
        categories: list[str] | None = None,
        progress_callback: Any | None = None,
    ) -> list[dict[str, Any]]:
        wanted_total = max(0, int(total_limit or 0))
        if wanted_total <= 0:
            return []

        category_list = categories or ["general", "artist", "copyright", "character", "meta"]
        per_category_target = max(1, (wanted_total + len(category_list) - 1) // len(category_list))
        collected: dict[str, dict[str, Any]] = {}

        for category in category_list:
            page = 1
            category_count = 0
            while category_count < per_category_target and len(collected) < wanted_total:
                batch = self.get_tags_page(
                    limit=200,
                    page=page,
                    order="count",
                    category=category,
                    min_post_count=min_post_count,
                )
                if not batch:
                    break
                for tag in batch:
                    name = str(tag.get("name") or "").strip()
                    if not name:
                        continue
                    collected[name] = tag
                    category_count += 1
                    if category_count >= per_category_target or len(collected) >= wanted_total:
                        break
                if progress_callback is not None:
                    progress_callback(category, len(collected), wanted_total)
                page += 1

        return sorted(
            collected.values(),
            key=lambda item: int(item.get("post_count") or 0),
            reverse=True,
        )[:wanted_total]

    def get_saved_searches(self) -> list[dict[str, Any]]:
        url = urljoin(self.base_url, "saved_searches.json")
        LOGGER.debug("Danbooru GET %s", url)
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected saved search response: {data!r}")
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
