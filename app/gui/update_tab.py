from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

from app.services.update_service import (
    check_for_update,
    download_update_asset,
    packaged_update_requirement_message,
    portable_update_available,
    start_portable_update,
    updates_dir,
)
from app.version import __version__


class UpdateTab(QWidget):
    """Portable update and future help tab."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        self.config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Updates & Help")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        intro = QLabel(
            "Check for new GitHub release builds and install portable updates. "
            "The updater replaces program files only and keeps local databases, logs, "
            "ratings, categories and downloaded metadata untouched."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 13px; color: #c7c7c7;")
        layout.addWidget(intro)

        help_box = QFrame()
        help_box.setFrameShape(QFrame.Shape.StyledPanel)
        help_box.setStyleSheet(
            "QFrame { border: 1px solid #555; border-radius: 8px; padding: 10px; }"
        )
        help_layout = QVBoxLayout(help_box)

        help_title = QLabel("Help section")
        help_title.setStyleSheet("font-weight: bold;")
        help_layout.addWidget(help_title)

        help_text = QLabel(
            "More built-in help will follow in a future version. For now, use the README "
            "and the documents in /docs for setup, configuration and workflow notes."
        )
        help_text.setWordWrap(True)
        help_layout.addWidget(help_text)

        layout.addWidget(help_box)

        info = QLabel(f"Installed version: {__version__}")
        info.setStyleSheet("font-weight: bold;")
        layout.addWidget(info)

        button_row = QHBoxLayout()
        self.check_button = QPushButton("Check for updates")
        self.check_button.clicked.connect(self.check_for_updates)
        button_row.addWidget(self.check_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        note = QLabel(
            "Portable self-updates are only active in the packaged application. "
            "When running from source, this tab can show the workflow but will not overwrite "
            "your checkout. Which is rude, but also sane."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #9aa0a6;")
        layout.addWidget(note)

        layout.addStretch(1)

    def check_for_updates(self) -> None:
        if not portable_update_available():
            QMessageBox.information(
                self,
                "Update check",
                packaged_update_requirement_message(),
            )
            return

        self.check_button.setEnabled(False)
        QApplication.setOverrideCursor(QtCursorBusy.cursor())
        QApplication.processEvents()

        try:
            info = check_for_update()
        except Exception as exc:
            QMessageBox.critical(self, "Update check failed", str(exc))
            self.check_button.setEnabled(True)
            QApplication.restoreOverrideCursor()
            return
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

        self.check_button.setEnabled(True)

        if not info.is_newer:
            QMessageBox.information(
                self,
                "No update available",
                f"Danbooru Manager {info.current_version} is already up to date.\n"
                f"Latest GitHub release: {info.tag_name}",
            )
            return

        answer = QMessageBox.question(
            self,
            "Update available",
            "A newer Danbooru Manager release is available.\n\n"
            f"Current version: {info.current_version}\n"
            f"Latest version:  {info.latest_version}\n"
            f"Asset: {info.asset.name}\n\n"
            "Download and install this update now? The application will close and restart.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        progress = QProgressDialog("Downloading update...", "Cancel", 0, 100, self)
        progress.setWindowTitle("Updating Danbooru Manager")
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)

        def on_progress(downloaded: int, total: int) -> None:
            if total > 0:
                progress.setValue(min(100, int(downloaded * 100 / total)))
            else:
                progress.setValue(0)
            QApplication.processEvents()
            if progress.wasCanceled():
                raise RuntimeError("Update download was canceled.")

        try:
            zip_path = download_update_asset(info, updates_dir(self.config), on_progress)
            progress.setLabelText("Starting updater...")
            progress.setValue(100)
            QApplication.processEvents()
            start_portable_update(zip_path, self.config)
        except Exception as exc:
            progress.close()
            QMessageBox.critical(self, "Update failed", str(exc))
            return

        progress.close()
        QApplication.quit()


class QtCursorBusy:
    """Tiny indirection so importing QtCore stays local to this tab."""

    @staticmethod
    def cursor():
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QCursor

        return QCursor(Qt.CursorShape.WaitCursor)
