from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Hashable


@dataclass(frozen=True)
class WriteQueueSnapshot:
    active: bool
    waiting: int


class DatabaseWriteCoordinator:
    """FIFO write gate for all SQLite connections using one database file.

    SQLite WAL permits readers while one writer is active, but it still permits
    only one writer at a time. This coordinator serializes application writes
    before SQLite has to resolve the collision itself. A connection keeps the
    gate from its first mutating statement until commit or rollback.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition(threading.Lock())
        self._next_ticket = 0
        self._serving_ticket = 0
        self._owner: Hashable | None = None
        self._owner_depth = 0
        self._waiting = 0

    def acquire(self, owner: Hashable) -> tuple[int, float]:
        with self._condition:
            if self._owner == owner:
                self._owner_depth += 1
                return (-1, 0.0)

            ticket = self._next_ticket
            wait_started = time.monotonic()
            self._next_ticket += 1
            self._waiting += 1
            try:
                self._condition.wait_for(
                    lambda: self._owner is None and ticket == self._serving_ticket
                )
                self._owner = owner
                self._owner_depth = 1
                return (ticket, time.monotonic() - wait_started)
            finally:
                self._waiting -= 1

    def release(self, owner: Hashable) -> None:
        with self._condition:
            if self._owner != owner:
                return
            self._owner_depth -= 1
            if self._owner_depth > 0:
                return
            self._owner = None
            self._owner_depth = 0
            self._serving_ticket += 1
            self._condition.notify_all()

    def snapshot(self) -> WriteQueueSnapshot:
        with self._condition:
            return WriteQueueSnapshot(active=self._owner is not None, waiting=self._waiting)


_registry_lock = threading.Lock()
_registry: dict[str, DatabaseWriteCoordinator] = {}


def coordinator_for_path(path: Path) -> DatabaseWriteCoordinator:
    key = str(path.expanduser().resolve())
    with _registry_lock:
        coordinator = _registry.get(key)
        if coordinator is None:
            coordinator = DatabaseWriteCoordinator()
            _registry[key] = coordinator
        return coordinator
