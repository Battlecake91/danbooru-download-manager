from __future__ import annotations

import json
import secrets
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from app.core.db.common import (
    ACTIVE_STATUSES,
    ALL_ALLOWED_STATUSES,
    calculate_computed_tag_score,
    clamp_number,
    is_path_like_preview_search_term,
    parse_preview_search_terms,
)
from app.core.tag_privacy import build_tag_identity, canonicalize_tag, normalize_tag_token, salted_tag_hash


class DatabasePostMixin:
    """Post browsing, status updates, file paths, and category assignment."""

    def fetch_preview_posts(
        self,
        view_mode: str = "worklist",
        status_filter: str | None = None,
        text_filter: str | None = None,
        worklist_statuses: list[str] | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        where_sql, parameters = self._build_preview_where(
            view_mode=view_mode,
            status_filter=status_filter,
            text_filter=text_filter,
            worklist_statuses=worklist_statuses,
        )

        parameters.extend([limit, offset])

        return list(
            self.execute(
                f"""
                SELECT
                    p.id,
                    p.rating,
                    p.score,
                    p.fav_count,
                    p.thumbnail_path,
                    p.rejected_thumbnail_path,
                    p.parent_id,
                    p.has_children,
                    p.status,
                    p.local_score,
                    p.llm_score,
                    p.llm_decision,
                    p.llm_category,
                    p.llm_reason,
                    p.llm_model,
                    p.llm_reviewed_at,
                    p.final_score,
                    p.final_file_path,
                    p.final_directory,
                    p.rejected_at,
                    p.saved_at,
                    p.already_known_at,

                    CASE
                        WHEN p.parent_id IS NOT NULL
                         AND EXISTS (
                             SELECT 1
                             FROM posts parent
                             WHERE parent.id = p.parent_id
                               AND parent.final_file_path IS NOT NULL
                               AND parent.final_file_path != ''
                         )
                        THEN 1
                        ELSE 0
                    END AS known_parent_loaded,

                    (
                        SELECT COUNT(*)
                        FROM posts child
                        WHERE child.parent_id = p.id
                          AND child.final_file_path IS NOT NULL
                          AND child.final_file_path != ''
                    ) AS known_child_count,

                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id
                        ORDER BY
                            CASE pt.tag_type
                                WHEN 'copyright' THEN 1
                                WHEN 'character' THEN 2
                                WHEN 'artist' THEN 3
                                WHEN 'general' THEN 4
                                WHEN 'meta' THEN 5
                                ELSE 9
                            END,
                            pt.tag
                    ) AS tags,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'general'
                        ORDER BY pt.tag
                    ) AS tags_general,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'character'
                        ORDER BY pt.tag
                    ) AS tags_character,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'copyright'
                        ORDER BY pt.tag
                    ) AS tags_copyright,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'artist'
                        ORDER BY pt.tag
                    ) AS tags_artist,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'meta'
                        ORDER BY pt.tag
                    ) AS tags_meta
                FROM posts p
                {where_sql}
                ORDER BY p.id DESC
                LIMIT ?
                OFFSET ?
                """,
                parameters,
            ).fetchall()
        )

    def count_preview_posts(
        self,
        view_mode: str = "worklist",
        status_filter: str | None = None,
        text_filter: str | None = None,
        worklist_statuses: list[str] | None = None,
    ) -> int:
        where_sql, parameters = self._build_preview_where(
            view_mode=view_mode,
            status_filter=status_filter,
            text_filter=text_filter,
            worklist_statuses=worklist_statuses,
        )

        row = self.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM posts p
            {where_sql}
            """,
            parameters,
        ).fetchone()

        return int(row["count"]) if row else 0

    def _build_preview_where(
        self,
        view_mode: str,
        status_filter: str | None,
        text_filter: str | None,
        worklist_statuses: list[str] | None,
    ) -> tuple[str, list[Any]]:
        where_parts: list[str] = []
        parameters: list[Any] = []

        has_specific_status_filter = bool(status_filter and status_filter != "all")

        # When text/tag search is active, search across all statuses on purpose
        # so already locally saved images remain findable by tags. Otherwise the
        # worklist hides exactly the files being searched. Classic.
        if not text_filter:
            if view_mode == "worklist" and not has_specific_status_filter:
                statuses = worklist_statuses or sorted(ACTIVE_STATUSES)
                placeholders = ", ".join("?" for _ in statuses)
                where_parts.append(f"p.status IN ({placeholders})")
                parameters.extend(statuses)
            elif view_mode == "saved" and not has_specific_status_filter:
                where_parts.append("p.status = ?")
                parameters.append("saved")
            elif view_mode == "rejected" and not has_specific_status_filter:
                where_parts.append("p.status IN (?, ?)")
                parameters.append("rejected")
            elif view_mode == "known" and not has_specific_status_filter:
                where_parts.append("p.status IN (?, ?)")
                parameters.append("already_known")
            elif view_mode == "all" or has_specific_status_filter:
                pass
            else:
                raise ValueError(f"Invalid view_mode: {view_mode}")

            if has_specific_status_filter:
                where_parts.append("p.status = ?")
                parameters.append(status_filter)

        if text_filter:
            positive_terms, negative_terms = parse_preview_search_terms(text_filter)

            for term in positive_terms:
                pattern = f"%{term}%"
                if is_path_like_preview_search_term(term):
                    where_parts.append(
                        """
                        (
                            CAST(p.id AS TEXT) LIKE ?
                            OR p.final_file_path LIKE ?
                            OR p.final_directory LIKE ?
                            OR EXISTS (
                                SELECT 1
                                FROM post_tags pt
                                WHERE pt.post_id = p.id
                                  AND pt.tag = ? COLLATE NOCASE
                            )
                        )
                        """
                    )
                    parameters.extend([pattern, pattern, pattern, term])
                else:
                    where_parts.append(
                        """
                        (
                            CAST(p.id AS TEXT) LIKE ?
                            OR EXISTS (
                                SELECT 1
                                FROM post_tags pt
                                WHERE pt.post_id = p.id
                                  AND pt.tag = ? COLLATE NOCASE
                            )
                        )
                        """
                    )
                    parameters.extend([pattern, term])

            for term in negative_terms:
                where_parts.append(
                    """
                    NOT EXISTS (
                        SELECT 1
                        FROM post_tags pt_excl
                        WHERE pt_excl.post_id = p.id
                          AND pt_excl.tag = ? COLLATE NOCASE
                    )
                    """
                )
                parameters.append(term)

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        return where_sql, parameters

    def get_post_detail(self, post_id: int) -> sqlite3.Row | None:
        return self.execute(
            """
            SELECT
                p.*,
                CASE
                    WHEN p.parent_id IS NOT NULL
                     AND EXISTS (
                         SELECT 1
                         FROM posts parent
                         WHERE parent.id = p.parent_id
                           AND parent.final_file_path IS NOT NULL
                           AND parent.final_file_path != ''
                     )
                    THEN 1
                    ELSE 0
                END AS known_parent_loaded,
                (
                    SELECT COUNT(*)
                    FROM posts child
                    WHERE child.parent_id = p.id
                      AND child.final_file_path IS NOT NULL
                      AND child.final_file_path != ''
                ) AS known_child_count,
                (
                    SELECT GROUP_CONCAT(pt.tag, ' ')
                    FROM post_tags pt
                    WHERE pt.post_id = p.id
                    ORDER BY
                        CASE pt.tag_type
                            WHEN 'copyright' THEN 1
                            WHEN 'character' THEN 2
                            WHEN 'artist' THEN 3
                            WHEN 'general' THEN 4
                            WHEN 'meta' THEN 5
                            ELSE 9
                        END,
                        pt.tag
                ) AS tags,
                (
                    SELECT GROUP_CONCAT(pt.tag, ' ')
                    FROM post_tags pt
                    WHERE pt.post_id = p.id AND pt.tag_type = 'general'
                    ORDER BY pt.tag
                ) AS tags_general,
                (
                    SELECT GROUP_CONCAT(pt.tag, ' ')
                    FROM post_tags pt
                    WHERE pt.post_id = p.id AND pt.tag_type = 'character'
                    ORDER BY pt.tag
                ) AS tags_character,
                (
                    SELECT GROUP_CONCAT(pt.tag, ' ')
                    FROM post_tags pt
                    WHERE pt.post_id = p.id AND pt.tag_type = 'copyright'
                    ORDER BY pt.tag
                ) AS tags_copyright,
                (
                    SELECT GROUP_CONCAT(pt.tag, ' ')
                    FROM post_tags pt
                    WHERE pt.post_id = p.id AND pt.tag_type = 'artist'
                    ORDER BY pt.tag
                ) AS tags_artist,
                (
                    SELECT GROUP_CONCAT(pt.tag, ' ')
                    FROM post_tags pt
                    WHERE pt.post_id = p.id AND pt.tag_type = 'meta'
                    ORDER BY pt.tag
                ) AS tags_meta,
                (
                    SELECT stars
                    FROM post_reviews pr
                    WHERE pr.post_id = p.id
                ) AS stars
            FROM posts p
            WHERE p.id = ?
            """,
            (post_id,),
        ).fetchone()

    def get_related_posts(self, post_id: int) -> list[sqlite3.Row]:
        current = self.execute("SELECT id, parent_id FROM posts WHERE id = ?", (post_id,)).fetchone()
        if current is None:
            return []

        rows: list[sqlite3.Row] = []

        parent_id = current["parent_id"]
        if parent_id is not None:
            parent = self.execute(
                """
                SELECT
                    'parent' AS relation,
                    id,
                    parent_id,
                    status,
                    rating,
                    score,
                    final_file_path,
                    thumbnail_path,
                    rejected_thumbnail_path
                FROM posts
                WHERE id = ?
                """,
                (parent_id,),
            ).fetchone()
            if parent is not None:
                rows.append(parent)

        rows.extend(
            self.execute(
                """
                SELECT
                    'child' AS relation,
                    id,
                    parent_id,
                    status,
                    rating,
                    score,
                    final_file_path,
                    thumbnail_path,
                    rejected_thumbnail_path
                FROM posts
                WHERE parent_id = ?
                ORDER BY id DESC
                """,
                (post_id,),
            ).fetchall()
        )

        return rows

    def update_post_remote_metadata(self, post_id: int, post: dict[str, Any]) -> None:
        self.execute(
            """
            UPDATE posts
            SET image_width = COALESCE(?, image_width),
                image_height = COALESCE(?, image_height),
                file_size = COALESCE(?, file_size),
                file_url = COALESCE(NULLIF(?, ''), file_url),
                large_file_url = COALESCE(NULLIF(?, ''), large_file_url),
                preview_url = COALESCE(NULLIF(?, ''), preview_url),
                file_ext = COALESCE(NULLIF(?, ''), file_ext),
                last_seen_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                post.get("image_width"),
                post.get("image_height"),
                post.get("file_size"),
                str(post.get("file_url") or ""),
                str(post.get("large_file_url") or ""),
                str(post.get("preview_file_url") or post.get("preview_url") or ""),
                str(post.get("file_ext") or ""),
                post_id,
            ),
        )
        self.commit()

    def fetch_saved_posts_for_quality_audit(self) -> list[sqlite3.Row]:
        return list(
            self.execute(
                """
                SELECT
                    id,
                    file_url,
                    file_ext,
                    image_width,
                    image_height,
                    file_size,
                    final_file_path,
                    final_directory,
                    original_cache_path
                FROM posts
                WHERE final_file_path IS NOT NULL
                  AND final_file_path != ''
                ORDER BY saved_at DESC, id DESC
                """
            ).fetchall()
        )

    def set_original_cache_path(self, post_id: int, path: str) -> None:
        self.execute(
            """
            UPDATE posts
            SET original_cache_path = ?,
                downloaded_at = COALESCE(downloaded_at, CURRENT_TIMESTAMP)
            WHERE id = ?
            """,
            (path, post_id),
        )
        self.commit()

    def set_post_review(self, post_id: int, stars: float | None = None, decision: str | None = None) -> None:
        self.execute(
            """
            INSERT INTO post_reviews (post_id, stars, decision, reviewed_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(post_id) DO UPDATE SET
                stars = COALESCE(excluded.stars, post_reviews.stars),
                decision = COALESCE(excluded.decision, post_reviews.decision),
                reviewed_at = CURRENT_TIMESTAMP
            """,
            (post_id, stars, decision),
        )
        self.execute("UPDATE posts SET reviewed_at = CURRENT_TIMESTAMP WHERE id = ?", (post_id,))
        self.refresh_tag_statistics_for_post(post_id)
        self.commit()

    def set_post_status(self, post_id: int, status: str, config: dict[str, Any] | None = None) -> None:
        self._set_post_status_no_commit(post_id, status, config)
        self.refresh_tag_statistics_for_post(post_id)
        self.commit()

    def set_post_statuses(self, post_ids: list[int], status: str, config: dict[str, Any] | None = None) -> None:
        clean_ids = []
        seen: set[int] = set()
        for post_id in post_ids:
            post_id_int = int(post_id)
            if post_id_int in seen:
                continue
            seen.add(post_id_int)
            clean_ids.append(post_id_int)

        if not clean_ids:
            return

        if status not in ALL_ALLOWED_STATUSES:
            raise ValueError(f"Invalid status: {status}")

        scoring_statuses = {"saved", "rejected", "auto_rejected"}
        old_statuses = self._fetch_statuses_for_posts(clean_ids)
        needs_tag_statistics_refresh = status in scoring_statuses or any(
            old_status in scoring_statuses for old_status in old_statuses.values()
        )
        affected_tags = self._fetch_tags_for_posts(clean_ids) if needs_tag_statistics_refresh else []

        for post_id in clean_ids:
            self._set_post_status_no_commit(post_id, status, config)

        # Important for the previewer: with 100 selected thumbnails, do not aggregate
        # the same tag statistics once per post. It was technically correct, but about
        # as elegant for performance as a database join wearing concrete shoes. Update
        # the combined tag set exactly once, and only when saved/rejected is actually
        # affected for score calculation.
        if affected_tags:
            self.refresh_tag_statistics_for_tags(affected_tags)

        self.commit()

    def _fetch_statuses_for_posts(self, post_ids: list[int]) -> dict[int, str]:
        clean_ids = [int(post_id) for post_id in post_ids]
        if not clean_ids:
            return {}

        placeholders = ", ".join("?" for _ in clean_ids)
        rows = self.execute(
            f"SELECT id, status FROM posts WHERE id IN ({placeholders})",
            clean_ids,
        ).fetchall()
        return {int(row["id"]): str(row["status"] or "") for row in rows}

    def _fetch_tags_for_posts(self, post_ids: list[int]) -> list[str]:
        clean_ids = [int(post_id) for post_id in post_ids]
        if not clean_ids:
            return []

        placeholders = ", ".join("?" for _ in clean_ids)
        rows = self.execute(
            f"SELECT DISTINCT tag FROM post_tags WHERE post_id IN ({placeholders})",
            clean_ids,
        ).fetchall()
        return [str(row["tag"]) for row in rows if str(row["tag"] or "").strip()]

    def _set_post_status_no_commit(self, post_id: int, status: str, config: dict[str, Any] | None = None) -> None:
        if status not in ALL_ALLOWED_STATUSES:
            raise ValueError(f"Invalid status: {status}")

        extra_sets: list[str] = []
        parameters: list[Any] = [status]

        if status == "selected_save":
            extra_sets.append("selected_at = COALESCE(selected_at, CURRENT_TIMESTAMP)")
        elif status in {"rejected", "auto_rejected"}:
            extra_sets.append("rejected_at = COALESCE(rejected_at, CURRENT_TIMESTAMP)")
        elif status == "saved":
            extra_sets.append("saved_at = COALESCE(saved_at, CURRENT_TIMESTAMP)")
        elif status == "already_known":
            extra_sets.append("already_known_at = COALESCE(already_known_at, CURRENT_TIMESTAMP)")

        if config is not None:
            moved_thumbnail_path = None
            if status in {"rejected", "auto_rejected"}:
                moved_thumbnail_path = self.move_thumbnail_to_bucket(post_id, Path(config["rejected_thumbnail_dir"]))
                if moved_thumbnail_path:
                    extra_sets.append("rejected_thumbnail_path = ?")
                    parameters.append(moved_thumbnail_path)
            elif status == "saved":
                moved_thumbnail_path = self.move_thumbnail_to_bucket(post_id, Path(config["saved_thumbnail_dir"]))
                if moved_thumbnail_path:
                    extra_sets.append("thumbnail_path = ?")
                    parameters.append(moved_thumbnail_path)

        set_sql = "status = ?"
        if extra_sets:
            set_sql += ", " + ", ".join(extra_sets)

        parameters.append(post_id)

        self.execute(
            f"""
            UPDATE posts
            SET {set_sql}
            WHERE id = ?
            """,
            parameters,
        )

    def move_thumbnail_to_bucket(self, post_id: int, target_dir: Path) -> str | None:
        row = self.execute(
            "SELECT thumbnail_path, rejected_thumbnail_path FROM posts WHERE id = ?",
            (post_id,),
        ).fetchone()

        if row is None:
            return None

        source_value = row["thumbnail_path"] or row["rejected_thumbnail_path"]
        if not source_value:
            return None

        source = Path(str(source_value))
        if not source.exists():
            return None

        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name

        if source.resolve() == target.resolve():
            return str(target)

        shutil.move(str(source), str(target))
        return str(target)

    def assign_post_category(self, post_id: int, category_id: int, source: str = "manual") -> None:
        """Store exactly one effective category assignment for a post."""
        self.execute("DELETE FROM post_categories WHERE post_id = ?", (post_id,))
        self.execute(
            """
            INSERT INTO post_categories (post_id, category_id, source)
            VALUES (?, ?, ?)
            """,
            (post_id, category_id, source),
        )
        self.commit()

    def assign_post_category_by_name(self, post_id: int, category_name: str, source: str = "manual") -> None:
        category = self.get_category_by_name(category_name)
        if category is None:
            raise RuntimeError(f"Category not found: {category_name}")
        self.assign_post_category(post_id, int(category["id"]), source)

    def reassign_posts_category(
        self,
        post_ids: list[int],
        old_category_id: int,
        new_category_id: int,
        source: str = "import-repair",
    ) -> None:
        clean_ids: list[int] = []
        seen: set[int] = set()
        for post_id in post_ids:
            post_id_int = int(post_id)
            if post_id_int in seen:
                continue
            seen.add(post_id_int)
            clean_ids.append(post_id_int)

        if not clean_ids:
            return

        affected_tags = self._fetch_tags_for_posts(clean_ids)
        placeholders = ", ".join("?" for _ in clean_ids)
        parameters: list[Any] = [int(old_category_id), *clean_ids]

        self.execute(
            f"""
            DELETE FROM post_categories
            WHERE category_id = ?
              AND post_id IN ({placeholders})
            """,
            parameters,
        )

        self.executemany(
            """
            INSERT INTO post_categories (post_id, category_id, source)
            VALUES (?, ?, ?)
            ON CONFLICT(post_id, category_id) DO UPDATE SET
                source = excluded.source
            """,
            [(post_id, int(new_category_id), source) for post_id in clean_ids],
        )

        self.execute(
            f"""
            UPDATE posts
            SET last_seen_at = CURRENT_TIMESTAMP
            WHERE id IN ({placeholders})
            """,
            clean_ids,
        )

        if affected_tags:
            self.refresh_tag_statistics_for_tags(affected_tags)

        self.commit()

    def import_existing_saved_file(self, post_id: int, category_id: int, file_path: str, source: str = "import") -> None:
        """Mark an already downloaded local file as saved and feed its tags into scoring.

        Used by the legacy-file importer. It deliberately does not move files,
        because the import source folder is supposed to remain under the user's
        control. Touching old download folders without being asked is how tools
        earn uninstall privileges.
        """
        path = Path(str(file_path)).expanduser()
        final_path = str(path)
        final_directory = str(path.parent)

        self.execute(
            """
            UPDATE posts
            SET status = 'saved',
                final_file_path = ?,
                final_directory = ?,
                original_path = COALESCE(original_path, ?),
                downloaded_at = COALESCE(downloaded_at, CURRENT_TIMESTAMP),
                saved_at = COALESCE(saved_at, CURRENT_TIMESTAMP),
                reviewed_at = COALESCE(reviewed_at, CURRENT_TIMESTAMP),
                last_seen_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (final_path, final_directory, final_path, int(post_id)),
        )

        self.execute("DELETE FROM post_categories WHERE post_id = ?", (int(post_id),))
        self.execute(
            """
            INSERT INTO post_categories (post_id, category_id, source)
            VALUES (?, ?, ?)
            """,
            (int(post_id), int(category_id), source),
        )

        affected_tags = self._fetch_tags_for_posts([int(post_id)])
        if affected_tags:
            self.refresh_tag_statistics_for_tags(affected_tags)

        self.commit()

    def update_post_final_file_path(self, post_id: int, file_path: str) -> None:
        path = Path(str(file_path)).expanduser()
        self.execute(
            """
            UPDATE posts
            SET final_file_path = ?,
                final_directory = ?,
                original_path = COALESCE(original_path, ?),
                status = 'saved',
                saved_at = COALESCE(saved_at, CURRENT_TIMESTAMP),
                last_seen_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (str(path), str(path.parent), str(path), int(post_id)),
        )
        self.commit()

    def fetch_saved_file_posts_for_category(self, category_id: int | None = None) -> list[sqlite3.Row]:
        parameters: list[Any] = []
        category_filter = ""
        if category_id is not None:
            category_filter = "AND pc.category_id = ?"
            parameters.append(int(category_id))

        return list(
            self.execute(
                f"""
                SELECT DISTINCT
                    p.id,
                    p.final_file_path,
                    p.file_ext,
                    pc.category_id
                FROM posts p
                JOIN post_categories pc ON pc.post_id = p.id
                WHERE p.final_file_path IS NOT NULL
                  AND p.final_file_path != ''
                  AND p.status = 'saved'
                  {category_filter}
                ORDER BY p.saved_at DESC, p.id DESC
                """,
                parameters,
            ).fetchall()
        )

    def get_assigned_category_for_post(self, post_id: int) -> sqlite3.Row | None:
        return self.execute(
            """
            SELECT c.*, pc.source AS assignment_source
            FROM post_categories pc
            JOIN categories c ON c.id = pc.category_id
            WHERE pc.post_id = ?
            ORDER BY CASE pc.source WHEN 'manual' THEN 0 ELSE 1 END, c.sort_order, c.name
            LIMIT 1
            """,
            (post_id,),
        ).fetchone()

    def clear_post_final_file_path(self, post_id: int, new_status: str | None = None) -> None:
        """Clear the saved/final file reference after the local final file was deleted."""
        if new_status:
            self.execute(
                """
                UPDATE posts
                SET final_file_path = NULL,
                    final_directory = NULL,
                    saved_at = NULL,
                    status = ?
                WHERE id = ?
                """,
                (str(new_status), int(post_id)),
            )
        else:
            self.execute(
                """
                UPDATE posts
                SET final_file_path = NULL,
                    final_directory = NULL,
                    saved_at = NULL
                WHERE id = ?
                """,
                (int(post_id),),
            )
        self.commit()

    def delete_post_record(self, post_id: int) -> None:
        """Remove one post and dependent DB rows, but do not delete image files."""
        self.execute("DELETE FROM post_reviews WHERE post_id = ?", (post_id,))
        self.execute("DELETE FROM post_categories WHERE post_id = ?", (post_id,))
        self.execute("DELETE FROM post_tags WHERE post_id = ?", (post_id,))
        self.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        self.commit()
