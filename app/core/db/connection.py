from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from app.core.db.write_coordinator import DatabaseWriteCoordinator, coordinator_for_path


_MUTATING_SQL = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP|VACUUM|REINDEX|ANALYZE|ATTACH|DETACH)\b",
    re.IGNORECASE,
)


class DatabaseConnectionMixin:
    """Connection handling, queued writes and retry-safe SQLite helpers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None
        self._write_coordinator: DatabaseWriteCoordinator = coordinator_for_path(path)
        self._write_owner = object()
        self._write_gate_held = False

    def connect(self) -> None:
        self.connection = sqlite3.connect(self.path, timeout=30.0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout = 30000")
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._acquire_write_gate()
        try:
            self.connection.execute("PRAGMA journal_mode = WAL")
        finally:
            self._release_write_gate()
        self.connection.execute("PRAGMA synchronous = NORMAL")

    def close(self) -> None:
        if self.connection is not None:
            try:
                if self.connection.in_transaction:
                    self.connection.rollback()
            finally:
                self.connection.close()
                self.connection = None
                self._release_write_gate()

    @staticmethod
    def _sql_is_mutating(sql: str) -> bool:
        statement = str(sql or "").lstrip()
        while statement.startswith("--"):
            newline = statement.find("\n")
            if newline < 0:
                return False
            statement = statement[newline + 1 :].lstrip()
        if not statement:
            return False

        first = statement.split(None, 1)[0].upper()
        if first in {"SELECT", "EXPLAIN"}:
            return False
        if first == "PRAGMA":
            # Read-only PRAGMAs use either a plain name or function syntax.
            # Assignments and maintenance PRAGMAs are writes/exclusive actions.
            upper = statement.upper()
            return "=" in statement or any(
                name in upper
                for name in ("WAL_CHECKPOINT", "OPTIMIZE", "INCREMENTAL_VACUUM")
            )
        if first == "WITH":
            return _MUTATING_SQL.search(statement) is not None
        return first in {
            "INSERT",
            "UPDATE",
            "DELETE",
            "REPLACE",
            "CREATE",
            "ALTER",
            "DROP",
            "VACUUM",
            "REINDEX",
            "ANALYZE",
            "ATTACH",
            "DETACH",
            "BEGIN",
        }

    def _acquire_write_gate(self) -> None:
        if self._write_gate_held:
            return
        self._write_coordinator.acquire(self._write_owner)
        self._write_gate_held = True

    def _release_write_gate(self) -> None:
        if not self._write_gate_held:
            return
        self._write_gate_held = False
        self._write_coordinator.release(self._write_owner)

    def write_queue_snapshot(self) -> dict[str, int | bool]:
        snapshot = self._write_coordinator.snapshot()
        return {"active": snapshot.active, "waiting": snapshot.waiting}

    def _is_database_locked_error(self, exc: sqlite3.OperationalError) -> bool:
        text = str(exc).lower()
        return "database is locked" in text or "database table is locked" in text

    def _lock_retry_delays(self) -> tuple[float, ...]:
        # The application-level write queue should prevent nearly all writer
        # collisions. Retries remain for external tools and antivirus/indexers,
        # because the outside world still exists and remains inconvenient.
        return (0.05, 0.10, 0.20, 0.35, 0.50, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0)

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Cursor:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        if self._sql_is_mutating(sql):
            self._acquire_write_gate()

        params = tuple(parameters)
        for delay in self._lock_retry_delays():
            try:
                return self.connection.execute(sql, params)
            except sqlite3.OperationalError as exc:
                if not self._is_database_locked_error(exc):
                    if not self.connection.in_transaction:
                        self._release_write_gate()
                    raise
                time.sleep(delay)
        try:
            return self.connection.execute(sql, params)
        except Exception:
            if not self.connection.in_transaction:
                self._release_write_gate()
            raise

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        if self._sql_is_mutating(sql):
            self._acquire_write_gate()

        materialized_rows = [tuple(row) for row in rows]
        for delay in self._lock_retry_delays():
            try:
                return self.connection.executemany(sql, materialized_rows)
            except sqlite3.OperationalError as exc:
                if not self._is_database_locked_error(exc):
                    if not self.connection.in_transaction:
                        self._release_write_gate()
                    raise
                time.sleep(delay)
        try:
            return self.connection.executemany(sql, materialized_rows)
        except Exception:
            if not self.connection.in_transaction:
                self._release_write_gate()
            raise

    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        if _MUTATING_SQL.search(sql_script or "") is not None:
            self._acquire_write_gate()
        try:
            return self.connection.executescript(sql_script)
        except Exception:
            if not self.connection.in_transaction:
                self._release_write_gate()
            raise

    def commit(self) -> None:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        try:
            for delay in self._lock_retry_delays():
                try:
                    self.connection.commit()
                    return
                except sqlite3.OperationalError as exc:
                    if not self._is_database_locked_error(exc):
                        raise
                    time.sleep(delay)
            self.connection.commit()
        except Exception:
            try:
                self.connection.rollback()
            finally:
                self._release_write_gate()
            raise
        finally:
            if self.connection is not None and not self.connection.in_transaction:
                self._release_write_gate()

    def rollback(self) -> None:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        try:
            self.connection.rollback()
        finally:
            self._release_write_gate()
