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

    def cache_thumbnail(self, post: dict[str, Any]) -> str | None:
        post_id = post.get("id")
        if post_id is None:
            return None

        url = choose_thumbnail_url(post)
        if not url:
            LOGGER.debug("Kein Thumbnail-URL für Post %s", post_id)
            return None

        ext = thumbnail_extension_from_url(url)
        target = self.thumbnail_dir / f"{post_id}{ext}"

        if target.exists() and target.stat().st_size > 0:
            return str(target)

        part = target.with_suffix(target.suffix + ".part")

        try:
            with self.session.get(url, stream=True, timeout=self.timeout) as response:
                response.raise_for_status()
                with part.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 64):
                        if chunk:
                            handle.write(chunk)
            part.replace(target)
            return str(target)
        except Exception:
            if part.exists():
                part.unlink(missing_ok=True)
            LOGGER.exception("Thumbnail konnte nicht geladen werden für Post %s", post_id)
            return None


def choose_thumbnail_url(post: dict[str, Any]) -> str | None:
    for key in ("preview_file_url", "large_file_url", "file_url"):
        value = post.get(key)
        if value:
            return str(value)

    media_asset = post.get("media_asset") or {}
    variants = media_asset.get("variants") or []
    for variant in variants:
        url = variant.get("url")
        if url:
            return str(url)

    return None


def thumbnail_extension_from_url(url: str) -> str:
    lowered = url.lower().split("?", 1)[0]
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if lowered.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"
