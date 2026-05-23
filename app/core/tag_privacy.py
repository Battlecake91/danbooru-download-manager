from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Mapping


_VALID_TOKEN_RE = re.compile(r"[^a-zA-Z0-9_]+")


@dataclass(frozen=True)
class TagIdentity:
    original_tag: str
    canonical_tag: str
    llm_token: str


def normalize_tag_token(tag: str) -> str:
    """Return a conservative normalized token for aliases/canonical tags."""
    clean = str(tag or "").strip().lower().replace(" ", "_")
    clean = _VALID_TOKEN_RE.sub("_", clean)
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean


def canonicalize_tag(tag: str, aliases: Mapping[str, str] | None = None) -> str:
    """Resolve an original Danbooru tag to its canonical alias layer.

    Alias resolution is intentionally one hop plus a small loop guard. This lets
    simple chains work, but refuses to become a tiny graph database just because
    humans enjoy naming the same shirt twenty-seven times.
    """
    aliases = aliases or {}
    current = normalize_tag_token(tag)
    if not current:
        return ""

    seen = {current}
    for _ in range(8):
        next_value = normalize_tag_token(aliases.get(current, ""))
        if not next_value or next_value in seen:
            break
        current = next_value
        seen.add(current)
    return current


def salted_tag_hash(canonical_tag: str, salt: str, prefix: str = "tag_", length: int = 12) -> str:
    canonical = normalize_tag_token(canonical_tag)
    if not canonical:
        canonical = "empty"
    digest = hashlib.sha256(f"{salt}:{canonical}".encode("utf-8")).hexdigest()
    safe_length = max(4, min(64, int(length)))
    return f"{prefix}{digest[:safe_length]}"


def build_tag_identity(
    original_tag: str,
    aliases: Mapping[str, str] | None,
    salt: str,
    prefix: str = "tag_",
    length: int = 12,
) -> TagIdentity:
    original = normalize_tag_token(original_tag)
    canonical = canonicalize_tag(original, aliases)
    return TagIdentity(
        original_tag=original,
        canonical_tag=canonical,
        llm_token=salted_tag_hash(canonical, salt=salt, prefix=prefix, length=length),
    )
