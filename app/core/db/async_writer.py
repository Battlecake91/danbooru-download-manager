from __future__ import annotations

import json
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.database import Database


@dataclass(frozen=True)
class _SettingWrite:
    key: str
    value: Any


class AsyncSettingWriter:
    """Serialize small GUI setting writes on a dedicated background thread."""

    def __init__(self, database_file: Path) -> None:
        self.database_file = Path(database_file).resolve()
        self._queue: queue.Queue[_SettingWrite] = queue.Queue()
        self._thread = threading.Thread(
            target=self._run,
            name=f"AsyncSettingWriter:{self.database_file.name}",
            daemon=True,
        )
        self._thread.start()

    def enqueue(self, key: str, value: Any) -> None:
        self._queue.put(_SettingWrite(str(key), value))

    def _run(self) -> None:
        db = Database(self.database_file)
        db.connect()
        try:
            while True:
                item = self._queue.get()
                try:
                    encoded = json.dumps(item.value, ensure_ascii=False)
                    db.execute(
                        """
                        INSERT INTO app_settings (key, value, updated_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(key) DO UPDATE SET
                            value = excluded.value,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (item.key, encoded),
                    )
                    db.commit()
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                finally:
                    self._queue.task_done()
        finally:
            db.close()


_WRITERS: dict[Path, AsyncSettingWriter] = {}
_WRITERS_LOCK = threading.Lock()


def writer_for_database(database_file: Path) -> AsyncSettingWriter:
    resolved = Path(database_file).resolve()
    with _WRITERS_LOCK:
        writer = _WRITERS.get(resolved)
        if writer is None:
            writer = AsyncSettingWriter(resolved)
            _WRITERS[resolved] = writer
        return writer


def enqueue_app_setting(database_file: Path, key: str, value: Any) -> None:
    writer_for_database(database_file).enqueue(key, value)
