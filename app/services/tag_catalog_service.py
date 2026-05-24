from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.core.database import Database
from app.danbooru.api import DanbooruApi


ProgressCallback = Callable[[str, int, int], None]


@dataclass
class TagCatalogSyncResult:
    requested: int = 0
    fetched: int = 0
    stored: int = 0
    min_post_count: int = 0


class TagCatalogService:
    """Synchronize a local Danbooru tag catalog.

    This stores tag metadata separately from ``post_tags``. Local post tags stay
    the truth for your collection; the catalog is the wider Danbooru vocabulary
    used for suggestions, aliases and scoring preparation. Because apparently a
    tag list can become a whole municipal registry if you give it enough time.
    """

    def __init__(self, config: dict[str, Any], db: Database) -> None:
        self.config = config
        self.db = db
        self.api = DanbooruApi(config)

    def import_popular_tags(
        self,
        *,
        limit: int | None = None,
        min_post_count: int | None = None,
        categories: list[str] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> TagCatalogSyncResult:
        catalog_config = self.config.get("tag_catalog", {}) or {}
        wanted_limit = int(limit if limit is not None else catalog_config.get("popular_tag_limit", 10000))
        wanted_min_count = int(min_post_count if min_post_count is not None else catalog_config.get("popular_tag_min_post_count", 50))
        wanted_categories = categories or list(catalog_config.get("popular_tag_categories", []) or [])
        if not wanted_categories:
            wanted_categories = ["general", "artist", "copyright", "character", "meta"]

        tags = self.api.get_popular_tags(
            total_limit=wanted_limit,
            min_post_count=wanted_min_count,
            categories=wanted_categories,
            progress_callback=progress_callback,
        )
        stored = self.db.upsert_danbooru_tags(tags)
        return TagCatalogSyncResult(
            requested=wanted_limit,
            fetched=len(tags),
            stored=stored,
            min_post_count=wanted_min_count,
        )
