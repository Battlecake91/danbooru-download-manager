from __future__ import annotations

import sys
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app.core.archive_paths import archive_root_path
from app.core.connection_profile import (
    REMOTE_MODE,
    apply_connection_profile,
    connection_profile_exists,
    database_from_config,
    load_connection_profile,
)
from app.core.database import Database
from app.core.paths import ensure_runtime_dirs
from app.gui.app_window import AppWindow
from app.gui.error_handler import install_global_exception_hook
from app.gui.icon_utils import ensure_app_icon
from app.gui.first_run_setup import ConnectionSetupDialog, FirstRunSetupDialog, should_show_first_run_setup


def run_gui(config: dict[str, Any], db: Database | None = None) -> int:
    app = QApplication.instance()
    owns_app = app is None

    if app is None:
        app = QApplication(sys.argv)

    app.setWindowIcon(ensure_app_icon(config))

    error_logger = install_global_exception_hook(config)
    owns_db = db is None

    try:
        if db is None:
            profile = load_connection_profile(config)
            if not connection_profile_exists(config):
                chooser = ConnectionSetupDialog(config, profile)
                if chooser.exec() != QDialog.Accepted:
                    return 0
                profile = load_connection_profile(config)

            while True:
                apply_connection_profile(config, profile)
                db = database_from_config(config)
                try:
                    db.connect()
                    db.initialize_schema()
                    db.apply_app_settings_to_config(config)
                    break
                except Exception as exc:
                    try:
                        db.close()
                    except Exception:
                        pass
                    answer = QMessageBox.question(
                        None,
                        "Database connection failed",
                        f"The configured data source could not be opened:\n\n{exc}\n\nEdit the connection settings?",
                        QMessageBox.Yes | QMessageBox.Cancel,
                        QMessageBox.Yes,
                    )
                    if answer != QMessageBox.Yes:
                        return 1
                    chooser = ConnectionSetupDialog(config, profile)
                    if chooser.exec() != QDialog.Accepted:
                        return 1
                    profile = load_connection_profile(config)

            if profile["mode"] != REMOTE_MODE:
                archive_root_path(config)
            ensure_runtime_dirs(config)

        if db is None:
            raise RuntimeError("Database initialization failed")

        if not bool(getattr(db, "is_remote", False)) and should_show_first_run_setup(db):
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
        if owns_db and db is not None:
            try:
                db.close()
            except Exception:
                pass
        return 1

    if owns_app:
        exit_code = int(app.exec())
    else:
        exit_code = 0

    if owns_db and db is not None:
        db.close()
    return exit_code
