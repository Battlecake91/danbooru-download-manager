from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from app.core.database import Database

LOGGER = logging.getLogger(__name__)

FULL_ORIGINAL_SOURCE_LABEL = "file"
NON_FINAL_SOURCE_LABELS = {"preview", "large", "sample", "sample_large", "sample_alternates"}


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

    def ensure_original_cached(self, post_id: int, force: bool = False) -> str | None:
        """Cache a display-quality file for the viewer.

        This follows ``viewer_download_source`` and may therefore cache Danbooru's
        preview/large/sample image. It is intentionally *not* used for final saving.
        Humans naming this "original" was a tiny act of sabotage, naturally.
        """
        row = self.db.get_post_detail(post_id)
        if row is None:
            return None

        existing = row["original_cache_path"] or row["original_path"]
        if not force and existing and Path(str(existing)).exists():
            return str(existing)

        selected = choose_viewer_download_url(dict(row), self.config)
        if selected is None:
            LOGGER.warning("No download URL for post %s", post_id)
            return None

        url, source_label = selected
        return self._download_to_cache(post_id, url, source_label, row["file_ext"], "viewer file", force=force)

    def ensure_full_original_cached(self, post_id: int, force: bool = False) -> str | None:
        """Cache the real Danbooru original file for final saving.

        Final files must never be based on preview/large/sample thumbnails. If an
        older run already cached ``*_large.*`` or ``*_preview.*`` in
        ``original_cache_path``, this method ignores it and downloads ``file_url``.
        """
        row = self.db.get_post_detail(post_id)
        if row is None:
            return None

        file_url = clean_url(row["file_url"])
        file_ext = row["file_ext"]

        if file_url:
            ext = file_extension_from_url(file_url, file_ext)
            full_target = self.target_dir / f"{post_id}_{FULL_ORIGINAL_SOURCE_LABEL}{ext}"

            if not force and full_target.exists() and full_target.stat().st_size > 0:
                self.db.set_original_cache_path(post_id, str(full_target))
                return str(full_target)

            cached_value = row["original_cache_path"]
            if not force and cached_value:
                cached_path = Path(str(cached_value))
                if cached_path.exists() and is_full_original_cache_path(cached_path, post_id):
                    return str(cached_path)

            return self._download_to_cache(
                post_id,
                file_url,
                FULL_ORIGINAL_SOURCE_LABEL,
                file_ext,
                "original file",
                force=force,
            )

        # Fallback only for posts where Danbooru does not provide file_url.
        # Then use the best available variant and log clearly that it
        # may not be the real original.
        selected = choose_best_available_download_url(dict(row))
        if selected is None:
            LOGGER.warning("No original URL for post %s", post_id)
            return None

        url, source_label = selected
        LOGGER.warning(
            "Post %s has no file_url. Falling back to %s; final file may be smaller than the original.",
            post_id,
            source_label,
        )
        return self._download_to_cache(post_id, url, source_label, file_ext, "fallback file", force=force)

    def _download_to_cache(
        self,
        post_id: int,
        url: str,
        source_label: str,
        fallback_ext: str | None,
        log_label: str,
        force: bool = False,
    ) -> str | None:
        ext = file_extension_from_url(url, fallback_ext)
        safe_source_label = safe_source_name(source_label)
        target = self.target_dir / f"{post_id}_{safe_source_label}{ext}"
        part = target.with_suffix(target.suffix + ".part")

        if target.exists() and target.stat().st_size > 0 and not force:
            self.db.set_original_cache_path(post_id, str(target))
            return str(target)

        if force:
            part.unlink(missing_ok=True)

        LOGGER.info("Downloading %s for post %s: %s", log_label, post_id, url)

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
            LOGGER.exception("%s could not be downloaded for post %s", log_label, post_id)
            return None


def choose_viewer_download_url(row: dict[str, Any], config: dict[str, Any]) -> tuple[str, str] | None:
    source = str(config.get("viewer_download_source", "file")).lower()

    candidates_by_source: dict[str, list[tuple[str, str]]] = {
        "preview": [
            ("preview", str(row.get("preview_url") or "")),
            ("large", str(row.get("large_file_url") or "")),
            ("file", str(row.get("file_url") or "")),
        ],
        "large": [
            ("large", str(row.get("large_file_url") or "")),
            ("preview", str(row.get("preview_url") or "")),
            ("file", str(row.get("file_url") or "")),
        ],
        "file": [
            ("file", str(row.get("file_url") or "")),
            ("large", str(row.get("large_file_url") or "")),
            ("preview", str(row.get("preview_url") or "")),
        ],
        "best": [
            ("file", str(row.get("file_url") or "")),
            ("large", str(row.get("large_file_url") or "")),
            ("preview", str(row.get("preview_url") or "")),
        ],
    }

    candidates = candidates_by_source.get(source, candidates_by_source["preview"])
    return first_valid_url(candidates)


def choose_best_available_download_url(row: dict[str, Any]) -> tuple[str, str] | None:
    return first_valid_url(
        [
            ("file", str(row.get("file_url") or "")),
            ("large", str(row.get("large_file_url") or "")),
            ("preview", str(row.get("preview_url") or "")),
        ]
    )


def first_valid_url(candidates: list[tuple[str, str]]) -> tuple[str, str] | None:
    for label, url in candidates:
        cleaned = clean_url(url)
        if cleaned:
            return cleaned, label
    return None


def clean_url(url: Any) -> str | None:
    value = str(url or "").strip()
    if not value or value.lower() == "none":
        return None
    return value


def safe_source_name(source_label: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in source_label.lower()).strip("_")
    return cleaned or "file"


def is_full_original_cache_path(path: Path, post_id: int) -> bool:
    """Return True only for cache files that were stored from Danbooru file_url."""
    stem = path.stem.lower()
    expected_prefix = f"{post_id}_"
    if not stem.startswith(expected_prefix):
        return False

    source_part = stem[len(expected_prefix) :]
    if source_part in NON_FINAL_SOURCE_LABELS:
        return False

    return source_part == FULL_ORIGINAL_SOURCE_LABEL or source_part.startswith("file_")


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
