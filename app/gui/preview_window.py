from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.core.database import Database
from app.gui.thumbnail_grid import ThumbnailGrid


STATUS_LABELS: dict[str, str] = {
    "all": "Alle",
    "new": "Neu",
    "potential": "Hohes Potential",
    "review": "Prüfen",
    "auto_rejected": "Automatisch aussortiert",
    "rejected": "Abgelehnt",
    "accepted": "Akzeptiert",
    "downloaded": "Heruntergeladen",
    "saved": "Gespeichert",
}


class PreviewWindow(QMainWindow):
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.current_limit = 500
        self.current_offset = 0

        self.setWindowTitle("Danbooru Manager - Preview")

        self.toolbar = QToolBar("Preview")
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.reload_button = QPushButton("Neu laden")
        self.reload_button.clicked.connect(self.reload_posts)
        self.toolbar.addWidget(self.reload_button)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Status: "))
        self.status_filter = QComboBox()
        for status, label in STATUS_LABELS.items():
            self.status_filter.addItem(label, status)
        self.status_filter.currentIndexChanged.connect(self.reload_posts)
        self.toolbar.addWidget(self.status_filter)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Suche: "))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("ID oder Tag suchen...")
        self.search_edit.returnPressed.connect(self.reload_posts)
        self.search_edit.setMinimumWidth(260)
        self.toolbar.addWidget(self.search_edit)

        self.search_button = QPushButton("Suchen")
        self.search_button.clicked.connect(self.reload_posts)
        self.toolbar.addWidget(self.search_button)

        self.clear_search_button = QPushButton("Leeren")
        self.clear_search_button.clicked.connect(self.clear_search)
        self.toolbar.addWidget(self.clear_search_button)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Limit: "))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(50, 5000)
        self.limit_spin.setSingleStep(50)
        self.limit_spin.setValue(self.current_limit)
        self.limit_spin.valueChanged.connect(self.reload_posts)
        self.toolbar.addWidget(self.limit_spin)

        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout(self.main_widget)

        self.info_label = QLabel("")
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.main_layout.addWidget(self.info_label)

        self.grid = ThumbnailGrid(self.db, self.config)
        self.grid.status_changed.connect(self.on_status_changed)
        self.main_layout.addWidget(self.grid)

        self.setCentralWidget(self.main_widget)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.reload_posts()

    def selected_status(self) -> str:
        return str(self.status_filter.currentData())

    def current_search_text(self) -> str | None:
        text = self.search_edit.text().strip()
        return text or None

    def clear_search(self) -> None:
        self.search_edit.clear()
        self.reload_posts()

    def reload_posts(self) -> None:
        status = self.selected_status()
        text_filter = self.current_search_text()
        self.current_limit = int(self.limit_spin.value())

        total = self.db.count_preview_posts(status, text_filter)
        posts = self.db.fetch_preview_posts(
            status_filter=status,
            text_filter=text_filter,
            limit=self.current_limit,
            offset=self.current_offset,
        )

        self.grid.set_posts(posts)
        self.info_label.setText(
            f"Angezeigt: {len(posts)} / Treffer: {total} | Filter: {STATUS_LABELS.get(status, status)}"
        )
        self.status_bar.showMessage("Preview geladen")

    def on_status_changed(self, post_id: int, status: str) -> None:
        self.status_bar.showMessage(f"Post {post_id} → {STATUS_LABELS.get(status, status)}")
