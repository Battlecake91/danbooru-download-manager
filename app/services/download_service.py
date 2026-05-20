from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from app.core.database import Database

LOGGER = logging.getLogger(__name__)


class DownloadService:
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        self.config = config
        self.db = db
        self.timeout = int(config.get("request_timeout_seconds", 30))
        self.target_dir = Path(config["original_cache_dir"])
        self.target_dir.mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": str(config.get("user_agent", "DanbooruManager/0.1"))}
        )

        username = config.get("username")
        api_key = config.get("api_key")
        if username and api_key:
            self.session.auth = (username, api_key)

    def ensure_original_cached(self, post_id: int) -> str | None:
        row = self.db.get_post_detail(post_id)
        if row is None:
            return None

        existing = row["original_cache_path"] or row["original_path"]
        if existing and Path(str(existing)).exists():
            return str(existing)

        selected = choose_viewer_download_url(dict(row), self.config)
        if selected is None:
            LOGGER.warning("Keine Download-URL für Post %s", post_id)
            return None

        url, source_label = selected
        ext = file_extension_from_url(url, row["file_ext"])
        target = self.target_dir / f"{post_id}_{source_label}{ext}"
        part = target.with_suffix(target.suffix + ".part")

        if target.exists() and target.stat().st_size > 0:
            self.db.set_original_cache_path(post_id, str(target))
            return str(target)

        LOGGER.info("Lade Viewer-Datei für Post %s: %s", post_id, url)

        try:
            with self.session.get(url, stream=True, timeout=self.timeout) as response:
                response.raise_for_status()
                with part.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            handle.write(chunk)

            part.replace(target)
            self.db.set_original_cache_path(post_id, str(target))
            return str(target)

        except Exception:
            if part.exists():
                part.unlink(missing_ok=True)
            LOGGER.exception("Viewer-Datei konnte nicht geladen werden für Post %s", post_id)
            return None


def choose_viewer_download_url(row: dict[str, Any], config: dict[str, Any]) -> tuple[str, str] | None:
    source = str(config.get("viewer_download_source", "file")).lower()

    candidates_by_source: dict[str, list[tuple[str, str]]] = {
        "large": [
            ("large", str(row.get("large_file_url") or "")),
            ("file", str(row.get("file_url") or "")),
        ],
        "file": [
            ("file", str(row.get("file_url") or "")),
            ("large", str(row.get("large_file_url") or "")),
        ],
        "best": [
            ("file", str(row.get("file_url") or "")),
            ("large", str(row.get("large_file_url") or "")),
        ],
    }

    candidates = candidates_by_source.get(source, candidates_by_source["file"])

    for label, url in candidates:
        if url and url != "None":
            return url, label

    return None


def file_extension_from_url(url: str, fallback_ext: str | None) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix

    if suffix:
        return suffix

    if fallback_ext:
        fallback = str(fallback_ext).strip(".")
        if fallback:
            return f".{fallback}"

    return ".bin"
