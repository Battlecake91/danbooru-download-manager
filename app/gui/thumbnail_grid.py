from __future__ import annotations

import sqlite3
import webbrowser
from typing import Any

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QGuiApplication, QKeyEvent, QMouseEvent, QPixmap
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


TERMINAL_STATUSES = {"rejected", "already_known", "saved"}

STATUS_TEXT: dict[str, str] = {
    "new": "Neu",
    "potential": "Hohes Potential",
    "rejected": "Abgelehnt",
    "already_known": "Bereits bekannt",
    "saved": "Gespeichert",
}


DEFAULT_STATUS_COLORS: dict[str, str] = {
    "new": "#666666",
    "potential": "#2e7d32",
    "rejected": "#b71c1c",
    "already_known": "#6d4c41",
    "saved": "#00838f",
}


class ThumbnailGrid(QScrollArea):
    status_changed = Signal(int, str)
    request_reload = Signal()
    open_viewer_requested = Signal(int)
    final_save_requested = Signal(list)
    category_assign_requested = Signal(list, str)

    def __init__(self, db: Database, config: dict[str, Any]) -> None:
        super().__init__()

        self.db = db
        self.config = config

        gui_config = config.get("gui", {}) or {}
        self.thumbnail_size = int(gui_config.get("thumbnail_size", 340))
        self.card_width_extra = int(gui_config.get("card_width_extra", 100))

        self.columns = 5
        self.items: list[ThumbnailCard] = []
        self.current_posts: list[Any] = []

        self.selected_ids: set[int] = set()
        self.current_index: int = -1
        self.anchor_index: int = -1

        self.setWidgetResizable(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.container = QWidget()
        self.layout = QGridLayout(self.container)
        self.layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.layout.setSpacing(10)
        self.layout.setContentsMargins(10, 10, 10, 10)

        self.setWidget(self.container)

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        self.update_columns()

    def update_columns(self) -> None:
        width = max(1, self.viewport().width())
        card_width = self.thumbnail_size + self.card_width_extra + 10
        new_columns = max(1, width // card_width)
        if new_columns != self.columns:
            self.columns = new_columns
            self.relayout()

    def set_thumbnail_size(self, size: int) -> None:
        if size == self.thumbnail_size:
            return

        self.thumbnail_size = int(size)

        for card in self.items:
            card.set_thumbnail_size(self.thumbnail_size)

        self.update_columns()
        self.relayout()

    def clear(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self.items.clear()
        self.selected_ids.clear()
        self.current_index = -1
        self.anchor_index = -1

    def set_posts(self, posts: list[Any]) -> None:
        old_selected = set(self.selected_ids)
        old_current_id = self.current_card().post_id if self.current_card() else None

        self.current_posts = list(posts)
        self.clear()

        for row in self.current_posts:
            card = ThumbnailCard(self.db, self.config, row, self.thumbnail_size)
            card.status_changed.connect(self.status_changed.emit)
            card.request_reload.connect(self.request_reload.emit)
            card.clicked.connect(self.on_card_clicked)
            card.double_clicked.connect(self.open_viewer_requested.emit)
            card.final_save_requested.connect(lambda post_id: self.final_save_requested.emit([int(post_id)]))
            card.category_assign_requested.connect(self.on_card_category_assign_requested)
            self.items.append(card)

        self.selected_ids = {card.post_id for card in self.items if card.post_id in old_selected}

        if old_current_id is not None:
            for index, card in enumerate(self.items):
                if card.post_id == old_current_id:
                    self.current_index = index
                    break

        if self.current_index < 0 and self.items:
            self.current_index = 0
            self.anchor_index = 0

        self.update_columns()
        self.relayout()
        self.refresh_selection_styles()

    def on_card_category_assign_requested(self, post_id: int, category_name: str) -> None:
        if post_id in self.selected_ids and len(self.selected_ids) > 1:
            post_ids = self.selected_or_current_post_ids()
        else:
            post_ids = [int(post_id)]

        self.category_assign_requested.emit(post_ids, category_name)

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

    def visible_post_ids(self) -> list[int]:
        return [card.post_id for card in self.items]

    def selected_or_current_post_ids(self) -> list[int]:
        cards = self.selected_or_current_cards()
        return [card.post_id for card in cards]

    def update_card_status(self, post_id: int, status: str) -> None:
        for card in self.items:
            if card.post_id == post_id:
                card.apply_external_status(status)
                break

    def update_card_category(self, post_id: int, category_name: str, source: str = "manual") -> None:
        for card in self.items:
            if card.post_id == post_id:
                card.apply_external_category(category_name, source)
                break

    def current_card(self) -> "ThumbnailCard | None":
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index]
        return None

    def on_card_clicked(self, post_id: int, ctrl: bool, shift: bool) -> None:
        self.setFocus()
        clicked_index = self.index_by_post_id(post_id)
        if clicked_index < 0:
            return

        if shift and self.anchor_index >= 0:
            self.select_range(self.anchor_index, clicked_index, additive=ctrl)
            self.current_index = clicked_index
        elif ctrl:
            if post_id in self.selected_ids:
                self.selected_ids.remove(post_id)
            else:
                self.selected_ids.add(post_id)
            self.current_index = clicked_index
            self.anchor_index = clicked_index
        else:
            self.selected_ids = {post_id}
            self.current_index = clicked_index
            self.anchor_index = clicked_index

        self.ensure_current_visible()
        self.refresh_selection_styles()

    def index_by_post_id(self, post_id: int) -> int:
        for index, card in enumerate(self.items):
            if card.post_id == post_id:
                return index
        return -1

    def select_range(self, start: int, end: int, additive: bool = False) -> None:
        if not additive:
            self.selected_ids.clear()

        lo = max(0, min(start, end))
        hi = min(len(self.items) - 1, max(start, end))

        for index in range(lo, hi + 1):
            self.selected_ids.add(self.items[index].post_id)

    def refresh_selection_styles(self) -> None:
        for index, card in enumerate(self.items):
            card.set_selection_state(
                selected=card.post_id in self.selected_ids,
                current=index == self.current_index,
            )

    def ensure_current_visible(self) -> None:
        card = self.current_card()
        if card is not None:
            self.ensureWidgetVisible(card, 30, 30)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self.items:
            super().keyPressEvent(event)
            return

        key = event.key()
        modifiers = event.modifiers()

        if key in {Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_Home, Qt.Key_End}:
            self.handle_navigation_key(key, bool(modifiers & Qt.ShiftModifier))
            event.accept()
            return

        if key == Qt.Key_Space:
            self.toggle_current_selection()
            event.accept()
            return

        if key == Qt.Key_A and modifiers & Qt.ControlModifier:
            self.select_all_visible()
            event.accept()
            return

        if key == Qt.Key_Escape:
            self.clear_selection_keep_current()
            event.accept()
            return

        if key in {Qt.Key_Return, Qt.Key_Enter}:
            card = self.current_card()
            if card:
                self.open_viewer_requested.emit(card.post_id)
            event.accept()
            return

        if key == Qt.Key_F:
            self.final_save_requested.emit(self.selected_or_current_post_ids())
            event.accept()
            return

        if key == Qt.Key_O:
            card = self.current_card()
            if card:
                card.open_original_post()
            event.accept()
            return

        status = self.status_for_key(key)
        if status:
            self.apply_status_to_selection(status)
            event.accept()
            return

        super().keyPressEvent(event)

    def handle_navigation_key(self, key: int, extend_selection: bool) -> None:
        if self.current_index < 0:
            self.current_index = 0
            self.anchor_index = 0

        new_index = self.current_index

        if key == Qt.Key_Left:
            new_index -= 1
        elif key == Qt.Key_Right:
            new_index += 1
        elif key == Qt.Key_Up:
            new_index -= self.columns
        elif key == Qt.Key_Down:
            new_index += self.columns
        elif key == Qt.Key_Home:
            new_index = 0
        elif key == Qt.Key_End:
            new_index = len(self.items) - 1

        new_index = max(0, min(len(self.items) - 1, new_index))

        if extend_selection:
            if self.anchor_index < 0:
                self.anchor_index = self.current_index
            self.select_range(self.anchor_index, new_index, additive=False)
        else:
            self.selected_ids = {self.items[new_index].post_id}
            self.anchor_index = new_index

        self.current_index = new_index
        self.ensure_current_visible()
        self.refresh_selection_styles()

    def toggle_current_selection(self) -> None:
        card = self.current_card()
        if card is None:
            return

        if card.post_id in self.selected_ids:
            self.selected_ids.remove(card.post_id)
        else:
            self.selected_ids.add(card.post_id)

        self.anchor_index = self.current_index
        self.refresh_selection_styles()

    def select_all_visible(self) -> None:
        self.selected_ids = {card.post_id for card in self.items}
        if self.current_index < 0 and self.items:
            self.current_index = 0
        self.anchor_index = self.current_index
        self.refresh_selection_styles()

    def clear_selection_keep_current(self) -> None:
        self.selected_ids.clear()
        self.refresh_selection_styles()

    def selected_or_current_cards(self) -> list["ThumbnailCard"]:
        if self.selected_ids:
            return [card for card in self.items if card.post_id in self.selected_ids]

        card = self.current_card()
        return [card] if card else []

    def apply_status_to_selection(self, status: str) -> None:
        cards = self.selected_or_current_cards()
        if not cards:
            return

        for card in cards:
            card.set_status(status, emit_reload=False)

    def status_for_key(self, key: int) -> str | None:
        mapping = {
            Qt.Key_H: "potential",
            Qt.Key_Delete: "rejected",
            Qt.Key_G: "saved",
            Qt.Key_K: "already_known",
            Qt.Key_N: "new",
        }
        return mapping.get(key)


class ThumbnailCard(QFrame):
    status_changed = Signal(int, str)
    request_reload = Signal()
    clicked = Signal(int, bool, bool)
    double_clicked = Signal(int)
    final_save_requested = Signal(int)
    category_assign_requested = Signal(int, str)

    def __init__(
        self,
        db: Database,
        config: dict[str, Any],
        row: Any,
        thumbnail_size: int,
    ) -> None:
        super().__init__()

        self.db = db
        self.config = config
        self.row = row
        self.post_id = int(self.value("id"))
        self.thumbnail_size = thumbnail_size
        self.is_selected = False
        self.is_current = False
        self.current_status = str(self.value("status") or "new")
        self.current_category = str(self.value("preview_category_name") or "_unmatched")
        self.current_category_source = str(self.value("preview_category_source") or "auto")

        gui_config = config.get("gui", {}) or {}
        self.card_width_extra = int(gui_config.get("card_width_extra", 100))
        self.status_colors = read_status_colors(gui_config)
        self.border_widths = read_border_widths(gui_config)

        self.setFrameShape(QFrame.StyledPanel)
        self.setLineWidth(2)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_context_menu)

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.image_label, alignment=Qt.AlignCenter)

        self.title_label = QLabel()
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(self.title_label)

        self.status_label = QLabel()
        self.layout.addWidget(self.status_label)

        self.category_label = QLabel()
        self.category_label.setWordWrap(True)
        self.category_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(self.category_label)

        self.relation_label = QLabel()
        self.relation_label.setWordWrap(True)
        self.relation_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(self.relation_label)

        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(self.path_label)

        self.tags_label = QLabel()
        self.tags_label.setWordWrap(True)
        self.tags_label.setMaximumHeight(90)
        self.tags_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(self.tags_label)

        self.set_thumbnail_size(thumbnail_size)
        self.apply_row(row)

    def value(self, key: str, default: Any = None) -> Any:
        try:
            return self.row[key]
        except Exception:
            if isinstance(self.row, dict):
                return self.row.get(key, default)
            return default

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            modifiers = event.modifiers()
            self.clicked.emit(
                self.post_id,
                bool(modifiers & Qt.ControlModifier),
                bool(modifiers & Qt.ShiftModifier),
            )
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self.post_id)
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def set_selection_state(self, selected: bool, current: bool) -> None:
        self.is_selected = selected
        self.is_current = current
        self.apply_status_style(self.current_status)

    def set_thumbnail_size(self, size: int) -> None:
        self.thumbnail_size = int(size)
        self.setFixedWidth(self.thumbnail_size + self.card_width_extra)
        self.image_label.setFixedSize(QSize(self.thumbnail_size, self.thumbnail_size))
        self.image_label.setPixmap(self.load_pixmap())

    def apply_row(self, row: Any) -> None:
        self.row = row
        self.post_id = int(self.value("id"))

        pixmap = self.load_pixmap()
        self.image_label.setPixmap(pixmap)

        rating = self.value("rating") or "?"
        score = self.value("score") if self.value("score") is not None else "-"
        parent = self.value("parent_id") if self.value("parent_id") is not None else "-"
        child_marker = " | Childs" if self.value("has_children") else ""

        self.title_label.setText(
            f"ID {self.post_id}\nRating: {rating} | Score: {score}\nParent: {parent}{child_marker}"
        )

        status = self.value("status") or "new"
        self.current_status = str(status)
        self.status_label.setText(f"Status: {STATUS_TEXT.get(status, status)}")

        category = str(self.value("preview_category_name") or "_unmatched")
        category_source = str(self.value("preview_category_source") or "auto")
        self.apply_external_category(category, category_source)

        relation_parts = []
        if int(self.value("known_parent_loaded") or 0):
            relation_parts.append("Parent bekannt")
        child_count = int(self.value("known_child_count") or 0)
        if child_count:
            relation_parts.append(f"{child_count} Child(s) bekannt")

        if relation_parts:
            self.relation_label.setText("Verwandt: " + ", ".join(relation_parts))
            self.relation_label.show()
        else:
            self.relation_label.clear()
            self.relation_label.hide()

        final_path = self.value("final_file_path") or self.value("final_directory") or ""
        if final_path:
            self.path_label.setText(f"Pfad: {final_path}")
            self.path_label.show()
        else:
            self.path_label.clear()
            self.path_label.hide()

        tags = self.value("tags") or ""
        compact_tags = self.compact_tags(str(tags))
        self.tags_label.setText(compact_tags)

        self.apply_status_style(status)

    def apply_external_status(self, status: str) -> None:
        self.current_status = status
        self.status_label.setText(f"Status: {STATUS_TEXT.get(status, status)}")
        self.apply_status_style(status)

    def apply_external_category(self, category_name: str, source: str = "manual") -> None:
        self.current_category = category_name or "_unmatched"
        self.current_category_source = source or "auto"

        source_label = "manuell" if self.current_category_source == "manual" else "auto"
        self.category_label.setText(f"Kategorie: {self.current_category} ({source_label})")

        if self.current_category_source == "manual":
            self.category_label.setStyleSheet(
                "QLabel { color: #9be7ff; font-weight: bold; }"
            )
        elif self.current_category == "_unmatched":
            self.category_label.setStyleSheet(
                "QLabel { color: #ffb000; font-weight: bold; }"
            )
        else:
            self.category_label.setStyleSheet(
                "QLabel { color: #cccccc; }"
            )

    def load_pixmap(self) -> QPixmap:
        candidates = [
            self.value("thumbnail_path"),
            self.value("rejected_thumbnail_path"),
        ]

        for candidate in candidates:
            if candidate:
                pixmap = QPixmap(str(candidate))
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
        max_tags = 28 if self.thumbnail_size >= 260 else 20
        if len(parts) <= max_tags:
            return " ".join(parts)
        return " ".join(parts[:max_tags]) + " ..."

    def apply_status_style(self, status: str) -> None:
        color = self.status_colors.get(status, self.status_colors["new"])
        border_width = self.border_widths["default"]
        background = "#202020"
        label_color = "#dddddd"

        if status in {"downloaded", "already_known"}:
            border_width = self.border_widths["downloaded"]
        elif status == "saved":
            border_width = self.border_widths["saved"]
        elif status in {"rejected", "auto_rejected"}:
            border_width = self.border_widths["rejected"]
        elif status != "new":
            border_width = self.border_widths["marked"]

        if status in TERMINAL_STATUSES:
            background = "#181818"
            label_color = "#777777"

        if self.is_selected:
            background = "#2f3744" if status not in TERMINAL_STATUSES else "#252a33"

        if self.is_current:
            border_width = max(border_width, 4)

        self.setStyleSheet(
            f"""
            ThumbnailCard {{
                border: {border_width}px solid {color};
                border-radius: 8px;
                background: {background};
            }}
            QLabel {{
                color: {label_color};
            }}
            """
        )

    def open_context_menu(self, position) -> None:  # noqa: ANN001
        menu = QMenu(self)

        open_viewer_action = QAction("Bildbetrachter öffnen (Enter/Doppelklick)", self)
        open_viewer_action.triggered.connect(lambda: self.double_clicked.emit(self.post_id))
        menu.addAction(open_viewer_action)

        final_save_action = QAction("Final speichern (F)", self)
        final_save_action.triggered.connect(lambda: self.final_save_requested.emit(self.post_id))
        menu.addAction(final_save_action)

        category_menu = QMenu("Kategorie setzen", self)
        category_names = self.db.list_category_names()
        if not category_names:
            disabled = QAction("Keine Kategorien vorhanden", self)
            disabled.setEnabled(False)
            category_menu.addAction(disabled)
        for category_name in category_names:
            action = QAction(category_name, self)
            action.triggered.connect(
                lambda checked=False, c=category_name: self.category_assign_requested.emit(self.post_id, c)
            )
            category_menu.addAction(action)
        menu.addMenu(category_menu)

        menu.addSeparator()

        open_original_action = QAction("Originalpost öffnen (O)", self)
        open_original_action.triggered.connect(self.open_original_post)
        menu.addAction(open_original_action)

        copy_url_action = QAction("Originalpost-Link kopieren", self)
        copy_url_action.triggered.connect(self.copy_original_post_url)
        menu.addAction(copy_url_action)

        copy_id_action = QAction("Post-ID kopieren", self)
        copy_id_action.triggered.connect(self.copy_post_id)
        menu.addAction(copy_id_action)

        copy_tags_action = QAction("Tags kopieren", self)
        copy_tags_action.triggered.connect(self.copy_tags)
        menu.addAction(copy_tags_action)

        menu.addSeparator()

        actions: list[tuple[str, str]] = [
            ("High Potential [H]", "potential"),
            ("Ablehnen [Entf]", "rejected"),
            ("Als gespeichert markieren [G]", "saved"),
            ("Bereits bekannt [K]", "already_known"),
            ("Neu zurücksetzen [N]", "new"),
        ]

        for label, status in actions:
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, s=status: self.set_status(s, emit_reload=False))
            menu.addAction(action)

        menu.exec(self.mapToGlobal(position))

    def build_original_post_url(self) -> str:
        base_url = str(self.config.get("base_url", "https://danbooru.donmai.us")).rstrip("/")
        return f"{base_url}/posts/{self.post_id}"

    def open_original_post(self) -> None:
        webbrowser.open(self.build_original_post_url())

    def copy_original_post_url(self) -> None:
        QGuiApplication.clipboard().setText(self.build_original_post_url())

    def copy_post_id(self) -> None:
        QGuiApplication.clipboard().setText(str(self.post_id))

    def copy_tags(self) -> None:
        tags = self.value("tags") or ""
        QGuiApplication.clipboard().setText(str(tags))

    def set_status(self, status: str, emit_reload: bool = False) -> None:
        self.db.set_post_status(self.post_id, status, self.config)
        self.current_status = status
        self.status_label.setText(f"Status: {STATUS_TEXT.get(status, status)}")
        self.apply_status_style(status)
        self.status_changed.emit(self.post_id, status)


def read_status_colors(gui_config: dict[str, Any]) -> dict[str, str]:
    colors = dict(DEFAULT_STATUS_COLORS)
    configured = gui_config.get("status_colors", {}) or {}

    for status, color in configured.items():
        if isinstance(status, str) and isinstance(color, str) and color.strip():
            colors[status] = color.strip()

    return colors


def read_border_widths(gui_config: dict[str, Any]) -> dict[str, int]:
    configured = gui_config.get("status_border_width", {}) or {}

    return {
        "default": int(configured.get("default", 2)),
        "marked": int(configured.get("marked", 3)),
        "downloaded": int(configured.get("downloaded", 4)),
        "saved": int(configured.get("saved", 4)),
        "rejected": int(configured.get("rejected", 3)),
    }
