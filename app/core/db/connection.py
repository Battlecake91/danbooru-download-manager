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


class DatabaseConnectionMixin:
    """Connection handling and retry-safe SQLite execution helpers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def connect(self) -> None:
        # timeout/busy_timeout prevents two GUI/worker connections from
        # immediately losing against each other during short bursts. SQLite can
        # do WAL, but it is not magic. It needs a little patience taught to it.
        self.connection = sqlite3.connect(self.path, timeout=30.0)
        self.connection.row_factory = sqlite3.Row
        self.execute("PRAGMA busy_timeout = 30000")
        self.execute("PRAGMA foreign_keys = ON")
        self.execute("PRAGMA journal_mode = WAL")

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def _is_database_locked_error(self, exc: sqlite3.OperationalError) -> bool:
        text = str(exc).lower()
        return "database is locked" in text or "database table is locked" in text

    def _lock_retry_delays(self) -> tuple[float, ...]:
        # Adds roughly 12 seconds on top of sqlite busy_timeout. Long enough
        # for preview reloads, but short enough to avoid disguising real
        # deadlocks as a meditation exercise.
        return (0.05, 0.10, 0.20, 0.35, 0.50, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0)

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Cursor:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        params = tuple(parameters)
        for delay in self._lock_retry_delays():
            try:
                return self.connection.execute(sql, params)
            except sqlite3.OperationalError as exc:
                if not self._is_database_locked_error(exc):
                    raise
                time.sleep(delay)
        return self.connection.execute(sql, params)

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        materialized_rows = [tuple(row) for row in rows]
        for delay in self._lock_retry_delays():
            try:
                return self.connection.executemany(sql, materialized_rows)
            except sqlite3.OperationalError as exc:
                if not self._is_database_locked_error(exc):
                    raise
                time.sleep(delay)
        return self.connection.executemany(sql, materialized_rows)

    def commit(self) -> None:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        for delay in self._lock_retry_delays():
            try:
                self.connection.commit()
                return
            except sqlite3.OperationalError as exc:
                if not self._is_database_locked_error(exc):
                    raise
                time.sleep(delay)
        self.connection.commit()
