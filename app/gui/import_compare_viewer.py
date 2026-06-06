from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, Qt, QUrl, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.i18n.i18n import tr
from app.services.existing_file_import_service import ExistingFileImportCandidate


class _ImagePane(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._pixmap = QPixmap()
        self._fit = True

        layout = QVBoxLayout(self)
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_label.setMinimumSize(240, 240)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.image_label)
        layout.addWidget(self.scroll, stretch=1)

    def set_pixmap(self, pixmap: QPixmap, info: str = "") -> None:
        self._pixmap = pixmap
        self.info_label.setText(info)
        self.refresh()

    def set_message(self, message: str, info: str = "") -> None:
        self._pixmap = QPixmap()
        self.info_label.setText(info)
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText(message)

    def set_fit(self, enabled: bool) -> None:
        self._fit = enabled
        self.refresh()

    def refresh(self) -> None:
        if self._pixmap.isNull():
            return
        if self._fit:
            viewport = self.scroll.viewport().size()
            target = viewport.expandedTo(self.image_label.minimumSize())
            shown = self._pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            shown = self._pixmap
        self.image_label.setText("")
        self.image_label.setPixmap(shown)
        self.image_label.resize(shown.size())

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._fit:
            self.refresh()


class ImportCompareViewer(QDialog):
    decision_changed = Signal(int, bool)

    def __init__(
        self,
        config: dict[str, Any],
        candidates: list[ExistingFileImportCandidate],
        start_index: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.candidates = candidates
        self.index = max(0, min(start_index, len(candidates) - 1)) if candidates else 0
        self.network = QNetworkAccessManager(self)
        self.reply: QNetworkReply | None = None
        self._remote_bytes = QByteArray()

        self.setWindowTitle(tr("import.compare.title", "Compare local and remote image", config=self.config))
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.resize(1450, 900)

        root = QVBoxLayout(self)
        self.header_label = QLabel()
        self.header_label.setAlignment(Qt.AlignCenter)
        self.header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        root.addWidget(self.header_label)

        comparison_headers = QHBoxLayout()
        self.local_heading = QLabel(tr("import.compare.local", "Local file", config=self.config))
        self.local_heading.setAlignment(Qt.AlignCenter)
        self.local_heading.setStyleSheet("font-weight: 700; font-size: 22px;")
        comparison_headers.addWidget(self.local_heading, stretch=1)

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumWidth(180)
        comparison_headers.addWidget(self.status_label)

        self.remote_heading = QLabel(tr("import.compare.remote", "Danbooru candidate", config=self.config))
        self.remote_heading.setAlignment(Qt.AlignCenter)
        self.remote_heading.setStyleSheet("font-weight: 700; font-size: 22px;")
        comparison_headers.addWidget(self.remote_heading, stretch=1)
        root.addLayout(comparison_headers)

        panes = QHBoxLayout()

        self.previous_button = QPushButton("◀")
        self.previous_button.setToolTip(tr("import.compare.previous", "Previous", config=self.config))
        self.previous_button.setFixedWidth(52)
        self.previous_button.setStyleSheet("font-size: 30px; font-weight: bold;")
        self.previous_button.clicked.connect(self.previous_candidate)
        panes.addWidget(self.previous_button, alignment=Qt.AlignVCenter)

        self.local_pane = _ImagePane()
        panes.addWidget(self.local_pane, stretch=1)

        decision_column = QVBoxLayout()
        decision_column.addStretch(1)
        self.mismatch_button = QPushButton(
            tr("import.compare.mark_mismatch", "Mark mismatch", config=self.config)
        )
        self.mismatch_button.setMinimumWidth(150)
        self.mismatch_button.setMinimumHeight(54)
        self.mismatch_button.setStyleSheet(
            "font-weight: bold; font-size: 15px; background: #f2a7a7; color: black;"
        )
        self.mismatch_button.clicked.connect(lambda: self.set_decision(False))
        decision_column.addWidget(self.mismatch_button)

        self.match_button = QPushButton(
            tr("import.compare.mark_match", "Mark match", config=self.config)
        )
        self.match_button.setMinimumWidth(150)
        self.match_button.setMinimumHeight(54)
        self.match_button.setStyleSheet(
            "font-weight: bold; font-size: 15px; background: #a9dfb3; color: black;"
        )
        self.match_button.clicked.connect(lambda: self.set_decision(True))
        decision_column.addWidget(self.match_button)
        decision_column.addStretch(1)
        panes.addLayout(decision_column)

        self.remote_pane = _ImagePane()
        panes.addWidget(self.remote_pane, stretch=1)

        self.next_button = QPushButton("▶")
        self.next_button.setToolTip(tr("import.compare.next", "Next", config=self.config))
        self.next_button.setFixedWidth(52)
        self.next_button.setStyleSheet("font-size: 30px; font-weight: bold;")
        self.next_button.clicked.connect(self.next_candidate)
        panes.addWidget(self.next_button, alignment=Qt.AlignVCenter)

        root.addLayout(panes, stretch=1)

        self.reason_label = QLabel()
        self.reason_label.setWordWrap(True)
        self.reason_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.reason_label)

        controls = QHBoxLayout()
        controls.addStretch(1)
        self.fit_button = QPushButton(tr("import.compare.fit", "Fit images", config=self.config))
        self.fit_button.setCheckable(True)
        self.fit_button.setChecked(True)
        self.fit_button.toggled.connect(self.set_fit_mode)
        controls.addWidget(self.fit_button)

        self.open_remote_button = QPushButton(tr("import.button.open_remote", "Open remote image", config=self.config))
        self.open_remote_button.clicked.connect(self.open_remote_in_browser)
        controls.addWidget(self.open_remote_button)

        controls.addStretch(1)
        self.close_button = QPushButton(tr("common.close", "Close", config=self.config))
        self.close_button.clicked.connect(self.accept)
        controls.addWidget(self.close_button)
        root.addLayout(controls)

        self.previous_shortcut = QShortcut(QKeySequence(Qt.Key_Left), self)
        self.previous_shortcut.activated.connect(self.previous_candidate)
        self.next_shortcut = QShortcut(QKeySequence(Qt.Key_Right), self)
        self.next_shortcut.activated.connect(self.next_candidate)

        self.show_candidate()

    def current_candidate(self) -> ExistingFileImportCandidate | None:
        if not self.candidates or self.index < 0 or self.index >= len(self.candidates):
            return None
        return self.candidates[self.index]

    def show_candidate(self) -> None:
        candidate = self.current_candidate()
        if candidate is None:
            self.header_label.setText(tr("import.compare.no_candidates", "No candidates available.", config=self.config))
            return

        self.abort_remote_request()
        self.header_label.setText(
            tr(
                "import.compare.header",
                "{current}/{total} · Post {post_id} · {filename}",
                config=self.config,
                current=self.index + 1,
                total=len(self.candidates),
                post_id=candidate.post_id or "?",
                filename=candidate.filename,
            )
        )
        self._update_status_label(candidate.confidence)
        local_info = self._resolution_text(candidate.local_width, candidate.local_height)
        remote_info = self._resolution_text(candidate.remote_width, candidate.remote_height)

        local_pixmap = QPixmap(candidate.path)
        if local_pixmap.isNull():
            self.local_pane.set_message(
                tr("import.compare.local_load_failed", "Local image could not be loaded.", config=self.config),
                local_info,
            )
        else:
            self.local_pane.set_pixmap(local_pixmap, local_info)

        preview = QPixmap(candidate.remote_thumbnail_path) if candidate.remote_thumbnail_path else QPixmap()
        if preview.isNull():
            self.remote_pane.set_message(
                tr("import.compare.remote_loading", "Loading remote image…", config=self.config),
                remote_info,
            )
        else:
            self.remote_pane.set_pixmap(preview, remote_info + " · " + tr("import.compare.preview", "preview", config=self.config))

        self.reason_label.setText(
            tr(
                "import.compare.reason",
                "Classification: {confidence}\nReason: {reason}",
                config=self.config,
                confidence=candidate.confidence,
                reason=candidate.reason,
            )
        )
        self.previous_button.setEnabled(self.index > 0)
        self.next_button.setEnabled(self.index + 1 < len(self.candidates))
        self.open_remote_button.setEnabled(bool(candidate.remote_image_url or candidate.remote_post_url))

        if candidate.remote_image_url:
            request = QNetworkRequest(QUrl(candidate.remote_image_url))
            request.setRawHeader(b"User-Agent", b"DanbooruDownloadManager/1.3")
            self.reply = self.network.get(request)
            self.reply.finished.connect(self.remote_download_finished)

    def _update_status_label(self, confidence: str) -> None:
        labels = {
            "high": tr("import.compare.status_match", "Match", config=self.config),
            "mismatch": tr("import.compare.status_mismatch", "Mismatch", config=self.config),
            "questionable": tr("import.compare.status_questionable", "Questionable", config=self.config),
        }
        styles = {
            "high": "background: #a9dfb3; color: black;",
            "mismatch": "background: #f2a7a7; color: black;",
            "questionable": "background: #ffe59a; color: black;",
        }
        self.status_label.setText(labels.get(confidence, confidence.title()))
        self.status_label.setStyleSheet(
            "font-weight: 800; font-size: 18px; padding: 8px 18px; "
            "border: 1px solid #666; border-radius: 6px; " + styles.get(confidence, "")
        )

    def remote_download_finished(self) -> None:
        reply = self.reply
        self.reply = None
        if reply is None:
            return
        try:
            candidate = self.current_candidate()
            if candidate is None:
                return
            if reply.error() != QNetworkReply.NoError:
                if self.remote_pane._pixmap.isNull():
                    self.remote_pane.set_message(
                        tr("import.compare.remote_load_failed", "Remote image could not be loaded.", config=self.config),
                        self._resolution_text(candidate.remote_width, candidate.remote_height),
                    )
                return
            data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                self.remote_pane.set_pixmap(
                    pixmap,
                    self._resolution_text(candidate.remote_width, candidate.remote_height),
                )
        finally:
            reply.deleteLater()

    def abort_remote_request(self) -> None:
        if self.reply is not None:
            self.reply.abort()
            self.reply.deleteLater()
            self.reply = None

    def set_fit_mode(self, enabled: bool) -> None:
        self.local_pane.set_fit(enabled)
        self.remote_pane.set_fit(enabled)
        self.fit_button.setText(
            tr("import.compare.fit", "Fit images", config=self.config)
            if enabled
            else tr("import.compare.actual_size", "100% size", config=self.config)
        )

    def previous_candidate(self) -> None:
        if self.index > 0:
            self.index -= 1
            self.show_candidate()

    def next_candidate(self) -> None:
        if self.index + 1 < len(self.candidates):
            self.index += 1
            self.show_candidate()

    def set_decision(self, matches: bool) -> None:
        candidate = self.current_candidate()
        if candidate is None:
            return
        candidate.importable = matches
        if matches:
            candidate.confidence = "high"
            candidate.reason = tr(
                "import.compare.manual_match_reason",
                "Manually confirmed as matching.",
                config=self.config,
            )
        else:
            candidate.confidence = "mismatch"
            candidate.reason = tr(
                "import.compare.manual_mismatch_reason",
                "Manually rejected as a mismatch.",
                config=self.config,
            )
        self.decision_changed.emit(self.index, matches)
        if self.index + 1 < len(self.candidates):
            self.index += 1
            self.show_candidate()
        else:
            self.show_candidate()

    def open_remote_in_browser(self) -> None:
        from PySide6.QtGui import QDesktopServices

        candidate = self.current_candidate()
        if candidate is None:
            return
        url = candidate.remote_image_url or candidate.remote_post_url
        if url:
            QDesktopServices.openUrl(QUrl(url))

    @staticmethod
    def _resolution_text(width: int | None, height: int | None) -> str:
        return f"{width}×{height}" if width and height else "?"

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.abort_remote_request()
        super().closeEvent(event)
