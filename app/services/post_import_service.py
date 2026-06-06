from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.core.database import Database
from app.danbooru.api import DanbooruApi, build_search_queries
from app.danbooru.thumbnail_cache import ThumbnailCache

LOGGER = logging.getLogger(__name__)


@dataclass
class FetchResult:
    queries: int = 0
    processed_queries: int = 0
    seen_posts: int = 0
    inserted_posts: int = 0
    updated_posts: int = 0
    fetch_excluded_posts: int = 0
    resolution_excluded_posts: int = 0
    cached_thumbnails: int = 0
    target_unknown_per_query: int = 0
    target_unknown_total: int = 0
    fetched_post_ids: list[int] = field(default_factory=list)
    inserted_post_ids: list[int] = field(default_factory=list)


@dataclass
class FetchProgress:
    query_index: int = 0
    query_total: int = 0
    query: str = ""
    seen_total: int = 0
    planned_total: int = 0
    seen_for_query: int = 0
    planned_for_query: int = 0
    inserted_for_query: int = 0
    target_unknown_for_query: int = 0
    inserted_posts: int = 0
    known_posts: int = 0
    cached_thumbnails: int = 0
    phase: str = "running"


class PostImportService:
    def __init__(
        self,
        config: dict[str, Any],
        db: Database,
        progress_callback: Callable[[FetchProgress], None] | None = None,
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config
        self.db = db
        self.api = DanbooruApi(config)
        self.thumbnail_cache = ThumbnailCache(config, self.api.session)
        self.progress_callback = progress_callback
        self.log_callback = log_callback

    def emit_log(self, message: str) -> None:
        if self.log_callback is not None:
            self.log_callback(message)

    def emit_progress(self, progress: FetchProgress) -> None:
        if self.progress_callback is not None:
            self.progress_callback(progress)

    def fetch_and_store(self) -> FetchResult:
        fetch_started = time.monotonic()
        queries = build_search_queries(self.config, self.api)
        if not queries:
            raise RuntimeError("No search queries available")

        min_unknown_per_query = max(0, int(self.config.get("min_unknown_posts_per_query", 0) or 0))
        result = FetchResult(
            queries=len(queries),
            target_unknown_per_query=min_unknown_per_query,
            target_unknown_total=len(queries) * min_unknown_per_query,
        )

        max_total_posts = int(self.config.get("max_total_posts", 500))
        max_posts_per_query = int(self.config.get("max_posts_per_query", 200))
        limit = int(self.config.get("limit", 100))

        if min_unknown_per_query > 0:
            planned_total = max(1, min(max_total_posts, len(queries) * min_unknown_per_query))
            planned_for_query = min_unknown_per_query
        else:
            planned_total = max(1, min(max_total_posts, len(queries) * max_posts_per_query))
            planned_for_query = max_posts_per_query

        total_seen = 0
        fetch_excluded_tags = self.db.fetch_excluded_tag_set()
        trace_path = Path(self.db.path).expanduser().resolve().parent / "logs" / "database_trace.log"
        self.emit_log(f"[TRACE] Detailed database trace: {trace_path}")
        self.emit_log(
            f"[TRACE] Fetch plan: queries={len(queries)}, page_limit={limit}, "
            f"max_per_query={max_posts_per_query}, max_total={max_total_posts}"
        )

        self.emit_progress(
            FetchProgress(
                query_total=len(queries),
                planned_total=planned_total,
                planned_for_query=planned_for_query,
                target_unknown_for_query=min_unknown_per_query,
                phase="start",
            )
        )

        for query_index, query in enumerate(queries, start=1):
            if total_seen >= max_total_posts:
                break

            result.processed_queries += 1

            LOGGER.info("Loading query %s/%s: %s", query_index, len(queries), query)
            page = None
            seen_for_query = 0
            inserted_for_query = 0
            self.emit_progress(
                FetchProgress(
                    query_index=query_index,
                    query_total=len(queries),
                    query=query,
                    seen_total=total_seen,
                    planned_total=planned_total,
                    seen_for_query=seen_for_query,
                    planned_for_query=planned_for_query,
                    inserted_for_query=inserted_for_query,
                    target_unknown_for_query=min_unknown_per_query,
                    inserted_posts=result.inserted_posts,
                    known_posts=result.updated_posts,
                    cached_thumbnails=result.cached_thumbnails,
                    phase="query",
                )
            )

            while total_seen < max_total_posts:
                if min_unknown_per_query > 0:
                    if inserted_for_query >= min_unknown_per_query:
                        break
                elif seen_for_query >= max_posts_per_query:
                    break

                page_started = time.monotonic()
                self.emit_log(
                    f"[TRACE] API request: query={query_index}/{len(queries)} page={page or 'first'} "
                    f"seen={total_seen} queue={self.db.write_queue_snapshot()}"
                )
                page_data = self.api.get_posts(query, limit=limit, page=page)
                self.emit_log(
                    f"[TRACE] API response: posts={len(page_data.posts)} next={page_data.next_page or '-'} "
                    f"duration={time.monotonic() - page_started:.3f}s"
                )
                if not page_data.posts:
                    break

                for post in page_data.posts:
                    if total_seen >= max_total_posts:
                        break
                    if min_unknown_per_query > 0:
                        if inserted_for_query >= min_unknown_per_query:
                            break
                    elif seen_for_query >= max_posts_per_query:
                        break

                    post_id = int(post["id"])
                    result.seen_posts += 1
                    total_seen += 1
                    seen_for_query += 1

                    if fetch_excluded_tags and self.post_matches_fetch_exclude(post, fetch_excluded_tags):
                        result.fetch_excluded_posts += 1
                        continue

                    if not self.post_matches_resolution_filter(post):
                        result.resolution_excluded_posts += 1
                        continue

                    if total_seen == 1 or total_seen % 25 == 0:
                        self.emit_log(
                            f"[TRACE] Before store: post={post_id} seen={total_seen} "
                            f"queue={self.db.write_queue_snapshot()}"
                        )
                    store_started = time.monotonic()
                    post_result = self.store_post(post)
                    store_duration = time.monotonic() - store_started
                    if store_duration >= 0.250 or total_seen == 1 or total_seen % 25 == 0:
                        self.emit_log(
                            f"[TRACE] Stored: post={post_id} result={post_result} "
                            f"duration={store_duration:.3f}s queue={self.db.write_queue_snapshot()}"
                        )
                    result.fetched_post_ids.append(post_id)

                    if post_result == "inserted":
                        result.inserted_posts += 1
                        result.inserted_post_ids.append(post_id)
                        inserted_for_query += 1
                    else:
                        result.updated_posts += 1

                    # Do not reload active thumbnails for posts that already have a decision.
                    status = self.get_status(post_id)
                    if status in {"new", "potential", "review", "selected_save"}:
                        thumbnail_started = time.monotonic()
                        thumbnail_path = self.thumbnail_cache.cache_thumbnail(post)
                        thumbnail_duration = time.monotonic() - thumbnail_started
                        if thumbnail_duration >= 2.0:
                            self.emit_log(
                                f"[TRACE] Slow thumbnail: post={post_id} duration={thumbnail_duration:.3f}s"
                            )
                        if thumbnail_path:
                            self.set_thumbnail_path(post_id, thumbnail_path)
                            result.cached_thumbnails += 1

                    self.emit_progress(
                        FetchProgress(
                            query_index=query_index,
                            query_total=len(queries),
                            query=query,
                            seen_total=total_seen,
                            planned_total=planned_total,
                            seen_for_query=seen_for_query,
                            planned_for_query=planned_for_query,
                            inserted_for_query=inserted_for_query,
                            target_unknown_for_query=min_unknown_per_query,
                            inserted_posts=result.inserted_posts,
                            known_posts=result.updated_posts,
                            cached_thumbnails=result.cached_thumbnails,
                            phase="post",
                        )
                    )

                if not page_data.next_page:
                    break

                page = page_data.next_page

        self.emit_progress(
            FetchProgress(
                query_index=result.processed_queries,
                query_total=len(queries),
                seen_total=total_seen,
                planned_total=planned_total,
                planned_for_query=planned_for_query,
                target_unknown_for_query=min_unknown_per_query,
                inserted_posts=result.inserted_posts,
                known_posts=result.updated_posts,
                cached_thumbnails=result.cached_thumbnails,
                phase="done",
            )
        )
        self.emit_log(f"[TRACE] Fetch storage phase completed in {time.monotonic() - fetch_started:.3f}s")
        return result

    @staticmethod
    def post_matches_fetch_exclude(post: dict[str, Any], excluded_tags: set[str]) -> bool:
        if not excluded_tags:
            return False
        fields = (
            "tag_string",
            "tag_string_general",
            "tag_string_character",
            "tag_string_copyright",
            "tag_string_artist",
            "tag_string_meta",
        )
        post_tags: set[str] = set()
        for field_name in fields:
            post_tags.update(split_tags(str(post.get(field_name) or "")))
        return not post_tags.isdisjoint(excluded_tags)

    def post_matches_resolution_filter(self, post: dict[str, Any]) -> bool:
        filters = self.config.get("resolution_filters", {}) or {}
        if not isinstance(filters, dict):
            return True

        min_width = max(0, int(filters.get("min_width", 0) or 0))
        max_width = max(0, int(filters.get("max_width", 0) or 0))
        min_height = max(0, int(filters.get("min_height", 0) or 0))
        max_height = max(0, int(filters.get("max_height", 0) or 0))
        if not any((min_width, max_width, min_height, max_height)):
            return True

        width = int(post.get("image_width") or 0)
        height = int(post.get("image_height") or 0)

        # Active limits require Danbooru to provide the corresponding dimension.
        # Unknown is not secretly 4K, despite databases occasionally acting optimistic.
        if (min_width or max_width) and width <= 0:
            return False
        if (min_height or max_height) and height <= 0:
            return False
        if min_width and width < min_width:
            return False
        if max_width and width > max_width:
            return False
        if min_height and height < min_height:
            return False
        if max_height and height > max_height:
            return False
        return True

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
