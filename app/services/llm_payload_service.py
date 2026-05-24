from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.core.database import Database
from app.core.recommendation_engine import RecommendationEngine
from app.core.tag_privacy import normalize_tag_token


@dataclass(frozen=True)
class LLMPayloadPost:
    post_id: int
    rating: str | None
    danbooru_score: int | None
    status: str | None
    personal_rating: int | None
    local_score: float | None
    current_category: str | None
    raw_tags: list[str]
    tags: list[str]


class LLMPayloadService:
    """Build provider-neutral LLM input payloads.

    The payload now includes a compact preference context from local history.
    Without that, the model only gets the current tags and confidently guesses.
    Computers do love pretending that a list of words is a personality profile.
    """

    def __init__(self, config: dict[str, Any], db: Database) -> None:
        self.config = config
        self.db = db
        self.recommendation_engine = RecommendationEngine(db)

    def build_payload_batches(self, post_ids: Iterable[int]) -> list[dict[str, Any]]:
        ids = self._dedupe_post_ids(post_ids)
        if not ids:
            raise ValueError("Keine Posts ausgewaehlt.")

        llm_config = self.config.get("llm", {}) or {}
        max_posts = max(1, int(llm_config.get("max_posts_per_request", 20) or 20))
        batches: list[dict[str, Any]] = []
        chunks = [ids[index:index + max_posts] for index in range(0, len(ids), max_posts)]
        for index, chunk in enumerate(chunks, start=1):
            payload = self.build_payload_for_posts(chunk)
            payload["batch"] = {
                "index": index,
                "total": len(chunks),
                "posts_in_batch": len(chunk),
                "posts_total": len(ids),
            }
            batches.append(payload)
        return batches

    def _dedupe_post_ids(self, post_ids: Iterable[int]) -> list[int]:
        ids = []
        seen: set[int] = set()
        for raw_id in post_ids:
            post_id = int(raw_id)
            if post_id not in seen:
                ids.append(post_id)
                seen.add(post_id)
        return ids

    def build_payload_for_posts(self, post_ids: Iterable[int]) -> dict[str, Any]:
        ids = self._dedupe_post_ids(post_ids)

        if not ids:
            raise ValueError("Keine Posts ausgewaehlt.")

        llm_config = self.config.get("llm", {}) or {}
        max_posts = max(1, int(llm_config.get("max_posts_per_request", 20) or 20))
        max_tags = max(1, int(llm_config.get("max_tags_per_post", 80) or 80))
        ids = ids[:max_posts]

        posts = [self._load_post(post_id, max_tags=max_tags) for post_id in ids]
        raw_categories = self._load_category_names()
        categories = self._export_categories(raw_categories)
        preference_context = self._build_preference_context(posts, llm_config)

        payload: dict[str, Any] = {
            "task": "danbooru_post_preselection",
            "schema_version": 3,
            "instructions": self._instructions(llm_config),
            "expected_response": {
                "posts": [
                    {
                        "post_id": "integer",
                        "score": "number from -100 to 100",
                        "decision": "reject|maybe|keep|save_candidate",
                        "category": "category id from config.available_categories or null",
                        "reason": "short German reason",
                    }
                ]
            },
            "config": {
                "provider_enabled": bool(llm_config.get("enabled", False)),
                "backend": str(llm_config.get("backend", "none")),
                "tag_export_mode": str(llm_config.get("tag_export_mode", "hashed_alias")),
                "category_export_mode": str(llm_config.get("category_export_mode", "hashed")),
                "include_tag_legend": bool(llm_config.get("include_tag_legend", False)),
                "include_category_legend": bool(llm_config.get("include_category_legend", False)),
                "include_preference_context": bool(llm_config.get("include_preference_context", True)),
                "available_categories": categories,
            },
            "posts": [self._post_to_payload(post) for post in posts],
        }

        if bool(llm_config.get("include_category_legend", False)):
            payload["config"]["category_legend"] = {
                self._export_category(name): name
                for name in raw_categories
                if self._export_category(name)
            }

        if preference_context:
            payload["preference_context"] = preference_context

        return payload

    def _instructions(self, llm_config: dict[str, Any]) -> str:
        custom_prompt = str(llm_config.get("system_prompt", "") or "").strip()
        if custom_prompt:
            return custom_prompt
        return (
            "Bewerte Danbooru-Posts anhand der Tags, Metadaten und des preference_context. "
            "Der preference_context enthaelt kompakte historische Praeferenzen mit confidence/conflict-Hinweisen, "
            "Kategorieprofile und gekuerzte Beispiele. Kategorien koennen anonymisierte IDs sein; "
            "verwende in der Antwort nur category-Werte aus config.available_categories oder null. "
            "Nutze lokale Scores als Hinweis, aber nicht blind. Behandle mixed/conflict-Signale vorsichtig "
            "und bevorzuge klare Keep/Reject-Entscheidungen; maybe nur bei echter Unsicherheit. "
            "Gib pro Post eine kurze JSON-taugliche Entscheidung zurueck."
        )

    def _load_post(self, post_id: int, max_tags: int) -> LLMPayloadPost:
        post_row = self.db.execute(
            """
            SELECT
                p.id,
                p.rating,
                p.score,
                p.status,
                p.local_score,
                p.llm_score,
                pr.stars AS personal_rating,
                c.name AS category_name
            FROM posts p
            LEFT JOIN post_reviews pr ON pr.post_id = p.id
            LEFT JOIN post_categories pc ON pc.post_id = p.id
            LEFT JOIN categories c ON c.id = pc.category_id
            WHERE p.id = ?
            ORDER BY CASE pc.source WHEN 'manual' THEN 0 ELSE 1 END, c.sort_order, c.name
            LIMIT 1
            """,
            (post_id,),
        ).fetchone()
        if post_row is None:
            raise ValueError(f"Post {post_id} ist nicht in der lokalen Datenbank.")

        tag_rows = self.db.execute(
            """
            SELECT pt.tag, pt.tag_type, COALESCE(ts.ignore_llm_input, 0) AS ignore_llm_input
            FROM post_tags pt
            LEFT JOIN tag_scores ts ON ts.tag = pt.tag
            WHERE pt.post_id = ?
            ORDER BY
                CASE pt.tag_type
                    WHEN 'artist' THEN 0
                    WHEN 'character' THEN 1
                    WHEN 'copyright' THEN 2
                    WHEN 'meta' THEN 3
                    ELSE 4
                END,
                pt.tag COLLATE NOCASE ASC
            """,
            (post_id,),
        ).fetchall()

        clean_tags: list[str] = []
        for row in tag_rows:
            if bool(row["ignore_llm_input"]):
                continue
            tag = normalize_tag_token(str(row["tag"] or ""))
            if tag:
                clean_tags.append(tag)

        exported_tags = self.db.build_llm_tag_export(clean_tags)[:max_tags]

        return LLMPayloadPost(
            post_id=int(post_row["id"]),
            rating=post_row["rating"],
            danbooru_score=post_row["score"],
            status=post_row["status"],
            personal_rating=post_row["personal_rating"],
            local_score=post_row["local_score"],
            current_category=post_row["category_name"],
            raw_tags=clean_tags,
            tags=exported_tags,
        )

    def _post_to_payload(self, post: LLMPayloadPost) -> dict[str, Any]:
        # Score raw tags, not exported hashed tokens. Otherwise the local scorer
        # stares at tag_abcdef and finds exactly nothing. Shocking, I know.
        recommendation = self.recommendation_engine.score_tags(post.raw_tags)
        return {
            "post_id": post.post_id,
            "rating": post.rating,
            "danbooru_score": post.danbooru_score,
            "status": post.status,
            "personal_rating": post.personal_rating,
            "local_score": post.local_score,
            "current_category": self._export_category(post.current_category),
            "local_recommendation_score": recommendation.score,
            "local_positive_signals": self._export_signal_tags(recommendation.positive),
            "local_negative_signals": self._export_signal_tags(recommendation.negative),
            "tags": post.tags,
        }

    def _export_signal_tags(self, signals: list[str]) -> list[str]:
        exported: list[str] = []
        for signal in signals:
            parts = signal.rsplit(" ", 1)
            if not parts:
                continue
            tag = parts[0]
            value = parts[1] if len(parts) > 1 else ""
            exported_tag = self.db.llm_export_value_for_tag(tag)
            exported.append(f"{exported_tag} {value}".strip())
        return exported

    def _build_preference_context(self, posts: list[LLMPayloadPost], llm_config: dict[str, Any]) -> dict[str, Any] | None:
        if not bool(llm_config.get("include_preference_context", True)):
            return None

        current_raw_tags = sorted({tag for post in posts for tag in post.raw_tags})
        max_pref_tags = max(0, int(llm_config.get("max_preference_tags", 80) or 80))
        max_positive_examples = max(0, int(llm_config.get("max_positive_examples", 8) or 8))
        max_negative_examples = max(0, int(llm_config.get("max_negative_examples", 8) or 8))
        max_category_examples = max(0, int(llm_config.get("max_category_examples", 3) or 3))
        max_example_tags = max(1, min(80, int(llm_config.get("max_example_tags", 30) or 30)))

        context: dict[str, Any] = {
            "summary": self.db.fetch_llm_preference_summary(),
        }

        known_preferences = self.db.fetch_llm_tag_preferences(
            current_tags=current_raw_tags,
            limit=max_pref_tags,
        )
        preference_payload: list[dict[str, Any]] = []
        if known_preferences:
            preference_payload = [self._tag_preference_to_payload(item) for item in known_preferences]
            preference_payload = [item for item in preference_payload if self._keep_preference_payload_item(item)]
            if preference_payload:
                context["known_tag_preferences"] = preference_payload

        raw_preference_by_tag = {str(item.get("tag") or ""): item for item in known_preferences}

        category_profiles = self.db.fetch_llm_category_profiles(
            max_tags_per_category=max(4, min(20, max_pref_tags // 4 if max_pref_tags else 10)),
        )
        category_payload: list[dict[str, Any]] = []
        category_profile_tags: set[str] = set()
        if category_profiles:
            for item in category_profiles:
                category_profile_tags.update(str(tag) for tag in item.get("top_positive_tags", []) if tag)
                category_profile_tags.update(str(tag) for tag in item.get("top_negative_tags", []) if tag)
                category_payload.append(self._category_profile_to_payload(item))
            if category_payload:
                context["category_profiles"] = category_payload

        examples = self.db.fetch_llm_examples(
            positive_limit=max_positive_examples,
            negative_limit=max_negative_examples,
            category_limit=max_category_examples,
            # Fetch a little more than we finally emit so the compactor can pick relevant tags.
            max_tags=max(80, max_example_tags * 3),
        )
        if examples:
            context["examples"] = self._examples_to_payload(
                examples,
                max_tags=max_example_tags,
                current_tags=set(current_raw_tags),
                preference_by_tag=raw_preference_by_tag,
                category_profile_tags=category_profile_tags,
            )

        context["payload_stats"] = {
            "preference_tags_total": len(preference_payload),
            "category_profiles_total": len(category_payload),
            "example_groups_total": len(context.get("examples", {}) or {}),
            "example_tags_max": max_example_tags,
            "compacted": True,
        }

        # Remove empty sections, but keep summary. The payload should be honest,
        # not a JSON-shaped cupboard full of empty boxes.
        compact = {key: value for key, value in context.items() if value not in ({}, [], None)}
        return compact or None

    def _tag_preference_to_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        tag = str(item.get("tag") or "")
        exported_tag = self.db.llm_export_value_for_tag(tag)
        computed = self._safe_float(item.get("computed_score"))
        manual = self._safe_float(item.get("manual_score"))
        accepted = int(item.get("accepted_count") or 0)
        rejected = int(item.get("rejected_count") or 0)
        average = self._safe_float(item.get("average_rating"))
        confidence, conflict = self._preference_confidence(
            computed_score=computed,
            manual_score=manual,
            accepted_count=accepted,
            rejected_count=rejected,
            average_rating=average,
        )
        signal = self._preference_signal(
            computed_score=computed,
            manual_score=manual,
            accepted_count=accepted,
            rejected_count=rejected,
            average_rating=average,
        )
        payload = {
            "tag": exported_tag,
            "computed_score": round(computed, 2) if computed is not None else None,
            "manual_score": round(manual, 2) if manual is not None else None,
            "accepted_count": accepted,
            "rejected_count": rejected,
            "avg_personal_rating": round(average, 2) if average is not None else None,
            "signal": signal,
            "confidence": confidence,
            "in_current_batch": bool(item.get("in_current_batch")),
        }
        if conflict:
            payload["conflict"] = conflict
        if bool(self.config.get("llm", {}).get("include_tag_legend", False)):
            payload["original_tag"] = tag
            payload["canonical_tag"] = self.db.canonical_tag_for_tag(tag)
        return payload

    def _keep_preference_payload_item(self, item: dict[str, Any]) -> bool:
        manual = self._safe_float(item.get("manual_score")) or 0.0
        computed = self._safe_float(item.get("computed_score")) or 0.0
        count = int(item.get("accepted_count") or 0) + int(item.get("rejected_count") or 0)
        confidence = str(item.get("confidence") or "")
        if bool(item.get("in_current_batch")):
            return count >= 5 or abs(manual) >= 1 or abs(computed) >= 0.25 or confidence != "weak"
        if abs(manual) >= 3:
            return True
        if abs(computed) >= 2:
            return True
        if count >= 50 and confidence != "weak":
            return True
        return False

    def _safe_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _sign(self, value: float | None, *, deadband: float = 0.05) -> int:
        if value is None or abs(value) <= deadband:
            return 0
        return 1 if value > 0 else -1

    def _preference_signal(
        self,
        *,
        computed_score: float | None,
        manual_score: float | None,
        accepted_count: int,
        rejected_count: int,
        average_rating: float | None,
    ) -> str:
        manual_sign = self._sign(manual_score)
        computed_sign = self._sign(computed_score)
        if manual_sign > 0:
            return "positive"
        if manual_sign < 0:
            return "negative"
        if computed_sign > 0:
            return "positive"
        if computed_sign < 0:
            return "negative"
        if average_rating is not None:
            if average_rating >= 7:
                return "positive"
            if average_rating <= 3:
                return "negative"
        if accepted_count > rejected_count:
            return "positive"
        if rejected_count > accepted_count:
            return "negative"
        return "neutral"

    def _preference_confidence(
        self,
        *,
        computed_score: float | None,
        manual_score: float | None,
        accepted_count: int,
        rejected_count: int,
        average_rating: float | None,
    ) -> tuple[str, str | None]:
        manual_sign = self._sign(manual_score)
        computed_sign = self._sign(computed_score)
        total = accepted_count + rejected_count
        conflict: str | None = None
        if manual_sign and computed_sign and manual_sign != computed_sign:
            conflict = "manual_positive_but_history_negative" if manual_sign > 0 else "manual_negative_but_history_positive"
        elif manual_sign > 0 and rejected_count >= max(20, accepted_count * 3):
            conflict = "manual_positive_but_many_rejections"
        elif manual_sign < 0 and accepted_count >= max(20, rejected_count * 3):
            conflict = "manual_negative_but_many_accepts"
        elif average_rating is not None and manual_sign > 0 and average_rating <= 4:
            conflict = "manual_positive_but_low_average_rating"
        elif average_rating is not None and manual_sign < 0 and average_rating >= 7:
            conflict = "manual_negative_but_high_average_rating"

        if conflict:
            return "mixed", conflict
        if manual_score is not None and abs(manual_score) >= 7:
            return "strong_positive" if manual_score > 0 else "strong_negative", None
        if computed_score is not None and abs(computed_score) >= 4:
            return "strong_positive" if computed_score > 0 else "strong_negative", None
        if total >= 100:
            if accepted_count >= rejected_count * 3:
                return "strong_positive", None
            if rejected_count >= accepted_count * 3:
                return "strong_negative", None
        if manual_score is not None and abs(manual_score) >= 3:
            return "medium_positive" if manual_score > 0 else "medium_negative", None
        if computed_score is not None and abs(computed_score) >= 1:
            return "medium_positive" if computed_score > 0 else "medium_negative", None
        if average_rating is not None:
            if average_rating >= 7:
                return "medium_positive", None
            if average_rating <= 3:
                return "medium_negative", None
        return "weak", None

    def _category_profile_to_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        saved_posts = int(item.get("saved_posts") or 0)
        if saved_posts >= 50:
            profile_confidence = "high"
        elif saved_posts >= 10:
            profile_confidence = "medium"
        elif saved_posts >= 5:
            profile_confidence = "low"
        else:
            profile_confidence = "very_low"

        payload: dict[str, Any] = {
            "category": self._export_category(item.get("category")),
            "saved_posts": saved_posts,
            "avg_personal_rating": item.get("average_rating"),
            "profile_confidence": profile_confidence,
        }
        if saved_posts >= 5:
            positive_tags = [self.db.llm_export_value_for_tag(tag) for tag in item.get("top_positive_tags", [])]
            negative_tags = [self.db.llm_export_value_for_tag(tag) for tag in item.get("top_negative_tags", [])]
            payload["top_positive_tags"] = positive_tags
            payload["top_negative_tags"] = negative_tags
            if bool(self.config.get("llm", {}).get("include_tag_legend", False)):
                payload["legend"] = {
                    self.db.llm_export_value_for_tag(tag): self.db.canonical_tag_for_tag(tag)
                    for tag in list(item.get("top_positive_tags", [])) + list(item.get("top_negative_tags", []))
                }
        return payload

    def _examples_to_payload(
        self,
        examples: dict[str, list[dict[str, Any]]],
        *,
        max_tags: int,
        current_tags: set[str],
        preference_by_tag: dict[str, dict[str, Any]],
        category_profile_tags: set[str],
    ) -> dict[str, Any]:
        return {
            group: [
                self._example_to_payload(
                    example,
                    max_tags=max_tags,
                    current_tags=current_tags,
                    preference_by_tag=preference_by_tag,
                    category_profile_tags=category_profile_tags,
                )
                for example in rows
            ]
            for group, rows in examples.items()
            if rows
        }

    def _example_to_payload(
        self,
        example: dict[str, Any],
        *,
        max_tags: int,
        current_tags: set[str],
        preference_by_tag: dict[str, dict[str, Any]],
        category_profile_tags: set[str],
    ) -> dict[str, Any]:
        raw_tags = [normalize_tag_token(str(tag)) for tag in example.get("tags", []) if normalize_tag_token(str(tag))]
        compact_tags = self._compact_example_tags(
            raw_tags,
            max_tags=max_tags,
            current_tags=current_tags,
            preference_by_tag=preference_by_tag,
            category_profile_tags=category_profile_tags,
        )
        exported_tags = self.db.build_llm_tag_export(compact_tags)
        payload = {
            "post_id": example.get("post_id"),
            "status": example.get("status"),
            "personal_rating": example.get("personal_rating"),
            "category": self._export_category(example.get("category")),
            "local_score": example.get("local_score"),
            "tags": exported_tags,
            "tags_compacted_from": len(raw_tags),
        }
        if bool(self.config.get("llm", {}).get("include_tag_legend", False)):
            payload["tag_legend"] = {
                self.db.llm_export_value_for_tag(tag): self.db.canonical_tag_for_tag(tag)
                for tag in compact_tags
            }
        return payload

    def _compact_example_tags(
        self,
        raw_tags: list[str],
        *,
        max_tags: int,
        current_tags: set[str],
        preference_by_tag: dict[str, dict[str, Any]],
        category_profile_tags: set[str],
    ) -> list[str]:
        seen: set[str] = set()
        unique_tags = []
        for tag in raw_tags:
            if tag and tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)

        def rank(tag: str) -> tuple[int, float, str]:
            preference = preference_by_tag.get(tag, {})
            manual = self._safe_float(preference.get("manual_score")) or 0.0
            computed = self._safe_float(preference.get("computed_score")) or 0.0
            accepted = int(preference.get("accepted_count") or 0)
            rejected = int(preference.get("rejected_count") or 0)
            strength = max(abs(manual), abs(computed), min(5.0, (accepted + rejected) / 100.0))
            priority = 5
            if tag in current_tags:
                priority = 0
            elif abs(manual) >= 3:
                priority = 1
            elif abs(computed) >= 2 or accepted + rejected >= 50:
                priority = 2
            elif tag in category_profile_tags:
                priority = 3
            return (priority, -strength, tag)

        return sorted(unique_tags, key=rank)[:max_tags]


    def _export_category(self, category_name: Any) -> str | None:
        return self.db.llm_export_value_for_category(str(category_name).strip() if category_name not in (None, "") else None)

    def _export_categories(self, category_names: Iterable[str]) -> list[str]:
        return [value for value in (self._export_category(name) for name in category_names) if value]

    def _load_category_names(self) -> list[str]:
        try:
            return [str(name) for name in self.db.list_category_names()]
        except Exception:
            return []
