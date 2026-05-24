from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.core.database import Database, clamp_number
from app.core.tag_privacy import normalize_tag_token


@dataclass(frozen=True)
class RecommendationScore:
    score: float
    positive: list[str]
    negative: list[str]
    ignored: list[str]
    used_count: int

    @property
    def label(self) -> str:
        if self.score > 0:
            return f"+{self.score:g}"
        return f"{self.score:g}"


class RecommendationEngine:
    """Lightweight local tag-based recommendation scoring.

    This is intentionally not an LLM replacement. It simply combines the tag
    scores the user has already curated and respects the dedicated
    ``ignore_recommendation_score`` flag. Small, deterministic and boring,
    which is exactly what a preselection baseline should be before anyone lets
    a language model hallucinate taste.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def score_tags(self, tags: Iterable[str]) -> RecommendationScore:
        clean_tags = sorted({normalize_tag_token(str(tag)) for tag in tags if normalize_tag_token(str(tag))})
        if not clean_tags:
            return RecommendationScore(score=0.0, positive=[], negative=[], ignored=[], used_count=0)

        metadata = self.db.fetch_tag_display_metadata(clean_tags)

        # Avoid counting ten color variants as ten independent signals once they
        # collapse to the same canonical tag. Keep the strongest signal per
        # canonical tag. Yes, even the tag scorer gets to avoid spam. Lucky thing.
        by_canonical: dict[str, dict[str, Any]] = {}
        ignored: list[str] = []

        for tag in clean_tags:
            meta = metadata.get(tag, {})
            if bool(meta.get("ignore_recommendation_score")):
                ignored.append(tag)
                continue
            if bool(meta.get("scoring_excluded")):
                ignored.append(tag)
                continue

            try:
                value = float(meta.get("score") or 0.0)
            except (TypeError, ValueError):
                value = 0.0

            if value == 0.0:
                continue

            canonical = normalize_tag_token(str(meta.get("canonical_tag") or tag)) or tag
            previous = by_canonical.get(canonical)
            if previous is None or abs(value) > abs(float(previous["value"])):
                by_canonical[canonical] = {"tag": tag, "canonical": canonical, "value": value}

        contributions = list(by_canonical.values())
        contributions.sort(key=lambda item: (-abs(float(item["value"])), str(item["tag"]).casefold()))

        # Top-N cap keeps huge tag lists from steamrolling the score.
        top = contributions[:30]
        raw_score = sum(float(item["value"]) for item in top)
        score = round(clamp_number(raw_score, -100.0, 100.0), 2)

        positive_items = [item for item in contributions if float(item["value"]) > 0]
        negative_items = [item for item in contributions if float(item["value"]) < 0]
        positive_items.sort(key=lambda item: (-float(item["value"]), str(item["tag"]).casefold()))
        negative_items.sort(key=lambda item: (float(item["value"]), str(item["tag"]).casefold()))

        positive = [f"{item['tag']} +{float(item['value']):g}" for item in positive_items[:6]]
        negative = [f"{item['tag']} {float(item['value']):g}" for item in negative_items[:6]]

        return RecommendationScore(
            score=score,
            positive=positive,
            negative=negative,
            ignored=sorted(ignored, key=str.casefold),
            used_count=len(contributions),
        )
