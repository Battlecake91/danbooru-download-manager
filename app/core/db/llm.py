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


class DatabaseLlmMixin:
    """LLM export, anonymization, preference summaries, and stored decisions."""

    def ensure_llm_hash_salt(self) -> str:
        """Return the local salted-hash secret, creating one if missing.

        This salt stays local in SQLite/app_settings. Without it, hashed tags
        would be a dictionary attack with extra steps, and humanity has already
        invented enough fake privacy.
        """
        row = self.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("llm.hash_salt",),
        ).fetchone()
        if row is not None and row["value"]:
            try:
                loaded = json.loads(str(row["value"]))
                if isinstance(loaded, str) and loaded.strip():
                    return loaded.strip()
            except Exception:
                raw = str(row["value"]).strip()
                if raw:
                    return raw

        salt = secrets.token_hex(32)
        self.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            ("llm.hash_salt", json.dumps(salt)),
        )
        return salt

    def list_tag_alias_map(self) -> dict[str, str]:
        rows = self.execute(
            """
            SELECT original_tag, alias_tag
            FROM tag_aliases
            WHERE TRIM(COALESCE(alias_tag, '')) != ''
            """
        ).fetchall()
        result: dict[str, str] = {}
        for row in rows:
            original = normalize_tag_token(str(row["original_tag"] or ""))
            alias = normalize_tag_token(str(row["alias_tag"] or ""))
            if original and alias:
                result[original] = alias
        return result

    def get_llm_tag_export_settings(self) -> dict[str, Any]:
        def setting(key: str, default: Any) -> Any:
            row = self.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
            if row is None:
                return default
            try:
                return json.loads(str(row["value"]))
            except Exception:
                return row["value"]

        mode = str(setting("llm.tag_export_mode", "hashed_alias") or "hashed_alias").lower()
        if mode not in {"original", "alias", "hashed_alias"}:
            mode = "hashed_alias"
        prefix = str(setting("llm.hash_prefix", "tag_") or "tag_")
        try:
            length = int(setting("llm.hash_length", 12))
        except Exception:
            length = 12
        return {
            "mode": mode,
            "prefix": prefix,
            "hash_length": max(4, min(64, length)),
            "salt": self.ensure_llm_hash_salt(),
        }

    def build_tag_identities(self, tags: Iterable[str]) -> dict[str, dict[str, str]]:
        aliases = self.list_tag_alias_map()
        settings = self.get_llm_tag_export_settings()
        clean_tags = sorted({normalize_tag_token(str(tag)) for tag in tags if normalize_tag_token(str(tag))})
        result: dict[str, dict[str, str]] = {}
        cache_rows: list[tuple[str, str, str]] = []

        for tag in clean_tags:
            identity = build_tag_identity(
                tag,
                aliases=aliases,
                salt=str(settings["salt"]),
                prefix=str(settings["prefix"]),
                length=int(settings["hash_length"]),
            )
            result[tag] = {
                "original_tag": identity.original_tag,
                "canonical_tag": identity.canonical_tag,
                "llm_token": identity.llm_token,
            }
            cache_rows.append((identity.original_tag, identity.canonical_tag, identity.llm_token))

        if cache_rows:
            self.executemany(
                """
                INSERT INTO tag_identity_cache (original_tag, canonical_tag, llm_token, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(original_tag) DO UPDATE SET
                    canonical_tag = excluded.canonical_tag,
                    llm_token = excluded.llm_token,
                    updated_at = CURRENT_TIMESTAMP
                """,
                cache_rows,
            )
        return result

    def canonical_tag_for_tag(self, tag: str) -> str:
        clean_tag = normalize_tag_token(tag)
        if not clean_tag:
            return ""
        aliases = self.list_tag_alias_map()
        return canonicalize_tag(clean_tag, aliases)

    def llm_export_value_for_tag(self, tag: str, mode: str | None = None) -> str:
        clean_tag = normalize_tag_token(tag)
        if not clean_tag:
            return ""
        identity = self.build_tag_identities([clean_tag]).get(clean_tag)
        if not identity:
            return clean_tag
        export_mode = (mode or self.get_llm_tag_export_settings()["mode"]).lower()
        if export_mode == "original":
            return identity["original_tag"]
        if export_mode == "alias":
            return identity["canonical_tag"]
        return identity["llm_token"]

    def build_llm_tag_export(self, tags: Iterable[str], mode: str | None = None) -> list[str]:
        clean_tags = sorted({normalize_tag_token(str(tag)) for tag in tags if normalize_tag_token(str(tag))})
        identities = self.build_tag_identities(clean_tags)
        export_mode = (mode or self.get_llm_tag_export_settings()["mode"]).lower()
        exported: list[str] = []
        seen: set[str] = set()
        for tag in clean_tags:
            identity = identities.get(tag)
            if not identity:
                continue
            if export_mode == "original":
                value = identity["original_tag"]
            elif export_mode == "alias":
                value = identity["canonical_tag"]
            else:
                value = identity["llm_token"]
            if value and value not in seen:
                exported.append(value)
                seen.add(value)
        return exported

    def get_llm_category_export_settings(self) -> dict[str, Any]:
        def setting(key: str, default: Any) -> Any:
            row = self.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
            if row is None:
                return default
            try:
                return json.loads(str(row["value"]))
            except Exception:
                return row["value"]

        mode = str(setting("llm.category_export_mode", "hashed") or "hashed").lower()
        if mode not in {"original", "hashed"}:
            mode = "hashed"
        prefix = str(setting("llm.category_hash_prefix", "cat_") or "cat_")
        try:
            length = int(setting("llm.category_hash_length", setting("llm.hash_length", 12)))
        except Exception:
            length = 12
        return {
            "mode": mode,
            "prefix": prefix,
            "hash_length": max(4, min(64, length)),
            "salt": self.ensure_llm_hash_salt(),
        }

    def llm_export_value_for_category(self, category_name: str | None, mode: str | None = None) -> str | None:
        raw_name = str(category_name or "").strip()
        if not raw_name:
            return None
        settings = self.get_llm_category_export_settings()
        export_mode = (mode or settings["mode"]).lower()
        if export_mode == "original":
            return raw_name
        normalized = normalize_tag_token(raw_name)
        return salted_tag_hash(
            f"category_{normalized}",
            salt=str(settings["salt"]),
            prefix=str(settings["prefix"]),
            length=int(settings["hash_length"]),
        )

    def build_llm_category_export(self, category_names: Iterable[str], mode: str | None = None) -> list[str]:
        exported: list[str] = []
        seen: set[str] = set()
        for name in category_names:
            value = self.llm_export_value_for_category(str(name), mode=mode)
            if value and value not in seen:
                exported.append(value)
                seen.add(value)
        return exported

    def llm_category_name_for_export(self, exported_category: str | None) -> str | None:
        value = str(exported_category or "").strip()
        if not value:
            return None
        category_names = [str(name) for name in self.list_category_names()]
        if value in category_names:
            return value
        for name in category_names:
            if self.llm_export_value_for_category(name) == value:
                return name
        return None

    def fetch_llm_preference_summary(self) -> dict[str, Any]:
        """Return a small aggregate summary for LLM preference context."""
        row = self.execute(
            """
            SELECT
                COUNT(*) AS total_posts,
                SUM(CASE WHEN status = 'saved' THEN 1 ELSE 0 END) AS saved_posts,
                SUM(CASE
                    WHEN status = 'rejected'
                     AND NOT EXISTS (
                        SELECT 1 FROM posts family_saved
                        WHERE family_saved.status = 'saved'
                          AND COALESCE(family_saved.parent_id, family_saved.id) =
                              COALESCE(p.parent_id, p.id)
                     )
                    THEN 1 ELSE 0
                END) AS rejected_posts,
                SUM(CASE WHEN status = 'already_known' THEN 1 ELSE 0 END) AS already_known_posts,
                AVG(CASE
                    WHEN pr.stars IS NOT NULL
                     AND (
                        p.status = 'saved'
                        OR NOT EXISTS (
                            SELECT 1 FROM posts family_saved
                            WHERE family_saved.status = 'saved'
                              AND COALESCE(family_saved.parent_id, family_saved.id) =
                                  COALESCE(p.parent_id, p.id)
                        )
                     )
                    THEN pr.stars
                END) AS avg_personal_rating,
                SUM(CASE
                    WHEN pr.stars IS NOT NULL
                     AND (
                        p.status = 'saved'
                        OR NOT EXISTS (
                            SELECT 1 FROM posts family_saved
                            WHERE family_saved.status = 'saved'
                              AND COALESCE(family_saved.parent_id, family_saved.id) =
                                  COALESCE(p.parent_id, p.id)
                        )
                     )
                    THEN 1 ELSE 0
                END) AS rated_posts
            FROM posts p
            LEFT JOIN post_reviews pr ON pr.post_id = p.id
            """
        ).fetchone()
        if row is None:
            return {}
        return {
            "total_posts": int(row["total_posts"] or 0),
            "saved_posts": int(row["saved_posts"] or 0),
            "rejected_posts": int(row["rejected_posts"] or 0),
            "already_known_posts": int(row["already_known_posts"] or 0),
            "rated_posts": int(row["rated_posts"] or 0),
            "avg_personal_rating": round(float(row["avg_personal_rating"]), 2)
            if row["avg_personal_rating"] is not None else None,
        }

    def fetch_llm_tag_preferences(self, current_tags: Iterable[str] | None = None, limit: int = 80) -> list[dict[str, Any]]:
        """Return compact tag preference hints for the LLM payload.

        The result combines strongest positive/negative historical tag signals
        with any tags from the current batch that already have local history.
        This avoids sending the whole tag universe, because apparently even LLMs
        do not need a phone book to decide whether fox ears are relevant.
        """
        clean_current = sorted({normalize_tag_token(str(tag)) for tag in (current_tags or []) if normalize_tag_token(str(tag))})
        max_limit = max(0, int(limit or 0))
        if max_limit <= 0:
            return []

        def rows_to_items(rows: list[sqlite3.Row], in_current: bool = False) -> list[dict[str, Any]]:
            result: list[dict[str, Any]] = []
            for row in rows:
                tag = normalize_tag_token(str(row["tag"] or ""))
                if not tag:
                    continue
                accepted = int(row["accepted_count"] or 0)
                rejected = int(row["rejected_count"] or 0)
                computed = float(row["computed_score"] or 0.0)
                manual = row["manual_score"]
                average = row["average_rating"]
                if computed > 0 or (manual is not None and float(manual or 0) > 0) or accepted > rejected:
                    signal = "positive"
                elif computed < 0 or (manual is not None and float(manual or 0) < 0) or rejected > accepted:
                    signal = "negative"
                else:
                    signal = "neutral"
                result.append(
                    {
                        "tag": tag,
                        "computed_score": round(computed, 2),
                        "manual_score": round(float(manual), 2) if manual is not None else None,
                        "accepted_count": accepted,
                        "rejected_count": rejected,
                        "average_rating": round(float(average), 2) if average is not None else None,
                        "signal": signal,
                        "in_current_batch": in_current or tag in clean_current,
                    }
                )
            return result

        items_by_tag: dict[str, dict[str, Any]] = {}

        if clean_current:
            placeholders = ", ".join("?" for _ in clean_current)
            current_rows = self.execute(
                f"""
                SELECT tag, manual_score, computed_score, accepted_count, rejected_count, average_rating
                FROM tag_scores
                WHERE tag IN ({placeholders})
                  AND COALESCE(ignore_llm_input, 0) = 0
                  AND (
                        COALESCE(manual_score, 0) != 0
                     OR COALESCE(computed_score, 0) != 0
                     OR COALESCE(accepted_count, 0) != 0
                     OR COALESCE(rejected_count, 0) != 0
                     OR average_rating IS NOT NULL
                  )
                """,
                clean_current,
            ).fetchall()
            for item in rows_to_items(current_rows, in_current=True):
                items_by_tag[item["tag"]] = item

        per_side = max(10, max_limit // 2)
        positive_rows = self.execute(
            """
            SELECT tag, manual_score, computed_score, accepted_count, rejected_count, average_rating
            FROM tag_scores
            WHERE COALESCE(ignore_llm_input, 0) = 0
              AND COALESCE(scoring_excluded, 0) = 0
              AND (
                    COALESCE(manual_score, 0) > 0
                 OR COALESCE(computed_score, 0) > 0
                 OR COALESCE(average_rating, 0) >= 7
                 OR COALESCE(accepted_count, 0) > COALESCE(rejected_count, 0)
              )
            ORDER BY
                ABS(COALESCE(manual_score, computed_score, 0)) DESC,
                COALESCE(accepted_count, 0) DESC,
                tag COLLATE NOCASE ASC
            LIMIT ?
            """,
            (per_side,),
        ).fetchall()
        negative_rows = self.execute(
            """
            SELECT tag, manual_score, computed_score, accepted_count, rejected_count, average_rating
            FROM tag_scores
            WHERE COALESCE(ignore_llm_input, 0) = 0
              AND COALESCE(scoring_excluded, 0) = 0
              AND (
                    COALESCE(manual_score, 0) < 0
                 OR COALESCE(computed_score, 0) < 0
                 OR (average_rating IS NOT NULL AND average_rating <= 3)
                 OR COALESCE(rejected_count, 0) > COALESCE(accepted_count, 0)
              )
            ORDER BY
                ABS(COALESCE(manual_score, computed_score, 0)) DESC,
                COALESCE(rejected_count, 0) DESC,
                tag COLLATE NOCASE ASC
            LIMIT ?
            """,
            (per_side,),
        ).fetchall()

        for item in rows_to_items(positive_rows):
            items_by_tag.setdefault(item["tag"], item)
        for item in rows_to_items(negative_rows):
            items_by_tag.setdefault(item["tag"], item)

        def sort_key(item: dict[str, Any]) -> tuple[int, float, int, str]:
            score = item.get("manual_score") if item.get("manual_score") is not None else item.get("computed_score")
            try:
                strength = abs(float(score or 0.0))
            except Exception:
                strength = 0.0
            count = int(item.get("accepted_count") or 0) + int(item.get("rejected_count") or 0)
            return (0 if item.get("in_current_batch") else 1, -strength, -count, str(item.get("tag") or ""))

        items = sorted(items_by_tag.values(), key=sort_key)
        return items[:max_limit]

    def fetch_llm_category_profiles(self, max_tags_per_category: int = 10) -> list[dict[str, Any]]:
        max_tags = max(1, int(max_tags_per_category or 10))
        categories = self.execute(
            """
            SELECT
                c.id,
                c.name,
                COUNT(DISTINCT p.id) AS saved_posts,
                AVG(pr.stars) AS average_rating
            FROM categories c
            LEFT JOIN post_categories pc ON pc.category_id = c.id
            LEFT JOIN posts p ON p.id = pc.post_id AND p.status = 'saved'
            LEFT JOIN post_reviews pr ON pr.post_id = p.id AND pr.stars IS NOT NULL
            GROUP BY c.id, c.name
            HAVING saved_posts > 0
            ORDER BY c.sort_order ASC, c.name ASC
            """
        ).fetchall()

        result: list[dict[str, Any]] = []
        for category in categories:
            category_id = int(category["id"])
            positive_rows = self.execute(
                """
                SELECT pt.tag, COUNT(*) AS use_count, COALESCE(ts.computed_score, 0) AS score
                FROM post_categories pc
                JOIN posts p ON p.id = pc.post_id AND p.status = 'saved'
                JOIN post_tags pt ON pt.post_id = p.id
                LEFT JOIN tag_scores ts ON ts.tag = pt.tag
                WHERE pc.category_id = ?
                  AND COALESCE(ts.ignore_llm_input, 0) = 0
                  AND COALESCE(ts.scoring_excluded, 0) = 0
                GROUP BY pt.tag
                ORDER BY
                    COALESCE(ts.computed_score, 0) DESC,
                    use_count DESC,
                    pt.tag COLLATE NOCASE ASC
                LIMIT ?
                """,
                (category_id, max_tags),
            ).fetchall()
            negative_rows = self.execute(
                """
                SELECT ts.tag, COALESCE(ts.computed_score, 0) AS score, COALESCE(ts.rejected_count, 0) AS rejected_count
                FROM tag_scores ts
                WHERE COALESCE(ts.ignore_llm_input, 0) = 0
                  AND COALESCE(ts.scoring_excluded, 0) = 0
                  AND (
                        COALESCE(ts.computed_score, 0) < 0
                     OR COALESCE(ts.rejected_count, 0) > COALESCE(ts.accepted_count, 0)
                  )
                ORDER BY ABS(COALESCE(ts.computed_score, 0)) DESC, rejected_count DESC, ts.tag COLLATE NOCASE ASC
                LIMIT ?
                """,
                (max(3, max_tags // 2),),
            ).fetchall()
            result.append(
                {
                    "category": str(category["name"]),
                    "saved_posts": int(category["saved_posts"] or 0),
                    "average_rating": round(float(category["average_rating"]), 2)
                    if category["average_rating"] is not None else None,
                    "top_positive_tags": [str(row["tag"]) for row in positive_rows],
                    "top_negative_tags": [str(row["tag"]) for row in negative_rows],
                }
            )
        return result

    def fetch_llm_examples(
        self,
        *,
        positive_limit: int = 8,
        negative_limit: int = 8,
        category_limit: int = 3,
        max_tags: int = 80,
    ) -> dict[str, list[dict[str, Any]]]:
        examples: dict[str, list[dict[str, Any]]] = {}

        if positive_limit > 0:
            examples["liked"] = self._fetch_llm_example_rows(
                """
                WHERE p.status = 'saved'
                   OR (
                        COALESCE(pr.stars, 0) >= 8
                        AND NOT EXISTS (
                            SELECT 1 FROM posts family_saved
                            WHERE family_saved.status = 'saved'
                              AND COALESCE(family_saved.parent_id, family_saved.id) =
                                  COALESCE(p.parent_id, p.id)
                        )
                   )
                ORDER BY COALESCE(pr.stars, 0) DESC, p.saved_at DESC, p.id DESC
                LIMIT ?
                """,
                (int(positive_limit),),
                max_tags=max_tags,
            )

        if negative_limit > 0:
            examples["rejected"] = self._fetch_llm_example_rows(
                """
                WHERE (
                        p.status = 'rejected'
                        OR (pr.stars IS NOT NULL AND pr.stars <= 2)
                      )
                  AND NOT EXISTS (
                        SELECT 1 FROM posts family_saved
                        WHERE family_saved.status = 'saved'
                          AND COALESCE(family_saved.parent_id, family_saved.id) =
                              COALESCE(p.parent_id, p.id)
                  )
                ORDER BY
                    CASE WHEN p.status = 'rejected' THEN 0 ELSE 1 END,
                    COALESCE(pr.stars, 99) ASC,
                    p.rejected_at DESC,
                    p.id DESC
                LIMIT ?
                """,
                (int(negative_limit),),
                max_tags=max_tags,
            )

        if category_limit > 0:
            category_rows = self.execute(
                """
                SELECT id, name
                FROM categories
                ORDER BY sort_order ASC, name ASC
                """
            ).fetchall()
            by_category: list[dict[str, Any]] = []
            for category in category_rows:
                rows = self._fetch_llm_example_rows(
                    """
                    JOIN post_categories pc_filter ON pc_filter.post_id = p.id
                    WHERE pc_filter.category_id = ?
                      AND p.status = 'saved'
                    ORDER BY COALESCE(pr.stars, 0) DESC, p.saved_at DESC, p.id DESC
                    LIMIT ?
                    """,
                    (int(category["id"]), int(category_limit)),
                    max_tags=max_tags,
                )
                for row in rows:
                    row["category_profile"] = str(category["name"])
                by_category.extend(rows)
            examples["by_category"] = by_category

        return {key: value for key, value in examples.items() if value}

    def _fetch_llm_example_rows(self, where_and_order_sql: str, parameters: Iterable[Any], *, max_tags: int) -> list[dict[str, Any]]:
        rows = self.execute(
            f"""
            SELECT
                p.id,
                p.status,
                p.local_score,
                pr.stars AS personal_rating,
                c.name AS category_name
            FROM posts p
            LEFT JOIN post_reviews pr ON pr.post_id = p.id
            LEFT JOIN post_categories pc ON pc.post_id = p.id
            LEFT JOIN categories c ON c.id = pc.category_id
            {where_and_order_sql}
            """,
            parameters,
        ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            tags = self.execute(
                """
                SELECT pt.tag
                FROM post_tags pt
                LEFT JOIN tag_scores ts ON ts.tag = pt.tag
                WHERE pt.post_id = ?
                  AND COALESCE(ts.ignore_llm_input, 0) = 0
                ORDER BY
                    CASE pt.tag_type
                        WHEN 'artist' THEN 0
                        WHEN 'character' THEN 1
                        WHEN 'copyright' THEN 2
                        WHEN 'meta' THEN 3
                        ELSE 4
                    END,
                    pt.tag COLLATE NOCASE ASC
                LIMIT ?
                """,
                (int(row["id"]), max(1, int(max_tags))),
            ).fetchall()
            result.append(
                {
                    "post_id": int(row["id"]),
                    "status": row["status"],
                    "personal_rating": row["personal_rating"],
                    "category": row["category_name"],
                    "local_score": row["local_score"],
                    "tags": [str(tag_row["tag"]) for tag_row in tags],
                }
            )
        return result

    def store_llm_decisions(self, decisions: Iterable[dict[str, Any]], *, model: str | None = None) -> int:
        """Persist LLM decisions for posts without changing human workflow status.

        The LLM may suggest keep/reject/category, but this stores it as metadata.
        Automatic status changes can wait until we have seen it behave like less
        of a confident raccoon in a lab coat.
        """
        updated = 0
        for item in decisions:
            try:
                post_id = int(item.get("post_id"))
            except Exception:
                continue
            decision = str(item.get("decision") or "").strip() or None
            category = item.get("category")
            category_text = str(category).strip() if category not in (None, "") else None
            reason = str(item.get("reason") or "").strip() or None
            raw_score = item.get("score")
            try:
                score = float(raw_score) if raw_score is not None else None
            except Exception:
                score = None

            self.execute(
                """
                UPDATE posts
                SET llm_score = ?,
                    llm_decision = ?,
                    llm_category = ?,
                    llm_reason = ?,
                    llm_model = ?,
                    llm_reviewed_at = CURRENT_TIMESTAMP,
                    final_score = COALESCE(?, final_score)
                WHERE id = ?
                """,
                (score, decision, category_text, reason, model, score, post_id),
            )
            updated += 1
        if updated:
            self.commit()
        return updated

    def filter_post_ids_for_llm(
        self,
        post_ids: Iterable[int],
        *,
        statuses: Iterable[str] = ("new", "potential"),
        skip_already_scored: bool = True,
    ) -> list[int]:
        clean_ids: list[int] = []
        seen: set[int] = set()
        for raw_id in post_ids:
            try:
                post_id = int(raw_id)
            except Exception:
                continue
            if post_id and post_id not in seen:
                clean_ids.append(post_id)
                seen.add(post_id)
        if not clean_ids:
            return []

        status_list = [str(status) for status in statuses if str(status).strip()]
        placeholders = ",".join("?" for _ in clean_ids)
        parameters: list[Any] = list(clean_ids)
        where_parts = [f"id IN ({placeholders})"]
        if status_list:
            status_placeholders = ",".join("?" for _ in status_list)
            where_parts.append(f"status IN ({status_placeholders})")
            parameters.extend(status_list)
        if skip_already_scored:
            where_parts.append("llm_reviewed_at IS NULL")

        rows = self.execute(
            f"SELECT id FROM posts WHERE {' AND '.join(where_parts)} ORDER BY id DESC",
            parameters,
        ).fetchall()
        allowed = {int(row["id"]) for row in rows}
        return [post_id for post_id in clean_ids if post_id in allowed]
