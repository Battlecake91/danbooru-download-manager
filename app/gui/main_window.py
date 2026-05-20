from __future__ import annotations

import sys
from typing import Any

from PySide6.QtWidgets import QApplication

from app.core.database import Database
from app.gui.preview_window import PreviewWindow


def run_gui(config: dict[str, Any], db: Database) -> int:
    app = QApplication.instance()
    owns_app = app is None

    if app is None:
        app = QApplication(sys.argv)

    window = PreviewWindow(config, db)
    window.resize(1400, 900)
    window.show()

    if owns_app:
        return int(app.exec())

    return 0
