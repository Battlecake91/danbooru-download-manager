from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.database import Database


STATUS_TEXT: dict[str, str] = {
    "new": "Neu",
    "potential": "Hohes Potential",
    "review": "Prüfen",
    "auto_rejected": "Auto aussortiert",
    "rejected": "Abgelehnt",
    "accepted": "Akzeptiert",
    "downloaded": "Geladen",
    "saved": "Gespeichert",
}


STATUS_STYLE: dict[str, str] = {
    "new": "border: 2px solid #666;",
    "potential": "border: 3px solid #2e7d32;",
    "review": "border: 3px solid #f9a825;",
    "auto_rejected": "border: 3px solid #546e7a;",
    "rejected": "border: 3px solid #b71c1c;",
    "accepted": "border: 3px solid #1565c0;",
    "downloaded": "border: 3px solid #6a1b9a;",
    "saved": "border: 3px solid #00838f;",
}


class ThumbnailGrid(QScrollArea):
    status_changed = Signal(int, str)

    def __init__(self, db: Database) -> None:
        super().__init__()

        self.db = db
        self.thumbnail_size = 180
        self.columns = 5
        self.items: list[ThumbnailCard] = []

        self.setWidgetResizable(True)

        self.container = QWidget()
        self.layout = QGridLayout(self.container)
        self.layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.layout.setSpacing(10)
        self.layout.setContentsMargins(10, 10, 10, 10)

        self.setWidget(self.container)

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        width = max(1, self.viewport().width())
        card_width = self.thumbnail_size + 70
        new_columns = max(1, width // card_width)
        if new_columns != self.columns:
            self.columns = new_columns
            self.relayout()

    def clear(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self.items.clear()

    def set_posts(self, posts: list[sqlite3.Row]) -> None:
        self.clear()

        for row in posts:
            card = ThumbnailCard(self.db, row, self.thumbnail_size)
            card.status_changed.connect(self.status_changed.emit)
            self.items.append(card)

        self.relayout()

    def relayout(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        for index, card in enumerate(self.items):
            row = index // self.columns
            col = index % self.columns
            self.layout.addWidget(card, row, col)


class ThumbnailCard(QFrame):
    status_changed = Signal(int, str)

    def __init__(self, db: Database, row: sqlite3.Row, thumbnail_size: int) -> None:
        super().__init__()

        self.db = db
        self.row = row
        self.post_id = int(row["id"])
        self.thumbnail_size = thumbnail_size

        self.setFrameShape(QFrame.StyledPanel)
        self.setLineWidth(2)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_context_menu)

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedWidth(thumbnail_size + 60)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedSize(QSize(thumbnail_size, thumbnail_size))
        self.layout.addWidget(self.image_label, alignment=Qt.AlignCenter)

        self.title_label = QLabel()
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(self.title_label)

        self.status_label = QLabel()
        self.layout.addWidget(self.status_label)

        self.tags_label = QLabel()
        self.tags_label.setWordWrap(True)
        self.tags_label.setMaximumHeight(70)
        self.tags_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(self.tags_label)

        self.apply_row(row)

    def apply_row(self, row: sqlite3.Row) -> None:
        self.row = row
        self.post_id = int(row["id"])

        pixmap = self.load_pixmap(row["thumbnail_path"])
        self.image_label.setPixmap(pixmap)

        rating = row["rating"] or "?"
        score = row["score"] if row["score"] is not None else "-"
        parent = row["parent_id"] if row["parent_id"] is not None else "-"
        child_marker = " | Childs" if row["has_children"] else ""

        self.title_label.setText(
            f"ID {self.post_id}\nRating: {rating} | Score: {score}\nParent: {parent}{child_marker}"
        )

        status = row["status"] or "new"
        self.status_label.setText(f"Status: {STATUS_TEXT.get(status, status)}")

        tags = row["tags"] or ""
        compact_tags = self.compact_tags(tags)
        self.tags_label.setText(compact_tags)

        self.apply_status_style(status)

    def load_pixmap(self, thumbnail_path: str | None) -> QPixmap:
        if thumbnail_path:
            pixmap = QPixmap(thumbnail_path)
            if not pixmap.isNull():
                return pixmap.scaled(
                    self.thumbnail_size,
                    self.thumbnail_size,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )

        placeholder = QPixmap(self.thumbnail_size, self.thumbnail_size)
        placeholder.fill(Qt.darkGray)
        return placeholder

    def compact_tags(self, tags: str) -> str:
        parts = tags.split()
        if len(parts) <= 24:
            return " ".join(parts)
        return " ".join(parts[:24]) + " ..."

    def apply_status_style(self, status: str) -> None:
        border = STATUS_STYLE.get(status, STATUS_STYLE["new"])
        self.setStyleSheet(
            f"""
            ThumbnailCard {{
                {border}
                border-radius: 8px;
                background: #202020;
            }}
            QLabel {{
                color: #dddddd;
            }}
            """
        )

    def open_context_menu(self, position) -> None:  # noqa: ANN001
        menu = QMenu(self)

        actions: list[tuple[str, str]] = [
            ("Hohes Potential", "potential"),
            ("Prüfen", "review"),
            ("Automatisch aussortiert", "auto_rejected"),
            ("Ablehnen", "rejected"),
            ("Akzeptieren", "accepted"),
            ("Neu zurücksetzen", "new"),
        ]

        for label, status in actions:
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, s=status: self.set_status(s))
            menu.addAction(action)

        menu.exec(self.mapToGlobal(position))

    def set_status(self, status: str) -> None:
        self.db.set_post_status(self.post_id, status)

        # Row lokal nicht mutieren können wir bei sqlite3.Row nicht sauber.
        # Also minimal optisch aktualisieren.
        self.status_label.setText(f"Status: {STATUS_TEXT.get(status, status)}")
        self.apply_status_style(status)
        self.status_changed.emit(self.post_id, status)
