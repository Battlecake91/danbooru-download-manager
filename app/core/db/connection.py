from __future__ import annotations

import re
import sqlite3
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Iterable

from app.core.db.trace import trace_logger_for_database
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
        self._write_ticket: int | None = None
        self._trace_logger = trace_logger_for_database(path)


    def _trace(self, message: str) -> None:
        thread = __import__("threading").current_thread()
        connection_name = f"{self.__class__.__name__}@{id(self):x}"
        self._trace_logger.info(
            "thread=%s/%s | connection=%s | %s",
            thread.name,
            thread.ident,
            connection_name,
            message,
        )

    def connect(self) -> None:
        self._trace(f"CONNECT begin path={self.path}")
        connect_started = time.monotonic()
        self.connection = sqlite3.connect(self.path, timeout=30.0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout = 30000")
        self.connection.execute("PRAGMA foreign_keys = ON")

        # journal_mode is persistent for the database file. Re-applying WAL on
        # every connection is not harmless: SQLite may need an exclusive schema
        # lock for the assignment. A short-lived GUI worker could then acquire
        # the application write gate, block inside PRAGMA journal_mode=WAL and
        # prevent the active Fetch connection from obtaining its next write
        # slot. Read the current mode first and only change it during initial
        # database bootstrap or when an external tool changed it.
        journal_row = self.connection.execute("PRAGMA journal_mode").fetchone()
        journal_mode = str(journal_row[0] if journal_row else "").lower()
        if journal_mode != "wal":
            self._acquire_write_gate()
            try:
                self.connection.execute("PRAGMA journal_mode = WAL")
            finally:
                self._release_write_gate()

        self.connection.execute("PRAGMA synchronous = NORMAL")
        self._trace(f"CONNECT done duration={time.monotonic() - connect_started:.3f}s journal={journal_mode or 'unknown'}")

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

    def _acquire_write_gate(self, operation: str = "WRITE") -> None:
        if self._write_gate_held:
            return
        snapshot = self._write_coordinator.snapshot()

        # A synchronous Qt-main-thread write must never wait behind a background
        # Fetch writer. Besides freezing the UI, the main connection can hold
        # read state that makes a later SQLite lock upgrade block indefinitely.
        # Background workers remain serialized normally; GUI writes should use
        # the dedicated async writers. Fail fast and leave the Fetch queue free.
        if threading.current_thread() is threading.main_thread() and snapshot.active:
            stack = "".join(traceback.format_stack(limit=14)).replace("\n", " | ")
            self._trace(
                f"MAIN_THREAD_WRITE_REJECTED operation={operation} "
                f"active={snapshot.active} waiting={snapshot.waiting} stack={stack}"
            )
            raise RuntimeError(
                "A database write was requested from the GUI thread while a "
                "background writer was active. The operation was cancelled to "
                "protect the running Fetch. See database_trace.log for the caller."
            )

        self._trace(f"WRITE_GATE wait operation={operation} active={snapshot.active} waiting={snapshot.waiting}")
        ticket, waited = self._write_coordinator.acquire(self._write_owner)
        self._write_ticket = ticket
        self._write_gate_held = True
        self._trace(f"WRITE_GATE acquired ticket={ticket} waited={waited:.3f}s")

    def _release_write_gate(self) -> None:
        if not self._write_gate_held:
            return
        ticket = self._write_ticket
        self._write_gate_held = False
        self._write_ticket = None
        self._write_coordinator.release(self._write_owner)
        self._trace(f"WRITE_GATE released ticket={ticket}")

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
        is_mutating = self._sql_is_mutating(sql)
        operation = str(sql or "").lstrip().split(None, 1)[0].upper() if str(sql or "").strip() else "EMPTY"
        if is_mutating:
            self._acquire_write_gate(operation)

        params = tuple(parameters)
        started = time.monotonic()
        main_thread_autocommit = (
            is_mutating
            and operation != "BEGIN"
            and threading.current_thread() is threading.main_thread()
            and not self.connection.in_transaction
        )
        try:
            for delay in self._lock_retry_delays():
                try:
                    cursor = self.connection.execute(sql, params)
                    if main_thread_autocommit:
                        # GUI actions are expected to be short, standalone writes.
                        # Keeping their transaction open until an eventual caller
                        # commit lets an overlooked code path monopolize the global
                        # write gate and starve every later Fetch. Commit immediately
                        # unless the caller explicitly opened a transaction first.
                        self.connection.commit()
                        self._trace(
                            f"MAIN_THREAD_AUTOCOMMIT operation={operation} "
                            f"duration={time.monotonic() - started:.3f}s"
                        )
                        self._release_write_gate()
                    if is_mutating and time.monotonic() - started >= 0.100:
                        self._trace(f"SQL slow operation={operation} duration={time.monotonic() - started:.3f}s in_transaction={self.connection.in_transaction}")
                    if is_mutating and not self.connection.in_transaction:
                        # Some mutating statements commit implicitly or do not
                        # open a transaction. They must not leave the process-wide
                        # gate owned while SQLite itself is already idle.
                        self._release_write_gate()
                    return cursor
                except sqlite3.OperationalError as exc:
                    if not self._is_database_locked_error(exc):
                        raise
                    self._trace(f"SQL locked operation={operation} retry_delay={delay:.2f}s error={exc}")
                    time.sleep(delay)
            return self.connection.execute(sql, params)
        except Exception as exc:
            self._trace(f"SQL failed operation={operation} duration={time.monotonic() - started:.3f}s error={type(exc).__name__}: {exc}")
            # A failed mutating statement can leave SQLite inside a transaction.
            # If the caller catches the exception without rolling back, the
            # application write gate would otherwise remain owned forever and
            # every later Fetch would start with active=True. Always unwind the
            # failed write here; callers that need savepoints must handle them
            # explicitly above this helper.
            if is_mutating:
                try:
                    if self.connection.in_transaction:
                        self.connection.rollback()
                        self._trace(f"SQL failure rollback operation={operation}")
                finally:
                    self._release_write_gate()
            raise

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        if self._sql_is_mutating(sql):
            operation = str(sql or "").lstrip().split(None, 1)[0].upper() if str(sql or "").strip() else "EXECUTEMANY"
            self._acquire_write_gate(operation)

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
            try:
                if self.connection.in_transaction:
                    self.connection.rollback()
                    self._trace(f"EXECUTEMANY failure rollback operation={operation}")
            finally:
                self._release_write_gate()
            raise

    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        if _MUTATING_SQL.search(sql_script or "") is not None:
            self._acquire_write_gate("SCRIPT")
        try:
            return self.connection.executescript(sql_script)
        except Exception:
            try:
                if self.connection.in_transaction:
                    self.connection.rollback()
                    self._trace("SCRIPT failure rollback")
            finally:
                self._release_write_gate()
            raise

    def commit(self) -> None:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        started = time.monotonic()
        self._trace(f"COMMIT begin in_transaction={self.connection.in_transaction} ticket={self._write_ticket}")
        try:
            for delay in self._lock_retry_delays():
                try:
                    self.connection.commit()
                    self._trace(f"COMMIT done duration={time.monotonic() - started:.3f}s")
                    return
                except sqlite3.OperationalError as exc:
                    if not self._is_database_locked_error(exc):
                        raise
                    self._trace(f"COMMIT locked retry_delay={delay:.2f}s error={exc}")
                    time.sleep(delay)
            self.connection.commit()
            self._trace(f"COMMIT done duration={time.monotonic() - started:.3f}s after_retries")
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
