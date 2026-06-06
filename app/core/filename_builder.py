from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.core.database import Database


TAG_TYPE_ORDER = ["artist", "character", "copyright", "general", "meta"]


@dataclass(frozen=True)
class FilenamePreviewDetails:
    post_id: int
    pattern: str
    filename: str
    extension: str
    included_tags: dict[str, list[str]]
    excluded_tags: dict[str, list[str]]
    placeholder_values: dict[str, str]


class FilenameBuilder:
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        self.config = config
        self.db = db

    def build_filename(self, post_id: int, source_path: Path) -> str:
        return self.build_preview_details(post_id, source_path).filename

    def build_preview_details(
        self,
        post_id: int,
        source_path: Path,
        diagnostic: Callable[[str], None] | None = None,
    ) -> FilenamePreviewDetails:
        def diag(message: str) -> None:
            if diagnostic is not None:
                diagnostic(f"FILENAME {message}")

        diag(f"begin post_id={post_id} source={str(source_path)!r}")
        pattern = str(self.filename_config().get("pattern", "%artists%_%characters%_%general%_%postid%"))
        max_length = int(self.filename_config().get("max_length", 180))
        extension = self.resolve_extension(post_id, source_path)

        diag("typed_tags_for_post begin")
        raw_typed_tags = self.typed_tags_for_post(post_id)
        diag("typed_tags_for_post end counts=" + repr({key: len(value) for key, value in raw_typed_tags.items()}))
        diag("excluded_tags begin")
        excluded = self.excluded_tags()
        diag(f"excluded_tags end count={len(excluded)}")

        included_tags: dict[str, list[str]] = {}
        excluded_tags: dict[str, list[str]] = {}
        for tag_type, tags in raw_typed_tags.items():
            included = [tag for tag in tags if tag not in excluded]
            diag(f"prioritized_tags begin type={tag_type!r} count={len(included)}")
            included_tags[tag_type] = self.prioritized_tags(included, diagnostic=diagnostic)
            diag(f"prioritized_tags end type={tag_type!r}")
            excluded_tags[tag_type] = [tag for tag in tags if tag in excluded]

        artist_value = self.artist_placeholder_value(included_tags)

        values = {
            "postid": str(post_id),
            "id": str(post_id),
            "artist": artist_value,
            "artists": artist_value,
            "character": self.join_tags(included_tags["character"]),
            "characters": self.join_tags(included_tags["character"]),
            "copyright": self.join_tags(included_tags["copyright"]),
            "copyrights": self.join_tags(included_tags["copyright"]),
            "series": self.join_tags(included_tags["copyright"]),
            "serie": self.join_tags(included_tags["copyright"]),
            "general": self.join_tags(self.limited_general_tags(included_tags["general"])),
            "meta": self.join_tags(included_tags["meta"]),
            "tags": self.join_tags(self.default_tag_mix(included_tags)),
            "hash": self.short_hash(post_id, source_path),
            "ext": extension,
        }

        filename = pattern
        for key, value in values.items():
            filename = replace_placeholder(filename, key, value)

        if not contains_placeholder(pattern, "ext") and extension:
            filename = f"{filename}{extension}"

        filename = collapse_separators(safe_filename(filename))
        if not filename or filename == extension.lstrip(".") or filename == extension:
            filename = f"{post_id}{extension}"
        if len(filename) > max_length:
            filename = truncate_filename(filename, max_length)

        diag(f"end filename={filename!r}")
        return FilenamePreviewDetails(
            post_id=post_id,
            pattern=pattern,
            filename=filename,
            extension=extension,
            included_tags=included_tags,
            excluded_tags=excluded_tags,
            placeholder_values=values,
        )

    def filename_config(self) -> dict[str, Any]:
        value = self.config.get("filename", {})
        return value if isinstance(value, dict) else {}

    def prioritize_filename_tags(self) -> bool:
        """Return whether filename tags should be ordered by score.

        The GUI stores this option in SQLite app_settings. The FilenameBuilder
        can live longer than the Config tab, so relying only on the nested
        startup config makes the option look enabled while the builder keeps
        using the old value. Delightful little config gaslighting. Therefore
        the database value wins whenever it exists.
        """
        value: Any = None

        if hasattr(self.db, "get_app_setting"):
            try:
                value = self.db.get_app_setting("filename.sort_tags_by_average_rating", None)
            except Exception:
                value = None

        if value is None:
            value = self.filename_config().get("sort_tags_by_average_rating", False)

        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "y"}
        return bool(value)

    def prioritized_tags(
        self,
        tags: list[str],
        diagnostic: Callable[[str], None] | None = None,
    ) -> list[str]:
        """Return tags ordered for filename placeholders.

        Filename-Exclude is handled before this method. Scoring-Exclude does
        not remove a tag from filenames, it only prevents that tag from being
        promoted by automatic/manual scoring. That way a noisy tag can still be
        present if the pattern has enough room, but it no longer steals one of
        the important early filename slots. Tiny mercy for future-you reading
        folders at 2 a.m.
        """
        if not tags or not self.prioritize_filename_tags():
            return tags

        if diagnostic is not None:
            diagnostic(f"FILENAME fetch_tag_metadata begin count={len(tags)}")
        try:
            metadata = self.db.fetch_tag_metadata(tags)
            if diagnostic is not None:
                diagnostic(f"FILENAME fetch_tag_metadata end count={len(metadata)}")
        except Exception:
            return tags

        indexed_tags = list(enumerate(tags))

        def number(value: Any, default: float = 0.0) -> float:
            try:
                if value is None or value == "":
                    return default
                return float(value)
            except (TypeError, ValueError):
                return default

        def sort_key(item: tuple[int, str]) -> tuple[int, float, float, int]:
            index, tag = item
            info = metadata.get(tag, {})
            scoring_excluded = 1 if info.get("scoring_excluded") else 0
            score = number(info.get("score"), 0.0)
            average_rating = number(info.get("average_rating"), -1.0)
            return (
                scoring_excluded,
                -score,
                -average_rating,
                index,
            )

        return [tag for _, tag in sorted(indexed_tags, key=sort_key)]

    def typed_tags_for_post(self, post_id: int) -> dict[str, list[str]]:
        rows = self.db.execute(
            """
            SELECT tag, tag_type
            FROM post_tags
            WHERE post_id = ?
            ORDER BY
                CASE tag_type
                    WHEN 'artist' THEN 1
                    WHEN 'character' THEN 2
                    WHEN 'copyright' THEN 3
                    WHEN 'general' THEN 4
                    WHEN 'meta' THEN 5
                    ELSE 9
                END,
                tag ASC
            """,
            (post_id,),
        ).fetchall()

        result: dict[str, list[str]] = {tag_type: [] for tag_type in TAG_TYPE_ORDER}
        for row in rows:
            tag_type = str(row["tag_type"] or "general")
            tag = str(row["tag"] or "").strip()
            if not tag:
                continue
            if tag_type not in result:
                tag_type = "general"
            result[tag_type].append(tag)
        return result

    def excluded_tags(self) -> set[str]:
        if hasattr(self.db, "filename_excluded_tag_set"):
            return set(self.db.filename_excluded_tag_set())
        return {str(tag) for tag in self.filename_config().get("excluded_tags", []) or []}

    def resolve_extension(self, post_id: int, source_path: Path) -> str:
        row = self.db.get_post_detail(post_id)
        if row is not None and row["file_ext"]:
            ext = str(row["file_ext"]).strip()
            if ext:
                return "." + ext.lstrip(".")
        if source_path.suffix:
            return source_path.suffix
        return ".bin"

    def limited_general_tags(self, general_tags: list[str]) -> list[str]:
        count = int(self.filename_config().get("tags_count", 8))
        return general_tags[: max(0, count)]

    def default_tag_mix(self, typed_tags: dict[str, list[str]]) -> list[str]:
        count = int(self.filename_config().get("tags_count", 8))
        mixed: list[str] = []
        for tag_type in TAG_TYPE_ORDER:
            mixed.extend(typed_tags[tag_type])
        return mixed[: max(0, count)]

    def join_tags(self, tags: list[str]) -> str:
        clean = [safe_filename_part(tag) for tag in tags if tag]
        clean = [tag for tag in clean if tag]
        return "_".join(clean)

    def artist_placeholder_value(self, typed_tags: dict[str, list[str]]) -> str:
        artist_value = self.join_tags(typed_tags["artist"])
        if artist_value:
            return artist_value

        copyright_tags = {tag.lower() for tag in typed_tags.get("copyright", [])}
        if "original" in copyright_tags:
            return "original"

        return ""

    def short_hash(self, post_id: int, source_path: Path) -> str:
        hash_length = int(self.filename_config().get("hash_length", 8))
        seed = f"{post_id}:{source_path.name}".encode("utf-8", errors="ignore")
        return hashlib.sha1(seed).hexdigest()[: max(1, hash_length)]


def safe_filename_part(value: str) -> str:
    value = value.strip().replace(" ", "_")
    value = re.sub(r"[^\w.\-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value)
    return value.strip("._-")


def safe_filename(value: str) -> str:
    value = value.replace("\\", "_").replace("/", "_")
    value = re.sub(r'[<>:"|?*\x00-\x1F]', "_", value)
    value = re.sub(r"_+", "_", value)
    value = value.strip(" ._")
    return value


def collapse_separators(value: str) -> str:
    value = re.sub(r"_+", "_", value)
    return value.strip("_")


def truncate_filename(filename: str, max_length: int) -> str:
    if len(filename) <= max_length:
        return filename
    path = Path(filename)
    suffix = path.suffix
    stem = path.stem
    available = max(8, max_length - len(suffix))
    return stem[:available].rstrip("._-") + suffix


def replace_placeholder(pattern: str, key: str, value: str) -> str:
    result = pattern
    variants = {
        f"%{key}%",
        f"%{key.upper()}%",
        f"%{key.capitalize()}%",
        f"{{{key}}}",
        f"{{{key.upper()}}}",
        f"{{{key.capitalize()}}}",
    }
    if key == "postid":
        variants.update({"%postID%", "%postId%", "{postID}", "{postId}"})
    for placeholder in variants:
        result = result.replace(placeholder, value)
    return result


def contains_placeholder(pattern: str, key: str) -> bool:
    probe = pattern.lower()
    return f"%{key.lower()}%" in probe or f"{{{key.lower()}}}" in probe
