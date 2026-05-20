from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)


class ThumbnailCache:
    def __init__(self, config: dict[str, Any], session: requests.Session) -> None:
        self.thumbnail_dir = Path(config["thumbnail_dir"])
        self.timeout = int(config.get("request_timeout_seconds", 30))
        self.session = session
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)

        self.source = str(config.get("thumbnail_download_source", "large")).lower()
        self.redownload_existing = bool(config.get("thumbnail_redownload_existing", False))

    def cache_thumbnail(self, post: dict[str, Any]) -> str | None:
        post_id = post.get("id")
        if post_id is None:
            return None

        selected = choose_thumbnail_url(post, self.source)
        if not selected:
            LOGGER.debug("Kein Thumbnail-URL für Post %s", post_id)
            return None

        url, source_label = selected
        ext = thumbnail_extension_from_url(url)

        target = self.thumbnail_dir / f"{post_id}_{source_label}{ext}"

        if target.exists() and target.stat().st_size > 0 and not self.redownload_existing:
            return str(target)

        part = target.with_suffix(target.suffix + ".part")

        try:
            with self.session.get(url, stream=True, timeout=self.timeout) as response:
                response.raise_for_status()
                with part.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 128):
                        if chunk:
                            handle.write(chunk)
            part.replace(target)
            return str(target)
        except Exception:
            if part.exists():
                part.unlink(missing_ok=True)
            LOGGER.exception("Thumbnail konnte nicht geladen werden für Post %s", post_id)
            return None


def choose_thumbnail_url(post: dict[str, Any], source: str) -> tuple[str, str] | None:
    source = (source or "large").lower()

    candidates_by_source: dict[str, list[tuple[str, str]]] = {
        "preview": [
            ("preview", str(post.get("preview_file_url") or "")),
            ("large", str(post.get("large_file_url") or "")),
            ("file", str(post.get("file_url") or "")),
        ],
        "large": [
            ("large", str(post.get("large_file_url") or "")),
            ("file", str(post.get("file_url") or "")),
            ("preview", str(post.get("preview_file_url") or "")),
        ],
        "file": [
            ("file", str(post.get("file_url") or "")),
            ("large", str(post.get("large_file_url") or "")),
            ("preview", str(post.get("preview_file_url") or "")),
        ],
        "best": [
            ("file", str(post.get("file_url") or "")),
            ("large", str(post.get("large_file_url") or "")),
            ("preview", str(post.get("preview_file_url") or "")),
        ],
    }

    candidates = candidates_by_source.get(source, candidates_by_source["large"])

    for label, url in candidates:
        if url and url != "None":
            return url, label

    media_asset = post.get("media_asset") or {}
    variants = media_asset.get("variants") or []
    for variant in variants:
        url = variant.get("url")
        variant_type = str(variant.get("type") or "variant")
        if url:
            safe_type = "".join(ch if ch.isalnum() else "_" for ch in variant_type.lower())
            return str(url), safe_type

    return None


def thumbnail_extension_from_url(url: str) -> str:
    lowered = url.lower().split("?", 1)[0]
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if lowered.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"
