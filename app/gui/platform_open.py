from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def open_local_path(path: Path) -> bool:
    """Open a local file or directory with the operating system default app."""
    return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))))
