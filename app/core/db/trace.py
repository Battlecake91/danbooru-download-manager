from __future__ import annotations

import logging
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

_registry_lock = threading.Lock()
_loggers: dict[str, logging.Logger] = {}


def trace_logger_for_database(database_path: Path) -> logging.Logger:
    resolved = database_path.expanduser().resolve()
    log_dir = resolved.parent / "logs"
    log_path = log_dir / "database_trace.log"
    key = str(log_path)

    with _registry_lock:
        logger = _loggers.get(key)
        if logger is not None:
            return logger

        log_dir.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(f"ddm.database_trace.{abs(hash(key))}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d | %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
        _loggers[key] = logger
        return logger
