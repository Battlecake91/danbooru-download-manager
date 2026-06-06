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


class DatabaseTagMixin:
    """Tag catalog, aliases, filename excludes, scoring, and suggestions."""

    def fetch_tag_overview(
        self,
        search_text: str | None = None,
        tag_type: str | None = None,
        limit: int = 1000,
        source: str = "local",
    ) -> list[sqlite3.Row]:
        """Return tag overview rows from local posts, Danbooru catalog or both."""
        where_parts: list[str] = []
        parameters: list[Any] = []

        if search_text:
            where_parts.append("merged.tag LIKE ?")
            parameters.append(f"%{search_text.strip()}%")

        if tag_type and tag_type != "all":
            where_parts.append("merged.tag_type = ?")
            parameters.append(tag_type)

        source = str(source or "local").lower()
        if source == "local":
            where_parts.append("merged.local_post_count > 0")
        elif source == "catalog":
            where_parts.append("merged.catalog_post_count > 0")
        elif source == "catalog_only":
            where_parts.append("merged.catalog_post_count > 0 AND merged.local_post_count = 0")

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        parameters.append(limit)

        return list(
            self.execute(
                f"""
                WITH local_tags AS (
                    SELECT
                        pt.tag AS tag,
                        MIN(pt.tag_type) AS tag_type,
                        COUNT(DISTINCT pt.post_id) AS local_post_count,
                        SUM(CASE WHEN p.status = 'saved' THEN 1 ELSE 0 END) AS saved_count,
                        SUM(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
                        SUM(CASE WHEN p.status IN ('new', 'potential') THEN 1 ELSE 0 END) AS open_count,
                        COALESCE(ts.average_rating, AVG(pr.stars)) AS average_rating
                    FROM post_tags pt
                    JOIN posts p ON p.id = pt.post_id
                    LEFT JOIN tag_scores ts ON ts.tag = pt.tag
                    LEFT JOIN post_reviews pr ON pr.post_id = pt.post_id AND pr.stars IS NOT NULL
                    GROUP BY pt.tag
                ),
                all_tags AS (
                    SELECT tag FROM local_tags
                    UNION
                    SELECT name AS tag FROM danbooru_tags
                ),
                merged AS (
                    SELECT
                        all_tags.tag AS tag,
                        COALESCE(local_tags.tag_type, danbooru_tags.category, 'general') AS tag_type,
                        COALESCE(local_tags.local_post_count, 0) AS local_post_count,
                        COALESCE(danbooru_tags.post_count, 0) AS catalog_post_count,
                        COALESCE(local_tags.saved_count, 0) AS saved_count,
                        COALESCE(local_tags.rejected_count, 0) AS rejected_count,
                        COALESCE(local_tags.open_count, 0) AS open_count,
                        local_tags.average_rating AS local_average_rating
                    FROM all_tags
                    LEFT JOIN local_tags ON local_tags.tag = all_tags.tag
                    LEFT JOIN danbooru_tags ON danbooru_tags.name = all_tags.tag
                )
                SELECT
                    merged.tag AS tag,
                    merged.tag_type AS tag_type,
                    CASE
                        WHEN merged.local_post_count > 0 THEN merged.local_post_count
                        ELSE merged.catalog_post_count
                    END AS post_count,
                    merged.local_post_count AS local_post_count,
                    merged.catalog_post_count AS danbooru_post_count,
                    CASE
                        WHEN merged.local_post_count > 0 AND merged.catalog_post_count > 0 THEN 'both'
                        WHEN merged.catalog_post_count > 0 THEN 'catalog'
                        ELSE 'local'
                    END AS tag_source,
                    merged.saved_count AS saved_count,
                    merged.rejected_count AS rejected_count,
                    merged.open_count AS open_count,
                    COALESCE(ts.manual_score, '') AS manual_score,
                    COALESCE(ts.computed_score, 0) AS computed_score,
                    COALESCE(ts.average_rating, merged.local_average_rating) AS average_rating,
                    COALESCE(ts.scoring_excluded, 0) AS scoring_excluded,
                    COALESCE(ts.ignore_category_influence, 0) AS ignore_category_influence,
                    COALESCE(ts.ignore_recommendation_score, 0) AS ignore_recommendation_score,
                    COALESCE(ts.ignore_llm_input, 0) AS ignore_llm_input,
                    COALESCE(ta.alias_tag, dta.consequent_name, '') AS alias_tag,
                    CASE WHEN fet.tag IS NULL THEN 0 ELSE 1 END AS filename_excluded,
                    CASE WHEN xet.tag IS NULL THEN 0 ELSE 1 END AS fetch_excluded
                FROM merged
                LEFT JOIN tag_scores ts ON ts.tag = merged.tag
                LEFT JOIN tag_aliases ta ON ta.original_tag = merged.tag
                LEFT JOIN danbooru_tag_aliases dta ON dta.antecedent_name = merged.tag AND LOWER(COALESCE(dta.status, 'active')) IN ('active', 'approved')
                LEFT JOIN filename_excluded_tags fet ON fet.tag = merged.tag
                LEFT JOIN fetch_excluded_tags xet ON xet.tag = merged.tag
                {where_sql}
                ORDER BY post_count DESC, merged.tag ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        )

    def upsert_danbooru_tags(self, tags: Iterable[dict[str, Any]]) -> int:
        category_names = {0: "general", 1: "artist", 3: "copyright", 4: "character", 5: "meta"}
        rows: list[tuple[str, str, int | None, int, int, str]] = []
        for tag in tags:
            name = normalize_tag_token(str(tag.get("name") or ""))
            if not name:
                continue
            raw_category = tag.get("category")
            try:
                category_id = int(raw_category) if raw_category is not None else None
            except (TypeError, ValueError):
                category_id = None
            category = category_names.get(category_id, str(raw_category or "general").lower())
            try:
                post_count = int(tag.get("post_count") or 0)
            except (TypeError, ValueError):
                post_count = 0
            is_deprecated = 1 if tag.get("is_deprecated") else 0
            rows.append((name, category, category_id, post_count, is_deprecated, json.dumps(tag, ensure_ascii=False, sort_keys=True)))

        if not rows:
            return 0

        self.executemany(
            """
            INSERT INTO danbooru_tags (name, category, category_id, post_count, is_deprecated, raw_json, last_synced_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET
                category = excluded.category,
                category_id = excluded.category_id,
                post_count = excluded.post_count,
                is_deprecated = excluded.is_deprecated,
                raw_json = excluded.raw_json,
                last_synced_at = CURRENT_TIMESTAMP
            """,
            rows,
        )
        for name, *_ in rows:
            self.execute(
                """
                INSERT INTO tag_scores (tag)
                VALUES (?)
                ON CONFLICT(tag) DO NOTHING
                """,
                (name,),
            )
        self.commit()
        return len(rows)

    def upsert_danbooru_tag_aliases(self, aliases: Iterable[dict[str, Any]]) -> int:
        rows: list[tuple[str, str, str, str]] = []
        for alias in aliases:
            antecedent = normalize_tag_token(str(alias.get("antecedent_name") or alias.get("antecedent") or ""))
            consequent = normalize_tag_token(str(alias.get("consequent_name") or alias.get("consequent") or ""))
            if not antecedent or not consequent:
                continue
            rows.append((antecedent, consequent, str(alias.get("status") or ""), json.dumps(alias, ensure_ascii=False, sort_keys=True)))

        if not rows:
            return 0

        self.executemany(
            """
            INSERT INTO danbooru_tag_aliases (antecedent_name, consequent_name, status, raw_json, last_synced_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(antecedent_name) DO UPDATE SET
                consequent_name = excluded.consequent_name,
                status = excluded.status,
                raw_json = excluded.raw_json,
                last_synced_at = CURRENT_TIMESTAMP
            """,
            rows,
        )
        self.commit()
        return len(rows)

    def count_danbooru_tags(self) -> int:
        row = self.execute("SELECT COUNT(*) AS count FROM danbooru_tags").fetchone()
        return int(row["count"] if row else 0)

    def search_tags_by_pattern(
        self,
        pattern: str,
        tag_type: str | None = None,
        limit: int = 1000,
    ) -> list[sqlite3.Row]:
        """Search tags with shell-style wildcards.

        Supported wildcards:
        - ``*`` matches any number of characters
        - ``?`` matches one character

        SQL LIKE treats ``_`` as a wildcard, which is adorable until your tag
        database is made almost entirely of underscores. Escape first, then add
        our own wildcards.
        """
        clean_pattern = str(pattern or "").strip()
        if not clean_pattern:
            return []

        like_pattern = (
            clean_pattern
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
            .replace("*", "%")
            .replace("?", "_")
        )

        where_parts = ["pt.tag LIKE ? ESCAPE '\\'"]
        parameters: list[Any] = [like_pattern]

        if tag_type and tag_type != "all":
            where_parts.append("pt.tag_type = ?")
            parameters.append(tag_type)

        parameters.append(limit)

        return list(
            self.execute(
                f"""
                SELECT
                    pt.tag AS tag,
                    MIN(pt.tag_type) AS tag_type,
                    COUNT(DISTINCT pt.post_id) AS post_count,
                    ta.alias_tag AS alias_tag,
                    CASE WHEN fet.tag IS NULL THEN 0 ELSE 1 END AS filename_excluded,
                    CASE WHEN xet.tag IS NULL THEN 0 ELSE 1 END AS fetch_excluded,
                    COALESCE(ts.ignore_category_influence, 0) AS ignore_category_influence,
                    COALESCE(ts.ignore_recommendation_score, 0) AS ignore_recommendation_score,
                    COALESCE(ts.ignore_llm_input, 0) AS ignore_llm_input
                FROM post_tags pt
                LEFT JOIN tag_aliases ta ON ta.original_tag = pt.tag
                LEFT JOIN filename_excluded_tags fet ON fet.tag = pt.tag
                LEFT JOIN fetch_excluded_tags xet ON xet.tag = pt.tag
                LEFT JOIN tag_scores ts ON ts.tag = pt.tag
                WHERE {" AND ".join(where_parts)}
                GROUP BY pt.tag
                ORDER BY post_count DESC, pt.tag ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        )

    def fetch_category_tag_hits(self, tags: Iterable[str]) -> list[sqlite3.Row]:
        """Return category/tag co-occurrences with normalization data.

        The category influence engine must not simply reward raw hit counts.
        Otherwise a broad tag such as ``1girl`` makes the largest category win
        forever, which is less "suggestion" and more "database astrology".
        The extra totals allow the caller to score distinctive tags by lift and
        per-category coverage instead of absolute popularity.
        """
        clean_tags = sorted({normalize_tag_token(str(tag)) for tag in tags if normalize_tag_token(str(tag))})
        if not clean_tags:
            return []

        placeholders = ", ".join("?" for _ in clean_tags)
        parameters = [*clean_tags, *clean_tags]
        return list(
            self.execute(
                f"""
                WITH
                category_totals AS (
                    SELECT
                        category_id,
                        COUNT(DISTINCT post_id) AS category_post_count
                    FROM post_categories
                    GROUP BY category_id
                ),
                global_total AS (
                    SELECT COUNT(DISTINCT post_id) AS categorized_post_count
                    FROM post_categories
                ),
                tag_totals AS (
                    SELECT
                        pt.tag AS tag,
                        COUNT(DISTINCT pc.post_id) AS tag_total_hits
                    FROM post_categories pc
                    JOIN post_tags pt ON pt.post_id = pc.post_id
                    WHERE pt.tag IN ({placeholders})
                    GROUP BY pt.tag
                )
                SELECT
                    c.id AS category_id,
                    c.name AS category_name,
                    pt.tag AS tag,
                    COUNT(DISTINCT pt.post_id) AS hit_count,
                    SUM(CASE WHEN p.status = 'saved' THEN 1 ELSE 0 END) AS saved_hits,
                    AVG(pr.stars) AS avg_stars,
                    COALESCE(ct.category_post_count, 0) AS category_post_count,
                    COALESCE(tt.tag_total_hits, 0) AS tag_total_hits,
                    COALESCE(gt.categorized_post_count, 0) AS categorized_post_count
                FROM post_categories pc
                JOIN categories c ON c.id = pc.category_id
                JOIN post_tags pt ON pt.post_id = pc.post_id
                JOIN posts p ON p.id = pc.post_id
                LEFT JOIN post_reviews pr ON pr.post_id = pc.post_id AND pr.stars IS NOT NULL
                LEFT JOIN category_totals ct ON ct.category_id = pc.category_id
                LEFT JOIN tag_totals tt ON tt.tag = pt.tag
                CROSS JOIN global_total gt
                WHERE pt.tag IN ({placeholders})
                GROUP BY c.id, pt.tag
                ORDER BY c.sort_order ASC, c.name ASC, hit_count DESC, pt.tag ASC
                """,
                parameters,
            ).fetchall()
        )

    def fetch_tag_display_metadata(self, tags: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Return cheap per-tag metadata for viewer display and influence scoring.

        ``fetch_tag_metadata`` intentionally computes historical aggregates such
        as saved/rejected counts and average ratings. That is useful in the tag
        tab, but far too expensive for every image switch in the viewer. This
        fast path only reads direct tag settings plus alias/LLM identity data.
        Heavy historical fields are returned as neutral placeholders so the
        existing widgets can keep using one metadata shape.
        """
        clean_tags = sorted({normalize_tag_token(str(tag)) for tag in tags if normalize_tag_token(str(tag))})
        if not clean_tags:
            return {}

        placeholders = ", ".join("?" for _ in clean_tags)
        score_rows = self.execute(
            f"""
            SELECT
                tag,
                manual_score,
                COALESCE(computed_score, 0) AS stored_computed_score,
                COALESCE(scoring_excluded, 0) AS scoring_excluded,
                COALESCE(ignore_category_influence, 0) AS ignore_category_influence,
                COALESCE(ignore_recommendation_score, 0) AS ignore_recommendation_score,
                COALESCE(ignore_llm_input, 0) AS ignore_llm_input,
                average_rating
            FROM tag_scores
            WHERE tag IN ({placeholders})
            """,
            clean_tags,
        ).fetchall()
        score_by_tag = {str(row["tag"] or ""): row for row in score_rows}

        excluded_rows = self.execute(
            f"""
            SELECT tag
            FROM filename_excluded_tags
            WHERE tag IN ({placeholders})
            """,
            clean_tags,
        ).fetchall()
        filename_excluded = {str(row["tag"] or "") for row in excluded_rows}
        fetch_excluded_rows = self.execute(
            f"SELECT tag FROM fetch_excluded_tags WHERE tag IN ({placeholders})",
            clean_tags,
        ).fetchall()
        fetch_excluded = {str(row["tag"] or "") for row in fetch_excluded_rows}

        identities = self.build_tag_identities(clean_tags)
        result: dict[str, dict[str, Any]] = {}
        for tag in clean_tags:
            row = score_by_tag.get(tag)
            identity = identities.get(normalize_tag_token(tag), {})
            scoring_excluded = bool(row["scoring_excluded"]) if row is not None else False
            manual_score = row["manual_score"] if row is not None else None
            stored_computed_score = row["stored_computed_score"] if row is not None else 0.0
            computed_score = 0.0 if scoring_excluded else float(stored_computed_score or 0.0)
            effective_score = 0.0 if scoring_excluded else (manual_score if manual_score is not None else computed_score)
            result[tag] = {
                "canonical_tag": identity.get("canonical_tag", tag),
                "llm_token": identity.get("llm_token", ""),
                "score": effective_score,
                "manual_score": manual_score,
                "computed_score": computed_score,
                "stored_computed_score": stored_computed_score,
                "scoring_excluded": scoring_excluded,
                "ignore_category_influence": bool(row["ignore_category_influence"]) if row is not None else False,
                "ignore_recommendation_score": bool(row["ignore_recommendation_score"]) if row is not None else False,
                "ignore_llm_input": bool(row["ignore_llm_input"]) if row is not None else False,
                "filename_excluded": tag in filename_excluded,
                "fetch_excluded": tag in fetch_excluded,
                "average_rating": row["average_rating"] if row is not None else None,
                "rating_count": 0,
                "saved_count": 0,
                "rejected_count": 0,
                "post_count": 0,
            }
        return result

    def fetch_tag_metadata(self, tags: Iterable[str]) -> dict[str, dict[str, Any]]:
        clean_tags = sorted({str(tag).strip() for tag in tags if str(tag).strip()})
        if not clean_tags:
            return {}

        placeholders = ", ".join("?" for _ in clean_tags)
        rows = self.execute(
            f"""
            SELECT
                pt.tag AS tag,
                ts.manual_score AS manual_score,
                COALESCE(ts.computed_score, 0) AS stored_computed_score,
                COALESCE(ts.scoring_excluded, 0) AS scoring_excluded,
                COALESCE(ts.ignore_category_influence, 0) AS ignore_category_influence,
                COALESCE(ts.ignore_recommendation_score, 0) AS ignore_recommendation_score,
                COALESCE(ts.ignore_llm_input, 0) AS ignore_llm_input,
                CASE WHEN fet.tag IS NULL THEN 0 ELSE 1 END AS filename_excluded,
                    CASE WHEN xet.tag IS NULL THEN 0 ELSE 1 END AS fetch_excluded,
                COALESCE(ts.average_rating, AVG(pr.stars)) AS average_rating,
                COUNT(pr.stars) AS rating_count,
                SUM(CASE WHEN p.status = 'saved' THEN 1 ELSE 0 END) AS saved_count,
                SUM(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
                COUNT(DISTINCT pt.post_id) AS post_count
            FROM post_tags pt
            JOIN posts p ON p.id = pt.post_id
            LEFT JOIN tag_scores ts ON ts.tag = pt.tag
            LEFT JOIN filename_excluded_tags fet ON fet.tag = pt.tag
                LEFT JOIN fetch_excluded_tags xet ON xet.tag = pt.tag
            LEFT JOIN post_reviews pr ON pr.post_id = pt.post_id AND pr.stars IS NOT NULL
            WHERE pt.tag IN ({placeholders})
              AND (
                    p.status = 'saved'
                    OR NOT EXISTS (
                        SELECT 1
                        FROM posts family_saved
                        WHERE family_saved.status = 'saved'
                          AND COALESCE(family_saved.parent_id, family_saved.id) =
                              COALESCE(p.parent_id, p.id)
                    )
              )
            GROUP BY pt.tag
            """,
            clean_tags,
        ).fetchall()

        identities = self.build_tag_identities(clean_tags)

        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            tag = str(row["tag"] or "")
            identity = identities.get(normalize_tag_token(tag), {})
            scoring_excluded = bool(row["scoring_excluded"])
            saved_count = int(row["saved_count"] or 0)
            rejected_count = int(row["rejected_count"] or 0)
            computed_score = calculate_computed_tag_score(
                average_rating=row["average_rating"],
                saved_count=saved_count,
                rejected_count=rejected_count,
                scoring_excluded=scoring_excluded,
            )
            manual_score = row["manual_score"]
            effective_score = 0.0 if scoring_excluded else (manual_score if manual_score is not None else computed_score)
            result[tag] = {
                "canonical_tag": identity.get("canonical_tag", tag),
                "llm_token": identity.get("llm_token", ""),
                "score": effective_score,
                "manual_score": manual_score,
                "computed_score": computed_score,
                "stored_computed_score": row["stored_computed_score"],
                "scoring_excluded": scoring_excluded,
                "ignore_category_influence": bool(row["ignore_category_influence"]),
                "ignore_recommendation_score": bool(row["ignore_recommendation_score"]),
                "ignore_llm_input": bool(row["ignore_llm_input"]),
                "filename_excluded": bool(row["filename_excluded"]),
                "fetch_excluded": bool(row["fetch_excluded"]),
                "average_rating": row["average_rating"],
                "rating_count": int(row["rating_count"] or 0),
                "saved_count": saved_count,
                "rejected_count": rejected_count,
                "post_count": int(row["post_count"] or 0),
            }
        return result

    def add_filename_excluded_tag(self, tag: str, reason: str = "manual") -> None:
        clean_tag = tag.strip()
        if not clean_tag:
            return

        self.execute(
            """
            INSERT INTO filename_excluded_tags (tag, reason)
            VALUES (?, ?)
            ON CONFLICT(tag) DO UPDATE SET reason = excluded.reason
            """,
            (clean_tag, reason),
        )
        self.commit()

    def remove_filename_excluded_tag(self, tag: str) -> None:
        self.execute("DELETE FROM filename_excluded_tags WHERE tag = ?", (tag,))
        self.commit()

    def list_filename_excluded_tags(self, search_text: str | None = None) -> list[sqlite3.Row]:
        if search_text:
            return list(
                self.execute(
                    """
                    SELECT tag, reason
                    FROM filename_excluded_tags
                    WHERE tag LIKE ?
                    ORDER BY tag ASC
                    """,
                    (f"%{search_text.strip()}%",),
                ).fetchall()
            )

        return list(
            self.execute(
                """
                SELECT tag, reason
                FROM filename_excluded_tags
                ORDER BY tag ASC
                """
            ).fetchall()
        )

    def filename_excluded_tag_set(self) -> set[str]:
        rows = self.execute("SELECT tag FROM filename_excluded_tags").fetchall()
        return {str(row["tag"]) for row in rows}

    def add_fetch_excluded_tag(self, tag: str, reason: str = "manual") -> None:
        clean_tag = normalize_tag_token(tag)
        if not clean_tag:
            return
        self.execute(
            """
            INSERT INTO fetch_excluded_tags (tag, reason)
            VALUES (?, ?)
            ON CONFLICT(tag) DO UPDATE SET reason = excluded.reason
            """,
            (clean_tag, reason),
        )
        self.commit()

    def remove_fetch_excluded_tag(self, tag: str) -> None:
        self.execute("DELETE FROM fetch_excluded_tags WHERE tag = ?", (normalize_tag_token(tag),))
        self.commit()

    def fetch_excluded_tag_set(self) -> set[str]:
        rows = self.execute("SELECT tag FROM fetch_excluded_tags").fetchall()
        return {str(row["tag"]) for row in rows}

    def set_tag_alias(self, tag: str, alias: str) -> None:
        clean_tag = tag.strip()
        clean_alias = alias.strip()

        if not clean_tag:
            return

        clean_tag = normalize_tag_token(clean_tag)
        clean_alias = normalize_tag_token(clean_alias)

        if not clean_alias:
            self.execute("DELETE FROM tag_aliases WHERE original_tag = ?", (clean_tag,))
        else:
            self.execute(
                """
                INSERT INTO tag_aliases (original_tag, alias_tag)
                VALUES (?, ?)
                ON CONFLICT(original_tag) DO UPDATE SET alias_tag = excluded.alias_tag
                """,
                (clean_tag, clean_alias),
            )
        # Alias changes can affect chained aliases and grouped LLM tokens, so the
        # cheap and safe move is to rebuild the cache lazily on next use.
        self.execute("DELETE FROM tag_identity_cache")
        self.commit()

    def set_tag_manual_score(self, tag: str, score: float | None) -> None:
        clean_tag = tag.strip()
        if not clean_tag:
            return

        self.execute(
            """
            INSERT INTO tag_scores (tag, manual_score)
            VALUES (?, ?)
            ON CONFLICT(tag) DO UPDATE SET manual_score = excluded.manual_score
            """,
            (clean_tag, score),
        )
        self.commit()

    def set_tag_scoring_flags(
        self,
        tag: str,
        *,
        ignore_category_influence: bool | None = None,
        ignore_recommendation_score: bool | None = None,
        ignore_llm_input: bool | None = None,
    ) -> None:
        clean_tag = normalize_tag_token(str(tag or ""))
        if not clean_tag:
            return

        assignments: list[str] = []
        parameters: list[Any] = [clean_tag]

        if ignore_category_influence is not None:
            assignments.append("ignore_category_influence = ?")
            parameters.append(1 if ignore_category_influence else 0)
        if ignore_recommendation_score is not None:
            assignments.append("ignore_recommendation_score = ?")
            parameters.append(1 if ignore_recommendation_score else 0)
        if ignore_llm_input is not None:
            assignments.append("ignore_llm_input = ?")
            parameters.append(1 if ignore_llm_input else 0)

        if not assignments:
            return

        insert_columns = ["tag"]
        insert_values: list[Any] = [clean_tag]
        update_parts: list[str] = []
        if ignore_category_influence is not None:
            insert_columns.append("ignore_category_influence")
            insert_values.append(1 if ignore_category_influence else 0)
            update_parts.append("ignore_category_influence = excluded.ignore_category_influence")
        if ignore_recommendation_score is not None:
            insert_columns.append("ignore_recommendation_score")
            insert_values.append(1 if ignore_recommendation_score else 0)
            update_parts.append("ignore_recommendation_score = excluded.ignore_recommendation_score")
        if ignore_llm_input is not None:
            insert_columns.append("ignore_llm_input")
            insert_values.append(1 if ignore_llm_input else 0)
            update_parts.append("ignore_llm_input = excluded.ignore_llm_input")

        placeholders = ", ".join("?" for _ in insert_columns)
        self.execute(
            f"""
            INSERT INTO tag_scores ({", ".join(insert_columns)})
            VALUES ({placeholders})
            ON CONFLICT(tag) DO UPDATE SET {", ".join(update_parts)}
            """,
            insert_values,
        )
        self.commit()

    def scoring_flag_tag_set(self, column: str) -> set[str]:
        allowed_columns = {
            "ignore_category_influence",
            "ignore_recommendation_score",
            "ignore_llm_input",
            "scoring_excluded",
        }
        if column not in allowed_columns:
            raise ValueError(f"Unbekannte Scoring-Flag-Spalte: {column}")
        rows = self.execute(
            f"SELECT tag FROM tag_scores WHERE COALESCE({column}, 0) != 0"
        ).fetchall()
        return {str(row["tag"]) for row in rows}

    def category_influence_ignored_tag_set(self) -> set[str]:
        return self.scoring_flag_tag_set("ignore_category_influence")

    def set_tag_scoring_excluded(self, tag: str, excluded: bool = True) -> None:
        clean_tag = tag.strip()
        if not clean_tag:
            return

        self.execute(
            """
            INSERT INTO tag_scores (tag, scoring_excluded)
            VALUES (?, ?)
            ON CONFLICT(tag) DO UPDATE SET scoring_excluded = excluded.scoring_excluded
            """,
            (clean_tag, 1 if excluded else 0),
        )
        self.refresh_tag_statistics_for_tags([clean_tag])
        self.commit()

    def scoring_excluded_tag_set(self) -> set[str]:
        rows = self.execute(
            "SELECT tag FROM tag_scores WHERE COALESCE(scoring_excluded, 0) != 0"
        ).fetchall()
        return {str(row["tag"]) for row in rows}

    def refresh_tag_statistics_for_tags(self, tags: Iterable[str]) -> None:
        clean_tags = sorted({str(tag).strip() for tag in tags if str(tag).strip()})
        if not clean_tags:
            return

        placeholders = ", ".join("?" for _ in clean_tags)
        rows = self.execute(
            f"""
            WITH saved_families AS (
                SELECT DISTINCT COALESCE(parent_id, id) AS family_root
                FROM posts
                WHERE status = 'saved'
            ),
            relevant_posts AS (
                SELECT
                    pt.tag AS tag,
                    p.status AS status,
                    COALESCE(p.parent_id, p.id) AS family_root,
                    pr.stars AS stars
                FROM post_tags pt
                JOIN posts p ON p.id = pt.post_id
                LEFT JOIN post_reviews pr
                    ON pr.post_id = pt.post_id
                   AND pr.stars IS NOT NULL
                WHERE pt.tag IN ({placeholders})
            )
            SELECT
                rp.tag AS tag,
                SUM(CASE WHEN rp.status = 'saved' THEN 1 ELSE 0 END) AS saved_count,
                SUM(CASE WHEN rp.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
                COALESCE(ts.average_rating, AVG(rp.stars)) AS average_rating,
                COALESCE(ts.scoring_excluded, 0) AS scoring_excluded
            FROM relevant_posts rp
            LEFT JOIN saved_families sf ON sf.family_root = rp.family_root
            LEFT JOIN tag_scores ts ON ts.tag = rp.tag
            WHERE rp.status = 'saved' OR sf.family_root IS NULL
            GROUP BY rp.tag
            """,
            clean_tags,
        ).fetchall()

        payload: list[tuple[str, float, int, int, float | None]] = []
        for row in rows:
            saved_count = int(row["saved_count"] or 0)
            rejected_count = int(row["rejected_count"] or 0)
            average_rating = row["average_rating"]
            scoring_excluded = bool(row["scoring_excluded"])
            computed_score = calculate_computed_tag_score(
                average_rating=average_rating,
                saved_count=saved_count,
                rejected_count=rejected_count,
                scoring_excluded=scoring_excluded,
            )
            payload.append((str(row["tag"]), computed_score, saved_count, rejected_count, average_rating))

        if payload:
            self.executemany(
                """
                INSERT INTO tag_scores (tag, computed_score, accepted_count, rejected_count, average_rating)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tag) DO UPDATE SET
                    computed_score = excluded.computed_score,
                    accepted_count = excluded.accepted_count,
                    rejected_count = excluded.rejected_count,
                    average_rating = excluded.average_rating
                """,
                payload,
            )

    def refresh_tag_statistics_for_post(self, post_id: int) -> None:
        rows = self.execute("SELECT tag FROM post_tags WHERE post_id = ?", (post_id,)).fetchall()
        self.refresh_tag_statistics_for_tags([str(row["tag"]) for row in rows])

    def refresh_all_tag_statistics(self) -> None:
        """Refresh cached tag statistics from posts/reviews.

        The viewer computes fresh values on demand anyway. This cache refresh is
        useful for the Tag tab and exports, because stale counters are the sort
        of tiny lie that later turns into a debugging afternoon.
        """
        rows = self.execute(
            """
            SELECT
                pt.tag AS tag,
                SUM(CASE WHEN p.status = 'saved' THEN 1 ELSE 0 END) AS saved_count,
                SUM(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
                COALESCE(ts.average_rating, AVG(pr.stars)) AS average_rating,
                COALESCE(ts.scoring_excluded, 0) AS scoring_excluded
            FROM post_tags pt
            JOIN posts p ON p.id = pt.post_id
            LEFT JOIN tag_scores ts ON ts.tag = pt.tag
            LEFT JOIN post_reviews pr ON pr.post_id = pt.post_id AND pr.stars IS NOT NULL
            WHERE (
                    p.status = 'saved'
                    OR NOT EXISTS (
                        SELECT 1
                        FROM posts family_saved
                        WHERE family_saved.status = 'saved'
                          AND COALESCE(family_saved.parent_id, family_saved.id) =
                              COALESCE(p.parent_id, p.id)
                    )
            )
            GROUP BY pt.tag
            """
        ).fetchall()

        payload: list[tuple[str, float, int, int, float | None]] = []
        for row in rows:
            saved_count = int(row["saved_count"] or 0)
            rejected_count = int(row["rejected_count"] or 0)
            average_rating = row["average_rating"]
            scoring_excluded = bool(row["scoring_excluded"])
            computed_score = calculate_computed_tag_score(
                average_rating=average_rating,
                saved_count=saved_count,
                rejected_count=rejected_count,
                scoring_excluded=scoring_excluded,
            )
            payload.append((
                str(row["tag"]),
                computed_score,
                saved_count,
                rejected_count,
                average_rating,
            ))

        if payload:
            self.executemany(
                """
                INSERT INTO tag_scores (tag, computed_score, accepted_count, rejected_count, average_rating)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tag) DO UPDATE SET
                    computed_score = excluded.computed_score,
                    accepted_count = excluded.accepted_count,
                    rejected_count = excluded.rejected_count,
                    average_rating = excluded.average_rating
                """,
                payload,
            )
            self.commit()

    def suggest_tags(self, prefix: str = "", limit: int = 300) -> list[str]:
        """Return tag suggestions quickly enough that the GUI does not feel cursed.

        This is used for interactive completion. The old version ranked every
        candidate by COUNT(DISTINCT post_id), which is fine for a report and
        absurd for a keypress. This version keeps the useful per-type mix, but
        avoids global grouping/counting while the user is typing.
        """
        clean = str(prefix or "").strip()
        max_limit = max(1, int(limit))

        if max_limit <= 20:
            type_limits = {
                "copyright": max(1, max_limit // 4),
                "character": max(1, max_limit // 4),
                "artist": max(1, max_limit // 5),
                "meta": max(1, max_limit // 10),
                "general": max(1, max_limit),
            }
        else:
            type_limits = {
                "copyright": max(20, max_limit // 5),
                "character": max(20, max_limit // 5),
                "artist": max(15, max_limit // 6),
                "meta": max(10, max_limit // 12),
                "general": max(30, max_limit // 3),
            }

        type_order = ["copyright", "character", "artist", "meta", "general"]
        suggestions: list[str] = []
        seen: set[str] = set()

        def add_rows(rows: list[sqlite3.Row]) -> None:
            for row in rows:
                tag = str(row["tag"] or "").strip()
                if tag and tag not in seen:
                    seen.add(tag)
                    suggestions.append(tag)

        def query_rows(tag_type: str | None, pattern: str, row_limit: int) -> list[sqlite3.Row]:
            if tag_type is None:
                return list(
                    self.execute(
                        """
                        SELECT DISTINCT tag
                        FROM post_tags
                        WHERE tag LIKE ?
                        ORDER BY tag COLLATE NOCASE ASC
                        LIMIT ?
                        """,
                        (pattern, row_limit),
                    ).fetchall()
                )
            return list(
                self.execute(
                    """
                    SELECT DISTINCT tag
                    FROM post_tags
                    WHERE tag_type = ? AND tag LIKE ?
                    ORDER BY tag COLLATE NOCASE ASC
                    LIMIT ?
                    """,
                    (tag_type, pattern, row_limit),
                ).fetchall()
            )

        if clean:
            prefix_pattern = f"{clean}%"
            contains_pattern = f"%{clean}%"
        else:
            prefix_pattern = "%"
            contains_pattern = "%"

        for tag_type in type_order:
            if len(suggestions) >= max_limit:
                break
            per_type_limit = min(type_limits[tag_type], max_limit - len(suggestions))
            if per_type_limit <= 0:
                continue
            add_rows(query_rows(tag_type, prefix_pattern, per_type_limit))

        # Prefix hits are cheap and usually what a completion field should do.
        # If the user types the middle of a tag, do a smaller contains fallback.
        # Humanity survives both cases, barely.
        if clean and len(suggestions) < max_limit:
            for tag_type in type_order:
                if len(suggestions) >= max_limit:
                    break
                per_type_limit = min(max(5, type_limits[tag_type] // 2), max_limit - len(suggestions))
                add_rows(query_rows(tag_type, contains_pattern, per_type_limit))

        remaining = max_limit - len(suggestions)
        if remaining > 0:
            add_rows(query_rows(None, prefix_pattern, remaining))

        return suggestions[:max_limit]
