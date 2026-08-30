from __future__ import annotations

import json
import secrets
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from app.core.db.common import (
    ACTIVE_STATUSES,
    ALL_ALLOWED_STATUSES,
    calculate_computed_tag_score,
    clamp_number,
    is_path_like_preview_search_term,
    parse_preview_search_terms,
)
from app.core.tag_privacy import build_tag_identity, canonicalize_tag, normalize_tag_token, salted_tag_hash


class DatabaseMaintenanceMixin:
    """Database maintenance and size analysis helpers."""

    def database_file_sizes(self) -> dict[str, int]:
        """Return sizes of the SQLite database and sidecar files in bytes."""
        base = Path(self.path)
        sizes: dict[str, int] = {}
        for label, path in {
            "database": base,
            "wal": Path(str(base) + "-wal"),
            "shm": Path(str(base) + "-shm"),
        }.items():
            try:
                sizes[label] = path.stat().st_size if path.exists() else 0
            except OSError:
                sizes[label] = 0
        sizes["total"] = sum(sizes.values())
        return sizes

    def analyze_database_size(self) -> dict[str, Any]:
        """Collect a compact size report for the maintenance UI.

        Uses SQLite's dbstat virtual table when available. Some SQLite builds
        omit it, because apparently even introspection is optional if everyone
        involved enjoys guessing.
        """
        if self.connection is None:
            raise RuntimeError("Database is not connected")

        page_size = int(self.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(self.execute("PRAGMA page_count").fetchone()[0])
        freelist_count = int(self.execute("PRAGMA freelist_count").fetchone()[0])
        journal_mode = str(self.execute("PRAGMA journal_mode").fetchone()[0])
        wal_autocheckpoint = int(self.execute("PRAGMA wal_autocheckpoint").fetchone()[0])

        file_sizes = self.database_file_sizes()

        counts: dict[str, int | None] = {}
        for table in ("posts", "post_tags", "tag_scores", "categories", "app_settings"):
            try:
                row = self.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                counts[table] = int(row[0]) if row is not None else None
            except sqlite3.Error:
                counts[table] = None

        dbstat_available = True
        object_sizes: list[dict[str, Any]] = []
        try:
            rows = self.execute(
                """
                SELECT name, SUM(pgsize) AS bytes
                FROM dbstat
                GROUP BY name
                ORDER BY bytes DESC
                """
            ).fetchall()
            object_sizes = [
                {"name": str(row["name"]), "bytes": int(row["bytes"] or 0)}
                for row in rows
            ]
        except sqlite3.Error:
            dbstat_available = False

        setting_rows = self.execute(
            """
            SELECT key, LENGTH(COALESCE(value, '')) AS bytes, updated_at
            FROM app_settings
            ORDER BY bytes DESC
            LIMIT 30
            """
        ).fetchall()
        largest_app_settings = [
            {
                "key": str(row["key"]),
                "bytes": int(row["bytes"] or 0),
                "updated_at": str(row["updated_at"] or ""),
            }
            for row in setting_rows
        ]

        return {
            "path": str(self.path),
            "file_sizes": file_sizes,
            "sqlite": {
                "page_size": page_size,
                "page_count": page_count,
                "freelist_count": freelist_count,
                "database_bytes_from_pages": page_size * page_count,
                "free_bytes_estimate": page_size * freelist_count,
                "journal_mode": journal_mode,
                "wal_autocheckpoint": wal_autocheckpoint,
            },
            "counts": counts,
            "dbstat_available": dbstat_available,
            "object_sizes": object_sizes[:80],
            "largest_app_settings": largest_app_settings,
        }

    def clear_llm_debug_payload_settings(self) -> int:
        """Delete stored LLM debug payloads/summaries from app_settings."""
        keys = (
            "llm.last_fetch_payloads",
            "llm.last_fetch_payload_summary",
        )
        placeholders = ",".join("?" for _ in keys)
        cursor = self.execute(f"DELETE FROM app_settings WHERE key IN ({placeholders})", keys)
        self.commit()
        return int(cursor.rowcount if cursor.rowcount is not None else 0)

    def checkpoint_wal_truncate(self) -> list[Any]:
        """Checkpoint and truncate the WAL file."""
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        self.commit()
        self._acquire_write_gate()
        try:
            row = self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            return list(row) if row is not None else []
        finally:
            self._release_write_gate()

    def vacuum_database(self) -> None:
        """Compact the database file using VACUUM."""
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        self.commit()
        self._acquire_write_gate()
        try:
            self.connection.execute("VACUUM")
        finally:
            self._release_write_gate()

    def purge_rejected_cache_files(self, config: dict[str, Any]) -> dict[str, int]:
        """Delete stale cache files for rejected posts after the configured retention."""
        workflow = config.get("workflow", {}) or {}
        retention_days = max(1, int(workflow.get("rejected_thumbnail_retention_days", 7) or 7))
        original_cache_dir = Path(str(config.get("original_cache_dir", ""))).expanduser()
        rejected_thumbnail_dir = Path(str(config.get("rejected_thumbnail_dir", ""))).expanduser()
        modifier = f"-{retention_days} days"

        rows = self.execute(
            """
            SELECT id, thumbnail_path, rejected_thumbnail_path, original_cache_path
            FROM posts
            WHERE status = 'rejected'
              AND rejected_at IS NOT NULL
              AND rejected_at <= datetime('now', ?)
            """,
            (modifier,),
        ).fetchall()

        deleted_files = 0
        cleared_rows = 0
        for row in rows:
            post_id = int(row["id"])
            clear_original = False
            clear_rejected_thumbnail = False
            clear_thumbnail = False

            original_path = _safe_cache_path(row["original_cache_path"], original_cache_dir)
            if original_path is not None:
                if original_path.exists() and original_path.is_file():
                    original_path.unlink()
                    deleted_files += 1
                clear_original = True

            rejected_path = _safe_cache_path(row["rejected_thumbnail_path"], rejected_thumbnail_dir)
            if rejected_path is not None:
                if rejected_path.exists() and rejected_path.is_file():
                    rejected_path.unlink()
                    deleted_files += 1
                clear_rejected_thumbnail = True

            thumbnail_path = _safe_cache_path(row["thumbnail_path"], rejected_thumbnail_dir)
            if thumbnail_path is not None:
                if thumbnail_path.exists() and thumbnail_path.is_file():
                    thumbnail_path.unlink()
                    deleted_files += 1
                clear_thumbnail = True

            if clear_original or clear_rejected_thumbnail or clear_thumbnail:
                self.execute(
                    """
                    UPDATE posts
                    SET original_cache_path = CASE WHEN ? THEN NULL ELSE original_cache_path END,
                        rejected_thumbnail_path = CASE WHEN ? THEN NULL ELSE rejected_thumbnail_path END,
                        thumbnail_path = CASE WHEN ? THEN NULL ELSE thumbnail_path END
                    WHERE id = ?
                    """,
                    (
                        1 if clear_original else 0,
                        1 if clear_rejected_thumbnail else 0,
                        1 if clear_thumbnail else 0,
                        post_id,
                    ),
                )
                cleared_rows += 1

        if cleared_rows:
            self.commit()

        return {
            "retention_days": retention_days,
            "checked_posts": len(rows),
            "deleted_files": deleted_files,
            "cleared_rows": cleared_rows,
        }


def _safe_cache_path(value: object, cache_dir: Path) -> Path | None:
    if not value or not str(cache_dir):
        return None

    path = Path(str(value)).expanduser()
    try:
        resolved_path = path.resolve(strict=False)
        resolved_cache = cache_dir.resolve(strict=False)
        resolved_path.relative_to(resolved_cache)
    except Exception:
        return None

    return resolved_path
