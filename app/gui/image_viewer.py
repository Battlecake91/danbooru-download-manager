from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.core.database import Database
from app.services.download_service import DownloadService


STATUS_LABELS: dict[str, str] = {
    "new": "Neu",
    "potential": "Hohes Potential",
    "review": "Prüfen",
    "selected_save": "Zum Speichern",
    "auto_rejected": "Automatisch aussortiert",
    "rejected": "Abgelehnt",
    "accepted": "Akzeptiert",
    "already_known": "Bereits bekannt",
    "downloaded": "Heruntergeladen/alt",
    "saved": "Gespeichert",
}


class ImageViewerWindow(QMainWindow):
    status_changed = Signal(int, str)

    def __init__(
        self,
        config: dict[str, Any],
        db: Database,
        post_ids: list[int],
        initial_post_id: int,
    ) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.post_ids = post_ids
        self.current_index = max(0, post_ids.index(initial_post_id)) if initial_post_id in post_ids else 0
        self.download_service = DownloadService(config, db)

        self.current_pixmap: QPixmap | None = None
        self.current_post_id: int | None = None
        self.shortcuts: list[QShortcut] = []

        self.setWindowTitle("Danbooru Manager - Bildbetrachter")
        self.setFocusPolicy(Qt.StrongFocus)

        self.toolbar = QToolBar("Viewer")
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.prev_button = QPushButton("← Vorheriges")
        self.prev_button.clicked.connect(self.previous_post)
        self.toolbar.addWidget(self.prev_button)

        self.next_button = QPushButton("Nächstes →")
        self.next_button.clicked.connect(self.next_post)
        self.toolbar.addWidget(self.next_button)

        self.toolbar.addSeparator()

        self.fit_checkbox = QCheckBox("Einpassen")
        self.fit_checkbox.setChecked(bool((config.get("viewer", {}) or {}).get("fit_to_window", True)))
        self.fit_checkbox.stateChanged.connect(self.refresh_image)
        self.toolbar.addWidget(self.fit_checkbox)

        self.toolbar.addSeparator()

        self.open_original_button = QPushButton("Originalpost")
        self.open_original_button.clicked.connect(self.open_original_post)
        self.toolbar.addWidget(self.open_original_button)

        self.copy_link_button = QPushButton("Link kopieren")
        self.copy_link_button.clicked.connect(self.copy_original_post_url)
        self.toolbar.addWidget(self.copy_link_button)

        self.splitter = QSplitter(Qt.Horizontal)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFocusPolicy(Qt.NoFocus)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 400)
        self.image_label.setFocusPolicy(Qt.NoFocus)

        self.scroll_area.setWidget(self.image_label)
        self.splitter.addWidget(self.scroll_area)

        self.side_panel = QWidget()
        self.side_layout = QVBoxLayout(self.side_panel)

        self.info_label = QLabel()
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_label.setWordWrap(True)
        self.side_layout.addWidget(self.info_label)

        self.status_label = QLabel()
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.side_layout.addWidget(self.status_label)

        self.stars_label = QLabel()
        self.side_layout.addWidget(self.stars_label)

        self.tags_text = QTextEdit()
        self.tags_text.setReadOnly(True)
        self.tags_text.setFocusPolicy(Qt.ClickFocus)
        self.side_layout.addWidget(self.tags_text, stretch=1)

        self.button_row_1 = QHBoxLayout()
        self.potential_button = QPushButton("H Potential")
        self.potential_button.clicked.connect(lambda: self.set_status("potential"))
        self.button_row_1.addWidget(self.potential_button)

        self.review_button = QPushButton("P Prüfen")
        self.review_button.clicked.connect(lambda: self.set_status("review"))
        self.button_row_1.addWidget(self.review_button)

        self.save_select_button = QPushButton("S Speichern vormerken")
        self.save_select_button.clicked.connect(lambda: self.set_status("selected_save"))
        self.button_row_1.addWidget(self.save_select_button)

        self.side_layout.addLayout(self.button_row_1)

        self.button_row_2 = QHBoxLayout()
        self.reject_button = QPushButton("Entf Ablehnen")
        self.reject_button.clicked.connect(lambda: self.set_status("rejected"))
        self.button_row_2.addWidget(self.reject_button)

        self.auto_reject_button = QPushButton("A Auto raus")
        self.auto_reject_button.clicked.connect(lambda: self.set_status("auto_rejected"))
        self.button_row_2.addWidget(self.auto_reject_button)

        self.new_button = QPushButton("N Neu")
        self.new_button.clicked.connect(lambda: self.set_status("new"))
        self.button_row_2.addWidget(self.new_button)

        self.side_layout.addLayout(self.button_row_2)

        self.hint_label = QLabel(
            "Hotkeys: ←/→ blättern | 1-5 Sterne | H/P/S Status | Entf ablehnen | "
            "A auto raus | N neu | O Originalpost"
        )
        self.hint_label.setWordWrap(True)
        self.side_layout.addWidget(self.hint_label)

        self.splitter.addWidget(self.side_panel)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)

        self.setCentralWidget(self.splitter)

        self.install_shortcuts()
        self.load_current_post()

    def install_shortcuts(self) -> None:
        shortcut_map: list[tuple[str, Any]] = [
            ("Left", self.previous_post),
            ("Right", self.next_post),
            ("1", lambda: self.set_stars(1)),
            ("2", lambda: self.set_stars(2)),
            ("3", lambda: self.set_stars(3)),
            ("4", lambda: self.set_stars(4)),
            ("5", lambda: self.set_stars(5)),
            ("H", lambda: self.set_status("potential")),
            ("P", lambda: self.set_status("review")),
            ("S", lambda: self.set_status("selected_save")),
            ("A", lambda: self.set_status("auto_rejected")),
            ("Delete", lambda: self.set_status("rejected")),
            ("N", lambda: self.set_status("new")),
            ("O", self.open_original_post),
        ]

        for key_sequence, callback in shortcut_map:
            shortcut = QShortcut(QKeySequence(key_sequence), self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        self.refresh_image()

    def current_post_id_value(self) -> int | None:
        if 0 <= self.current_index < len(self.post_ids):
            return self.post_ids[self.current_index]
        return None

    def load_current_post(self) -> None:
        post_id = self.current_post_id_value()
        if post_id is None:
            return

        self.current_post_id = post_id
        row = self.db.get_post_detail(post_id)
        if row is None:
            return

        self.setWindowTitle(f"Danbooru Manager - Bildbetrachter - {post_id}")

        self.info_label.setText(
            f"ID: {post_id}\n"
            f"Rating: {row['rating'] or '?'}\n"
            f"Score: {row['score'] if row['score'] is not None else '-'}\n"
            f"Parent: {row['parent_id'] if row['parent_id'] is not None else '-'}\n"
            f"Position: {self.current_index + 1} / {len(self.post_ids)}"
        )

        status = row["status"] or "new"
        self.status_label.setText(f"Status: {STATUS_LABELS.get(status, status)}")

        stars = row["stars"]
        self.stars_label.setText(f"Sterne: {stars if stars is not None else '-'}")

        tags = row["tags"] or ""
        self.tags_text.setPlainText(tags.replace(" ", "\n"))

        image_path = self.ensure_image_path(post_id, row)
        if image_path:
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                self.current_pixmap = pixmap
            else:
                self.current_pixmap = None
                self.image_label.setText(f"Bild konnte nicht geladen werden:\n{image_path}")
        else:
            self.current_pixmap = None
            self.image_label.setText("Keine lokale Bilddatei und Download fehlgeschlagen.")

        self.refresh_image()

    def ensure_image_path(self, post_id: int, row) -> str | None:  # noqa: ANN001
        for candidate in (
            row["original_cache_path"],
            row["original_path"],
            row["final_file_path"],
            row["thumbnail_path"],
            row["rejected_thumbnail_path"],
        ):
            if candidate and Path(str(candidate)).exists():
                return str(candidate)

        return self.download_service.ensure_original_cached(post_id)

    def refresh_image(self) -> None:
        if self.current_pixmap is None:
            return

        if self.fit_checkbox.isChecked():
            viewport_size = self.scroll_area.viewport().size()
            scaled = self.current_pixmap.scaled(
                viewport_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled)
            self.image_label.resize(scaled.size())
        else:
            self.image_label.setPixmap(self.current_pixmap)
            self.image_label.resize(self.current_pixmap.size())

    def previous_post(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_post()

    def next_post(self) -> None:
        if self.current_index < len(self.post_ids) - 1:
            self.current_index += 1
            self.load_current_post()

    def set_status(self, status: str) -> None:
        if self.current_post_id is None:
            return

        self.db.set_post_status(self.current_post_id, status, self.config)
        self.status_label.setText(f"Status: {STATUS_LABELS.get(status, status)}")
        self.status_changed.emit(self.current_post_id, status)

    def set_stars(self, stars: int) -> None:
        if self.current_post_id is None:
            return

        self.db.set_post_review(self.current_post_id, stars=stars)
        self.stars_label.setText(f"Sterne: {stars}")

    def build_original_post_url(self) -> str:
        post_id = self.current_post_id_value()
        base_url = str(self.config.get("base_url", "https://danbooru.donmai.us")).rstrip("/")
        return f"{base_url}/posts/{post_id}"

    def open_original_post(self) -> None:
        webbrowser.open(self.build_original_post_url())

    def copy_original_post_url(self) -> None:
        QGuiApplication.clipboard().setText(self.build_original_post_url())
