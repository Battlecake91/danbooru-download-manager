from __future__ import annotations

import sys
from typing import Any

from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.database import Database
from app.gui.app_window import AppWindow
from app.gui.error_handler import install_global_exception_hook


def run_gui(config: dict[str, Any], db: Database) -> int:
    app = QApplication.instance()
    owns_app = app is None

    if app is None:
        app = QApplication(sys.argv)

    error_logger = install_global_exception_hook(config)

    try:
        window = AppWindow(config, db)
        window.resize(1500, 950)
        window.show()
    except Exception as exc:
        error_logger.write_exception(type(exc), exc, exc.__traceback__, "GUI startup failed")
        QMessageBox.critical(
            None,
            "GUI-Fehler",
            f"GUI konnte nicht gestartet werden:\n{exc}\n\nLog: {error_logger.log_path}",
        )
        return 1

    if owns_app:
        return int(app.exec())

    return 0
