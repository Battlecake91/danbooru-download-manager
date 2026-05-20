from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from app.core.database import Database


class FilenameBuilder:
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        self.config = config
        self.db = db

    def build_filename(self, post_id: int, source_path: Path) -> str:
        filename_config = self.config.get("filename", {}) or {}
        pattern = str(filename_config.get("pattern", "{id}_{tags}_{hash}{ext}"))
        max_length = int(filename_config.get("max_length", 180))
        tags_count = int(filename_config.get("tags_count", 8))
        hash_length = int(filename_config.get("hash_length", 8))

        excluded_tags = self.db.filename_excluded_tag_set()
        # Config bleibt Default/Import-Basis. Falls die DB noch leer ist, respektieren wir zur Sicherheit
        # zusätzlich die YAML-Werte in diesem Lauf.
        excluded_tags.update(str(tag) for tag in filename_config.get("excluded_tags", []) or [])

        tags = self.tags_for_filename(post_id, excluded_tags, tags_count)
        tag_part = "_".join(tags) if tags else "untagged"

        ext = source_path.suffix or self.extension_from_db(post_id) or ".bin"
        digest = self.short_hash(post_id, source_path, hash_length)

        filename = pattern.format(
            id=post_id,
            tags=tag_part,
            hash=digest,
            ext=ext,
        )

        filename = safe_filename(filename)
        filename = trim_filename(filename, max_length, ext)
        return filename

    def tags_for_filename(self, post_id: int, excluded_tags: set[str], limit: int) -> list[str]:
        rows = self.db.execute(
            """
            SELECT tag, tag_type
            FROM post_tags
            WHERE post_id = ?
            ORDER BY
                CASE tag_type
                    WHEN 'copyright' THEN 1
                    WHEN 'character' THEN 2
                    WHEN 'artist' THEN 3
                    WHEN 'general' THEN 4
                    WHEN 'meta' THEN 5
                    ELSE 9
                END,
                tag
            """,
            (post_id,),
        ).fetchall()

        selected: list[str] = []
        for row in rows:
            tag = str(row["tag"])
            if tag in excluded_tags:
                continue
            selected.append(tag)
            if len(selected) >= limit:
                break

        return selected

    def extension_from_db(self, post_id: int) -> str | None:
        row = self.db.execute("SELECT file_ext FROM posts WHERE id = ?", (post_id,)).fetchone()
        if row and row["file_ext"]:
            return "." + str(row["file_ext"]).strip(".")
        return None

    def short_hash(self, post_id: int, source_path: Path, hash_length: int) -> str:
        seed = f"{post_id}:{source_path.name}:{source_path.stat().st_size if source_path.exists() else 0}"
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:hash_length]


def safe_filename(value: str) -> str:
    value = value.strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"_+", "_", value)
    value = value.strip("._ ")
    return value or "file"


def trim_filename(filename: str, max_length: int, ext: str) -> str:
    if len(filename) <= max_length:
        return filename

    suffix = ext if filename.lower().endswith(ext.lower()) else ""
    stem = filename[: -len(suffix)] if suffix else filename
    allowed_stem_len = max(8, max_length - len(suffix))
    return stem[:allowed_stem_len].rstrip("._ ") + suffix
