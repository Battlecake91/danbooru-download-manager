from __future__ import annotations

import sys
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.database import Database
from app.gui.app_window import AppWindow
from app.gui.error_handler import install_global_exception_hook
from app.gui.icon_utils import ensure_app_icon
from app.gui.first_run_setup import FirstRunSetupDialog, should_show_first_run_setup


def run_gui(config: dict[str, Any], db: Database) -> int:
    app = QApplication.instance()
    owns_app = app is None

    if app is None:
        app = QApplication(sys.argv)

    app.setWindowIcon(ensure_app_icon(config))

    error_logger = install_global_exception_hook(config)

    try:
        if should_show_first_run_setup(db):
            setup_dialog = FirstRunSetupDialog(config, db)
            setup_dialog.exec()

        window = AppWindow(config, db)

        screen = app.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            target_width = min(1500, max(1100, available.width() - 80))
            target_height = min(950, max(760, available.height() - 80))
            window.resize(target_width, target_height)
        else:
            window.resize(1500, 950)

        window.show()
        QTimer.singleShot(0, window.refresh_layout_after_show)
        QTimer.singleShot(150, window.refresh_layout_after_show)
    except Exception as exc:
        error_logger.write_exception(type(exc), exc, exc.__traceback__, "GUI startup failed")
        QMessageBox.critical(
            None,
            "GUI error",
            f"GUI could not be started:\n{exc}\n\nLog: {error_logger.log_path}",
        )
        return 1

    if owns_app:
        return int(app.exec())

    return 0
