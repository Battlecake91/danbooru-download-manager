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
    local_score: float | None
    current_category: str | None
    tags: list[str]


class LLMPayloadService:
    """Build the first LLM input payload without sending it anywhere.

    This is intentionally provider-neutral. The next step can feed this payload
    into an OpenAI-compatible chat endpoint or a local model. For now the GUI can
    show/copy the exact data, so we can inspect the prompt before letting a model
    make confident nonsense. A rare moment of restraint, enjoy it.
    """

    def __init__(self, config: dict[str, Any], db: Database) -> None:
        self.config = config
        self.db = db
        self.recommendation_engine = RecommendationEngine(db)

    def build_payload_for_posts(self, post_ids: Iterable[int]) -> dict[str, Any]:
        ids = []
        seen: set[int] = set()
        for raw_id in post_ids:
            post_id = int(raw_id)
            if post_id not in seen:
                ids.append(post_id)
                seen.add(post_id)

        if not ids:
            raise ValueError("Keine Posts ausgewählt.")

        llm_config = self.config.get("llm", {}) or {}
        max_posts = max(1, int(llm_config.get("max_posts_per_request", 20) or 20))
        max_tags = max(1, int(llm_config.get("max_tags_per_post", 80) or 80))
        ids = ids[:max_posts]

        posts = [self._load_post(post_id, max_tags=max_tags) for post_id in ids]
        categories = self._load_category_names()

        return {
            "task": "danbooru_post_preselection",
            "schema_version": 1,
            "instructions": self._instructions(llm_config),
            "expected_response": {
                "posts": [
                    {
                        "post_id": "integer",
                        "score": "number from -100 to 100",
                        "decision": "reject|maybe|keep|save_candidate",
                        "category": "category name or null",
                        "reason": "short German reason",
                    }
                ]
            },
            "config": {
                "provider_enabled": bool(llm_config.get("enabled", False)),
                "backend": str(llm_config.get("backend", "none")),
                "tag_export_mode": str(llm_config.get("tag_export_mode", "hashed_alias")),
                "include_tag_legend": bool(llm_config.get("include_tag_legend", False)),
                "available_categories": categories,
            },
            "posts": [self._post_to_payload(post) for post in posts],
        }

    def _instructions(self, llm_config: dict[str, Any]) -> str:
        custom_prompt = str(llm_config.get("system_prompt", "") or "").strip()
        if custom_prompt:
            return custom_prompt
        return (
            "Bewerte Danbooru-Posts anhand der Tags und Metadaten. "
            "Nutze die lokalen Scores als Hinweis, aber nicht blind. "
            "Gib pro Post eine kurze JSON-taugliche Entscheidung zurück. "
            "Bevorzuge klare Keep/Reject-Entscheidungen; maybe nur bei Unsicherheit."
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
                c.name AS category_name
            FROM posts p
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
            local_score=post_row["local_score"],
            current_category=post_row["category_name"],
            tags=exported_tags,
        )

    def _post_to_payload(self, post: LLMPayloadPost) -> dict[str, Any]:
        recommendation = self.recommendation_engine.score_tags(post.tags)
        return {
            "post_id": post.post_id,
            "rating": post.rating,
            "danbooru_score": post.danbooru_score,
            "status": post.status,
            "local_score": post.local_score,
            "current_category": post.current_category,
            "local_recommendation_score": recommendation.score,
            "local_positive_signals": recommendation.positive,
            "local_negative_signals": recommendation.negative,
            "tags": post.tags,
        }

    def _load_category_names(self) -> list[str]:
        try:
            return [str(name) for name in self.db.list_category_names()]
        except Exception:
            return []
