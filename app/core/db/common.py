from __future__ import annotations

import shlex
from typing import Any

ACTIVE_STATUSES = {"new", "potential"}

ALL_ALLOWED_STATUSES = {
    "new",
    "potential",
    "review",
    "selected_save",
    "auto_rejected",
    "rejected",
    "accepted",
    "already_known",
    "downloaded",
    "saved",
}


def parse_preview_search_terms(search_text: str) -> tuple[list[str], list[str]]:
    """Parse preview search into include and exclude terms.

    Example: ``brown_eyes -red_hair`` means: must match brown_eyes,
    must not have red_hair as tag. Quoted terms are supported because even
    search strings deserve a tiny bit of dignity.
    """
    try:
        tokens = shlex.split(search_text)
    except ValueError:
        tokens = search_text.split()

    positive: list[str] = []
    negative: list[str] = []

    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token.startswith("-") and len(token) > 1:
            negative.append(token[1:].strip())
        else:
            positive.append(token)

    return positive, negative


def is_path_like_preview_search_term(term: str) -> bool:
    return any(marker in term for marker in ("/", "\\", "."))


def clamp_number(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def calculate_computed_tag_score(
    *,
    average_rating: Any,
    saved_count: int,
    rejected_count: int,
    scoring_excluded: bool = False,
) -> float:
    """Compute a conservative automatic tag score.

    The score combines user stars and saved/rejected statistics, but heavily
    dampens extremely common tags. Otherwise `1girl` would become a fake
    villain just because it appears in almost everything. Computers love that
    kind of statistical stupidity, so we put a fence around it.
    """
    if scoring_excluded:
        return 0.0

    sample_count = int(saved_count or 0) + int(rejected_count or 0)
    star_signal = 0.0
    if average_rating not in {None, "", "None"}:
        try:
            # 0..10 stars -> about -2.5..+2.5. Good/bad, but not a dictator.
            star_signal = clamp_number((float(average_rating) - 5.0) / 2.0, -2.5, 2.5)
        except (TypeError, ValueError):
            star_signal = 0.0

    accept_signal = 0.0
    if sample_count >= 20:
        accept_rate = (float(saved_count or 0) + 1.0) / (float(sample_count) + 2.0)
        accept_signal = clamp_number((accept_rate - 0.5) * 10.0, -5.0, 5.0)

        # Confidence grows with samples, but caps early. 20 samples are a hint,
        # 100+ are usually enough.
        confidence = clamp_number(sample_count / 100.0, 0.2, 1.0)

        # Very common tags are usually weak predictors. If both sides have lots
        # of examples, we damp the signal hard instead of letting generic tags
        # like `1girl` bulldoze the result.
        generic_damping = 1.0
        if sample_count >= 1000 and saved_count >= 100 and rejected_count >= 100:
            generic_damping = 0.25
        elif sample_count >= 500 and saved_count >= 50 and rejected_count >= 50:
            generic_damping = 0.45

        accept_signal *= confidence * generic_damping

    return round(clamp_number(star_signal + accept_signal, -5.0, 5.0), 2)


def normalize_categories(raw_categories: Any) -> list[dict[str, Any]]:
    if raw_categories is None:
        return []

    normalized: list[dict[str, Any]] = []

    if isinstance(raw_categories, list):
        for item in raw_categories:
            if isinstance(item, dict):
                if "name" not in item:
                    raise ValueError(f"Category without name: {item!r}")

                name = str(item["name"])

                normalized.append(
                    {
                        "name": name,
                        "folder_name": str(item.get("folder_name", name)),
                        "output_path": item.get("output_path"),
                        "hotkey": item.get("hotkey"),
                        "include": list(item.get("include", []) or []),
                        "exclude": list(item.get("exclude", []) or []),
                        "include_groups": list(item.get("include_groups", []) or []),
                    }
                )

            elif isinstance(item, str):
                normalized.append(
                    {
                        "name": item,
                        "folder_name": item,
                        "output_path": None,
                        "hotkey": None,
                        "include": [item],
                        "exclude": [],
                        "include_groups": [],
                    }
                )

            else:
                raise ValueError(f"Invalid category entry: {item!r}")

        return normalized

    if isinstance(raw_categories, dict):
        for name, value in raw_categories.items():
            if isinstance(value, list):
                normalized.append(
                    {
                        "name": str(name),
                        "folder_name": str(name),
                        "output_path": None,
                        "hotkey": None,
                        "include": list(value),
                        "exclude": [],
                        "include_groups": [],
                    }
                )

            elif isinstance(value, dict):
                normalized.append(
                    {
                        "name": str(name),
                        "folder_name": str(value.get("folder_name", name)),
                        "output_path": value.get("output_path"),
                        "hotkey": value.get("hotkey"),
                        "include": list(value.get("include", []) or []),
                        "exclude": list(value.get("exclude", []) or []),
                        "include_groups": list(value.get("include_groups", []) or []),
                    }
                )

            else:
                raise ValueError(f"Invalid category '{name}': {value!r}")

        return normalized

    raise ValueError(f"Invalid categories format: {type(raw_categories).__name__}")
