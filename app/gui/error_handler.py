from __future__ import annotations

import sys
import traceback
from pathlib import Path
from types import TracebackType
from typing import Any


class GuiErrorLogger:
    def __init__(self, config: dict[str, Any]) -> None:
        work_dir = Path(str(config.get("work_dir", ".")))
        self.log_dir = work_dir / "logs"
        self.log_path = self.log_dir / "gui_error.log"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def write_exception(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
        context: str = "Unhandled exception",
    ) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        self.write_text(f"{context}\n{text}")

    def write_text(self, text: str) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n" + "=" * 100 + "\n")
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")


def install_global_exception_hook(config: dict[str, Any]) -> GuiErrorLogger:
    logger = GuiErrorLogger(config)
    old_hook = sys.excepthook

    def excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        try:
            logger.write_exception(exc_type, exc_value, exc_traceback)
        finally:
            old_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = excepthook
    return logger
