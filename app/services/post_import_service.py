from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.core.database import Database
from app.danbooru.api import DanbooruApi, build_search_queries
from app.danbooru.thumbnail_cache import ThumbnailCache

LOGGER = logging.getLogger(__name__)


@dataclass
class FetchResult:
    queries: int = 0
    seen_posts: int = 0
    inserted_posts: int = 0
    updated_posts: int = 0
    cached_thumbnails: int = 0


class PostImportService:
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        self.config = config
        self.db = db
        self.api = DanbooruApi(config)
        self.thumbnail_cache = ThumbnailCache(config, self.api.session)

    def fetch_and_store(self) -> FetchResult:
        self.db.sync_static_config(self.config)

        queries = build_search_queries(self.config, self.api)
        if not queries:
            raise RuntimeError("Keine Suchqueries vorhanden")

        result = FetchResult(queries=len(queries))

        max_total_posts = int(self.config.get("max_total_posts", 500))
        max_posts_per_query = int(self.config.get("max_posts_per_query", 200))
        limit = int(self.config.get("limit", 100))

        total_seen = 0

        for query in queries:
            if total_seen >= max_total_posts:
                break

            LOGGER.info("Lade Query: %s", query)
            page = None
            seen_for_query = 0

            while seen_for_query < max_posts_per_query and total_seen < max_total_posts:
                page_data = self.api.get_posts(query, limit=limit, page=page)
                if not page_data.posts:
                    break

                for post in page_data.posts:
                    if seen_for_query >= max_posts_per_query or total_seen >= max_total_posts:
                        break

                    post_result = self.store_post(post)
                    result.seen_posts += 1
                    total_seen += 1
                    seen_for_query += 1

                    if post_result == "inserted":
                        result.inserted_posts += 1
                    else:
                        result.updated_posts += 1

                    # Für entschiedene Posts keine aktiven Thumbnails neu laden.
                    status = self.get_status(int(post["id"]))
                    if status in {"new", "potential", "review", "selected_save"}:
                        thumbnail_path = self.thumbnail_cache.cache_thumbnail(post)
                        if thumbnail_path:
                            self.set_thumbnail_path(int(post["id"]), thumbnail_path)
                            result.cached_thumbnails += 1

                if not page_data.next_page:
                    break

                page = page_data.next_page

        return result

    def get_status(self, post_id: int) -> str:
        row = self.db.execute("SELECT status FROM posts WHERE id = ?", (post_id,)).fetchone()
        if row is None:
            return "new"
        return str(row["status"] or "new")

    def store_post(self, post: dict[str, Any]) -> str:
        post_id = int(post["id"])

        existing = self.db.execute(
            "SELECT id, status FROM posts WHERE id = ?",
            (post_id,),
        ).fetchone()

        result = "updated" if existing else "inserted"

        self.db.execute(
            """
            INSERT INTO posts (
                id,
                source,
                rating,
                score,
                fav_count,
                file_ext,
                file_url,
                large_file_url,
                preview_url,
                image_width,
                image_height,
                file_size,
                parent_id,
                has_children,
                status,
                created_at,
                last_seen_at
            )
            VALUES (?, 'danbooru', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                rating = excluded.rating,
                score = excluded.score,
                fav_count = excluded.fav_count,
                file_ext = excluded.file_ext,
                file_url = excluded.file_url,
                large_file_url = excluded.large_file_url,
                preview_url = excluded.preview_url,
                image_width = COALESCE(excluded.image_width, posts.image_width),
                image_height = COALESCE(excluded.image_height, posts.image_height),
                file_size = COALESCE(excluded.file_size, posts.file_size),
                parent_id = excluded.parent_id,
                has_children = excluded.has_children,
                created_at = COALESCE(posts.created_at, excluded.created_at),
                last_seen_at = CURRENT_TIMESTAMP
            """,
            (
                post_id,
                post.get("rating"),
                post.get("score"),
                post.get("fav_count"),
                post.get("file_ext"),
                post.get("file_url"),
                post.get("large_file_url"),
                post.get("preview_file_url"),
                post.get("image_width"),
                post.get("image_height"),
                post.get("file_size"),
                post.get("parent_id"),
                1 if post.get("has_children") else 0,
                post.get("created_at"),
            ),
        )

        self.replace_tags(post_id, post)
        self.db.commit()
        return result

    def replace_tags(self, post_id: int, post: dict[str, Any]) -> None:
        self.db.execute("DELETE FROM post_tags WHERE post_id = ?", (post_id,))

        tag_rows: list[tuple[int, str, str]] = []

        tag_fields = {
            "general": "tag_string_general",
            "character": "tag_string_character",
            "copyright": "tag_string_copyright",
            "artist": "tag_string_artist",
            "meta": "tag_string_meta",
        }

        for tag_type, field_name in tag_fields.items():
            tag_string = post.get(field_name) or ""
            for tag in split_tags(tag_string):
                tag_rows.append((post_id, tag, tag_type))

        if tag_rows:
            self.db.executemany(
                """
                INSERT OR IGNORE INTO post_tags (post_id, tag, tag_type)
                VALUES (?, ?, ?)
                """,
                tag_rows,
            )

            for _, tag, _ in tag_rows:
                self.db.execute(
                    """
                    INSERT INTO tag_scores (tag)
                    VALUES (?)
                    ON CONFLICT(tag) DO NOTHING
                    """,
                    (tag,),
                )

    def set_thumbnail_path(self, post_id: int, thumbnail_path: str) -> None:
        self.db.execute(
            "UPDATE posts SET thumbnail_path = ? WHERE id = ?",
            (thumbnail_path, post_id),
        )
        self.db.commit()


def split_tags(tag_string: str) -> list[str]:
    return [tag.strip() for tag in tag_string.split(" ") if tag.strip()]
