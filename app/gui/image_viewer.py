from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
import faulthandler
import os
import threading
import time
import traceback
import webbrowser
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QRectF, Signal, QTimer
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QGuiApplication, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from app.core.category_engine import CategoryMatch
from app.core.database import Database
from app.services.download_service import DownloadService
from app.danbooru.api import DanbooruApi
from app.gui.icon_utils import ensure_app_icon
from app.i18n.i18n import tr
from app.gui.tag_display import TypedTagListWidget, typed_tags_for_post
from app.services.final_save_service import AlreadySavedError, FinalSaveService
from app.services.post_import_service import PostImportService


STATUS_LABELS: dict[str, str] = {
    "new": "New",
    "potential": "High Potential",
    "rejected": "Rejected",
    "already_known": "Already known",
    "saved": "Saved",
}


STATUS_COLORS: dict[str, str] = {
    "new": "#6c757d",
    "potential": "#3ddc84",
    "rejected": "#ff4d4d",
    "already_known": "#9b5de5",
    "saved": "#ffd166",
}


class StatusChip(QLabel):
    clicked = Signal(str)

    def __init__(self, status: str, text: str) -> None:
        super().__init__(text)
        self.status = status
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(30)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Set status. Clicking the active status resets it to New.")

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.status)
            event.accept()
            return
        super().mousePressEvent(event)


class StatusChipBar(QWidget):
    status_clicked = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._labels: dict[str, StatusChip] = {}
        self.active_status = "new"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        for status in ("new", "potential", "rejected", "saved"):
            label = StatusChip(status, STATUS_LABELS.get(status, status))
            label.setObjectName(f"statusChip_{status}")
            label.clicked.connect(self.status_clicked.emit)
            self._labels[status] = label
            layout.addWidget(label)

        layout.addStretch(1)
        self.setFixedHeight(34)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.set_status("new")

    def set_status(self, active_status: str | None) -> None:
        self.active_status = active_status or "new"
        print(f"[VIEWER-DIAG] StatusChipBar.set_status raw={active_status!r} normalized={self.active_status!r}", flush=True)
        for status, label in self._labels.items():
            color = STATUS_COLORS.get(status, "#888888")
            if status == self.active_status:
                label.setStyleSheet(
                    f"QLabel {{ background: {color}; color: #000000; border: 2px solid {color}; "
                    "border-radius: 5px; padding: 2px 8px; font-weight: bold; }}"
                )
            else:
                label.setStyleSheet(
                    f"QLabel {{ background: transparent; color: {color}; border: 2px solid {color}; "
                    "border-radius: 5px; padding: 2px 8px; font-weight: bold; }}"
                )


RATING_LABELS: dict[str, tuple[str, str]] = {
    "g": ("general", "#38d36a"),
    "general": ("general", "#38d36a"),
    "s": ("sensitive", "#ffd166"),
    "sensitive": ("sensitive", "#ffd166"),
    "q": ("questionable", "#ffd166"),
    "questionable": ("questionable", "#ffd166"),
    "e": ("explicit", "#ff4d4d"),
    "explicit": ("explicit", "#ff4d4d"),
}


def rating_text_and_color(rating: str | None) -> tuple[str, str]:
    key = str(rating or "").strip().lower()
    return RATING_LABELS.get(key, (key or "?", "#cccccc"))


def rating_html(rating: str | None) -> str:
    text, color = rating_text_and_color(rating)
    return f'<span style="color:{color}; font-weight:bold;">{text}</span>'


def score_to_stars(score: int | float | None, max_score: int | float | None) -> float:
    try:
        current = float(score if score is not None else 0)
        maximum = float(max_score if max_score is not None else 0)
    except (TypeError, ValueError):
        return 0.0

    if maximum <= 0:
        return 0.0
    return max(0.0, min(5.0, current / maximum * 5.0))


def star_text(value: float) -> str:
    full = int(value)
    half = value - full >= 0.5
    chars = ["★" for _ in range(full)]
    if half and len(chars) < 5:
        chars.append("◐")
    while len(chars) < 5:
        chars.append("☆")
    return "".join(chars[:5])


class PersonalStarRatingWidget(QWidget):
    rating_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._rating = 0
        self.setMinimumHeight(34)
        self.setMinimumWidth(260)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.setToolTip("Personal rating 0–10: left click sets 1–10, right click resets to 0.")

    def set_rating(self, value: int | float | None) -> None:
        try:
            rating = int(round(float(value if value is not None else 0)))
        except (TypeError, ValueError):
            rating = 0
        self._rating = max(0, min(10, rating))
        self.update()

    def rating(self) -> int:
        return self._rating

    def paintEvent(self, event) -> None:  # noqa: ANN001
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        font = self.font()
        font.setPointSize(max(15, font.pointSize() + 5))
        painter.setFont(font)

        star_width = max(22, self.width() // 10)

        for index in range(10):
            x = index * star_width + 1
            rect = QRectF(x, 2, star_width, self.height() - 4)

            painter.setPen(QColor("#555555"))
            painter.drawText(rect, Qt.AlignCenter, "★")

            if index >= self._rating:
                continue

            painter.setPen(QColor("#ff7ab6"))
            painter.drawText(rect, Qt.AlignCenter, "★")

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.RightButton:
            self.set_rating(0)
            self.rating_changed.emit(self._rating)
            return
        if event.button() != Qt.LeftButton:
            return
        star_width = max(1, self.width() / 10.0)
        raw_index = int(event.position().x() // star_width)
        raw_index = max(0, min(9, raw_index))
        self.set_rating(raw_index + 1)
        self.rating_changed.emit(self._rating)




class CategoryDecisionDialog(QDialog):
    def __init__(self, report: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Category Details")
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        hint = QLabel(
            "Compact diagnosis of category selection: winner, changed selection, matching rules and the most important blockers."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.report_edit = QTextEdit()
        self.report_edit.setReadOnly(True)
        self.report_edit.setPlainText(report)
        self.report_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(self.report_edit, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

class ImageViewerWindow(QMainWindow):
    status_changed = Signal(int, str)
    query_requested = Signal(str)

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
        self.final_save_service = FinalSaveService(config, db)
        self.api = DanbooruApi(config)
        self.post_import_service = PostImportService(config, db)

        self.current_pixmap: QPixmap | None = None
        self._pixmap_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._prefetch_image_cache: OrderedDict[str, QImage] = OrderedDict()
        self._prefetch_futures: dict[str, Future[QImage]] = {}
        self._prefetch_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="viewer-image-prefetch")
        self._pixmap_cache_max_items = int((config.get("viewer", {}) or {}).get("pixmap_cache_items", 12) or 12)
        self._image_prefetch_enabled = bool((config.get("viewer", {}) or {}).get("prefetch_next_image", True))
        self._image_prefetch_items = int((config.get("viewer", {}) or {}).get("prefetch_next_count", 1) or 1)
        self.current_post_id: int | None = None
        self.shortcuts: list[QShortcut] = []
        self.suggested_category_name: str | None = None
        self.category_influence_by_name: dict[str, float] = {}
        self.last_saved_path: Path | None = None
        self._tag_context_menu: QMenu | None = None
        self._related_context_menu: QMenu | None = None
        self.related_list_expanded = False
        self._related_viewers: list[ImageViewerWindow] = []
        self.max_score_in_view = self.calculate_max_score_in_view()

        viewer_config = config.get("viewer", {}) or {}
        self.auto_advance_after_save = bool(viewer_config.get("auto_advance_after_save", True))
        self.auto_advance_after_reject = bool(viewer_config.get("auto_advance_after_reject", True))
        self.viewer_perf_config = viewer_config.get("performance", {}) or {}
        self.viewer_perf_log_path = Path(config.get("work_dir", ".")) / "logs" / "viewer_performance.log"
        self.viewer_diagnostic_log_path = Path(config.get("work_dir", ".")) / "logs" / "viewer_diagnostics.log"
        self._viewer_load_generation = 0
        self._viewer_load_active = False

        self.setWindowTitle(self.t("viewer.window_title", "Danbooru Manager - Viewer"))
        self.setWindowIcon(ensure_app_icon(config))
        self.setFocusPolicy(Qt.StrongFocus)

        self.toolbar = QToolBar("Viewer")
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.fit_checkbox = QCheckBox(self.t("viewer.fit", "Fit"))
        self.fit_checkbox.setChecked(bool(viewer_config.get("fit_to_window", True)))
        self.fit_checkbox.stateChanged.connect(self.refresh_image)
        self.toolbar.addWidget(self.fit_checkbox)

        self.performance_checkbox = QCheckBox(self.t("viewer.performance", "Perf"))
        self.performance_checkbox.setChecked(bool(self.viewer_perf_config.get("enabled", False)))
        self.performance_checkbox.setToolTip(
            self.t(
                "viewer.performance_tooltip",
                "Measure viewer performance and write it to {path}. Useful for finding slow image changes without guessing.",
                path=self.viewer_perf_log_path,
            )
        )
        self.toolbar.addWidget(self.performance_checkbox)

        self.toolbar.addSeparator()

        self.final_save_button = QPushButton(self.t("viewer.save", "Save [F]"))
        self.final_save_button.clicked.connect(self.final_save_current_post)
        self.toolbar.addWidget(self.final_save_button)

        self.refetch_button = QPushButton(self.t("viewer.refetch", "Refetch Post"))
        self.refetch_button.setToolTip(self.t("viewer.refetch_tooltip", "Reloads post metadata and the viewer image from Danbooru."))
        self.refetch_button.clicked.connect(self.refetch_current_post)
        self.toolbar.addWidget(self.refetch_button)

        self.delete_db_button = QPushButton(self.t("viewer.remove_from_db", "Remove from DB"))
        self.delete_db_button.setToolTip(self.t("viewer.remove_from_db_tooltip", "Removes the post from the local database, but does not delete image files."))
        self.delete_db_button.clicked.connect(self.delete_current_post_from_database)
        self.toolbar.addWidget(self.delete_db_button)

        self.open_saved_folder_button = QPushButton(self.t("viewer.open_target_folder", "Open Target Folder"))
        self.open_saved_folder_button.clicked.connect(self.open_saved_folder)
        self.toolbar.addWidget(self.open_saved_folder_button)

        self.open_local_image_button = QPushButton(self.t("viewer.open_local_image", "Open Local Image"))
        self.open_local_image_button.clicked.connect(self.open_current_local_image)
        self.toolbar.addWidget(self.open_local_image_button)

        self.delete_final_file_button = QPushButton(self.t("viewer.delete_local_file", "Delete Local File"))
        self.delete_final_file_button.setToolTip(self.t("viewer.delete_local_file_tooltip", "Deletes the locally saved file and clears the local path in the database."))
        self.delete_final_file_button.clicked.connect(self.delete_current_final_file)
        self.toolbar.addWidget(self.delete_final_file_button)

        self.toolbar.addSeparator()

        self.open_original_button = QPushButton(self.t("viewer.original_post", "Original Post"))
        self.open_original_button.clicked.connect(self.open_original_post)
        self.toolbar.addWidget(self.open_original_button)

        self.copy_link_button = QPushButton(self.t("viewer.copy_link", "Copy Link"))
        self.copy_link_button.clicked.connect(self.copy_original_post_url)
        self.toolbar.addWidget(self.copy_link_button)

        self.central_container = QWidget()
        self.central_layout = QVBoxLayout(self.central_container)
        self.central_layout.setContentsMargins(4, 4, 4, 4)

        self.header_label = QLabel()
        self.header_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.header_label.setStyleSheet("QLabel { font-size: 16px; font-weight: bold; padding: 4px; }")
        self.central_layout.addWidget(self.header_label)

        self.splitter = QSplitter(Qt.Horizontal)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFocusPolicy(Qt.NoFocus)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 400)
        self.image_label.setFocusPolicy(Qt.NoFocus)

        self.scroll_area.setWidget(self.image_label)

        self.image_panel = QWidget()
        self.image_panel_layout = QVBoxLayout(self.image_panel)
        self.image_panel_layout.setContentsMargins(0, 0, 0, 0)
        self.image_panel_layout.setSpacing(4)
        self.image_panel_layout.addWidget(self.scroll_area, stretch=1)

        self.below_image_controls = QHBoxLayout()
        self.below_image_controls.setContentsMargins(0, 0, 0, 0)
        self.below_image_controls.setSpacing(12)

        self.personal_rating_label = QLabel(self.t("viewer.personal_rating_value", "Personal Rating: {rating}/10", rating=0))
        self.personal_rating_label.setStyleSheet("QLabel { font-weight: bold; }")
        self.below_image_controls.addWidget(self.personal_rating_label)

        self.personal_stars_widget = PersonalStarRatingWidget()
        self.personal_stars_widget.rating_changed.connect(self.set_personal_rating)
        self.below_image_controls.addWidget(self.personal_stars_widget)

        self.below_image_controls.addSpacing(28)

        self.prev_button = QPushButton(self.t("viewer.previous", "< Previous"))
        self.prev_button.setFixedWidth(118)
        self.prev_button.clicked.connect(self.previous_post)
        self.below_image_controls.addWidget(self.prev_button)

        self.footer_label = QLabel()
        self.footer_label.setAlignment(Qt.AlignCenter)
        self.footer_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.footer_label.setFixedWidth(230)
        self.footer_label.setStyleSheet("QLabel { font-size: 22px; font-weight: bold; padding: 4px 10px; }")
        self.below_image_controls.addWidget(self.footer_label)

        self.next_button = QPushButton(self.t("viewer.next", "Next >"))
        self.next_button.setFixedWidth(118)
        self.next_button.clicked.connect(self.next_post)
        self.below_image_controls.addWidget(self.next_button)

        self.below_image_controls.addStretch(1)

        self.category_label = QLabel(self.t("viewer.category", "Category"))
        self.category_label.setStyleSheet("QLabel { font-weight: bold; }")
        self.category_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.below_image_controls.addWidget(self.category_label)

        self.category_combo = QComboBox()
        self.category_combo.currentIndexChanged.connect(self.on_category_changed)
        self.category_combo.setMinimumWidth(220)
        self.below_image_controls.addWidget(self.category_combo)

        self.category_reason_button = QPushButton("Details")
        self.category_reason_button.setToolTip(self.t("viewer.category_details_tooltip", "Shows details about the category decision for this post."))
        self.category_reason_button.clicked.connect(self.show_category_decision_reason)
        self.below_image_controls.addWidget(self.category_reason_button)

        self.image_panel_layout.addLayout(self.below_image_controls)
        self.splitter.addWidget(self.image_panel)

        self.side_panel = QWidget()
        self.side_panel.setMinimumWidth(430)
        self.side_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.side_layout = QVBoxLayout(self.side_panel)

        self.info_label = QLabel()
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_label.setWordWrap(True)
        self.info_label.hide()
        self.side_layout.addWidget(self.info_label)

        self.score_label = QLabel()
        self.score_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.score_label.hide()
        self.side_layout.addWidget(self.score_label)

        self.status_chips = StatusChipBar()
        self.status_chips.status_clicked.connect(self.on_status_chip_clicked)
        self.side_layout.addWidget(self.status_chips)

        self.related_warning_label = QPushButton()
        self.related_warning_label.setToolTip(self.t("viewer.related_toggle_tooltip", "Expand or collapse the parent/child list."))
        self.related_warning_label.clicked.connect(self.toggle_related_posts_visible)
        self.related_warning_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.related_warning_label.setMaximumHeight(42)
        self.related_warning_label.setStyleSheet(
            """
            QPushButton {
                background: #5a3d00;
                color: #ffd166;
                border: 2px solid #ffb000;
                border-radius: 6px;
                padding: 6px;
                font-weight: bold;
                text-align: left;
            }
            QPushButton:hover { background: #704c00; }
            """
        )
        self.related_warning_label.hide()
        self.side_layout.addWidget(self.related_warning_label)

        self.related_label = QLabel(self.t("viewer.related_known_posts", "Known parent/child posts:"))
        self.related_label.hide()
        self.side_layout.addWidget(self.related_label)

        self.related_list = QListWidget()
        self.related_list.itemDoubleClicked.connect(self.open_related_item)
        self.related_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.related_list.customContextMenuRequested.connect(self.open_related_context_menu)
        self.related_list.setMaximumHeight(130)
        self.related_list.hide()
        self.side_layout.addWidget(self.related_list)

        self.tags_widget = TypedTagListWidget()
        for list_widget in self.tags_widget.lists.values():
            list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
            list_widget.customContextMenuRequested.connect(self.open_tag_context_menu)
            list_widget.itemDoubleClicked.connect(self.copy_single_tag_from_item)
        self.side_layout.addWidget(self.tags_widget)

        self.button_row_1 = QHBoxLayout()
        self.potential_button = QPushButton("High Potential [H]")
        self.potential_button.clicked.connect(lambda: self.set_status("potential"))
        self.button_row_1.addWidget(self.potential_button)

        self.reject_button = QPushButton(self.t("viewer.reject", "Reject [Del]"))
        self.reject_button.clicked.connect(lambda: self.set_status("rejected"))
        self.button_row_1.addWidget(self.reject_button)

        self.new_button = QPushButton(self.t("viewer.new", "New [N]"))
        self.new_button.clicked.connect(lambda: self.set_status("new"))
        self.button_row_1.addWidget(self.new_button)

        self.side_layout.addLayout(self.button_row_1)

        self.hint_label = QLabel(
            self.t(
                "viewer.hotkeys_hint",
                "Hotkeys: ←/→ navigate | 1-5 or star click personal rating | "
                "H High Potential | F save | Del reject or exclude selected tags from filename | "
                "N new | O original post | Select tags + right click for tag actions | "
                "Parent/Child: double-click opens local, right-click for local/remote",
            )
        )
        self.hint_label.setWordWrap(True)
        self.side_layout.addWidget(self.hint_label)

        self.splitter.addWidget(self.side_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([820, 520])
        self.central_layout.addWidget(self.splitter, stretch=1)

        self.path_footer = QWidget()
        self.path_footer_layout = QVBoxLayout(self.path_footer)
        self.path_footer_layout.setContentsMargins(0, 4, 0, 0)
        self.path_footer_layout.setSpacing(4)

        self.path_footer_header = QHBoxLayout()
        self.path_footer_header.setContentsMargins(0, 0, 0, 0)
        self.final_path_title_label = QLabel(self.t("viewer.target_path", "Target Path"))
        self.final_path_title_label.setStyleSheet("QLabel { font-weight: bold; margin-top: 2px; }")
        self.path_footer_header.addWidget(self.final_path_title_label)
        self.path_footer_header.addStretch(1)

        self.filename_preview_button = QPushButton(self.t("viewer.filename_preview_show", "Show Filename Preview"))
        self.filename_preview_button.setCheckable(True)
        self.filename_preview_button.toggled.connect(self.toggle_filename_preview)
        self.filename_preview_button.hide()
        self.path_footer_header.addWidget(self.filename_preview_button)
        self.path_footer_layout.addLayout(self.path_footer_header)

        self.final_path_label = QLabel()
        self.final_path_label.setWordWrap(True)
        self.final_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.final_path_label.setMaximumHeight(52)
        self.final_path_label.setMinimumWidth(0)
        self.final_path_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.final_path_label.setStyleSheet(
            "QLabel { background: transparent; color: #eeeeee; border: 1px solid #eeeeee; "
            "border-radius: 5px; padding: 6px; }"
        )
        self.path_footer_layout.addWidget(self.final_path_label)

        self.filename_preview_label = QLabel()
        self.filename_preview_label.setWordWrap(True)
        self.filename_preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.filename_preview_label.setMinimumWidth(0)
        self.filename_preview_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.filename_preview_label.setStyleSheet(
            "QLabel { background: #202020; border: 1px solid #555; border-radius: 6px; padding: 6px; }"
        )
        self.filename_preview_label.hide()
        self.path_footer_layout.addWidget(self.filename_preview_label)

        self.central_layout.addWidget(self.path_footer, stretch=0)

        self.setCentralWidget(self.central_container)

        self.install_shortcuts()
        self.load_current_post()

    def t(self, key: str, default: str, **kwargs: Any) -> str:
        return tr(key, default, config=self.config, **kwargs)

    def install_shortcuts(self) -> None:
        shortcut_map: list[tuple[str, Callable[[], None]]] = [
            ("Left", self.previous_post),
            ("Right", self.next_post),
            ("1", lambda: self.set_personal_rating(1.0)),
            ("2", lambda: self.set_personal_rating(2.0)),
            ("3", lambda: self.set_personal_rating(3.0)),
            ("4", lambda: self.set_personal_rating(4.0)),
            ("5", lambda: self.set_personal_rating(5.0)),
            ("H", lambda: self.set_status("potential")),
            ("F", self.final_save_current_post),
            ("Delete", self.handle_delete_shortcut),
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

    def focusInEvent(self, event) -> None:  # noqa: ANN001
        super().focusInEvent(event)
        self.update_final_path_preview()

    def handle_delete_shortcut(self) -> None:
        selected_tags = self.tags_widget.selected_tags()
        if selected_tags and self.tags_widget.is_filename_filter_active():
            self.add_tags_to_filename_exclude(selected_tags, show_message=False)
            self.statusBar().showMessage(
                self.t("viewer.tags_excluded_from_filename", "{count} tag(s) excluded from filename.", count=len(selected_tags)),
                3500,
            )
            return

        self.set_status("rejected")

    def calculate_max_score_in_view(self) -> int | None:
        return self.db.get_max_post_score(self.post_ids)

    def toggle_filename_preview(self, checked: bool) -> None:
        self.filename_preview_label.setVisible(checked)
        self.filename_preview_button.setText(
            self.t("viewer.filename_preview_hide", "Hide Filename Preview") if checked else self.t("viewer.filename_preview_show", "Show Filename Preview")
        )

    def current_post_id_value(self) -> int | None:
        if 0 <= self.current_index < len(self.post_ids):
            return self.post_ids[self.current_index]
        return None

    def viewer_performance_enabled(self) -> bool:
        checkbox = getattr(self, "performance_checkbox", None)
        if checkbox is not None:
            return bool(checkbox.isChecked())
        return bool(self.viewer_perf_config.get("enabled", False))

    def perf_add(self, metrics: dict[str, float] | None, key: str, started_at: float) -> None:
        if metrics is not None:
            metrics[key] = metrics.get(key, 0.0) + ((time.perf_counter() - started_at) * 1000.0)

    def write_viewer_performance_log(self, post_id: int, metrics: dict[str, float]) -> None:
        total_ms = metrics.get("total", 0.0)
        threshold_ms = float(self.viewer_perf_config.get("threshold_ms", 0) or 0)
        if threshold_ms > 0 and total_ms < threshold_ms:
            return

        ordered_keys = [
            "total",
            "get_post_detail",
            "get_related_posts",
            "related_local_paths",
            "header_status_rating",
            "update_related_posts",
            "category_suggest",
            "category_assigned",
            "category_influence",
            "category_list",
            "category_combo_ui",
            "final_path_preview",
            "tags_typed",
            "tags_filename_exclude",
            "tags_metadata",
            "tags_widget_ui",
            "ensure_image_path",
            "qpixmap_load",
            "refresh_image",
            "prefetch_schedule",
        ]
        parts = [f"post={post_id}"]
        for key in ordered_keys:
            if key in metrics:
                parts.append(f"{key}={metrics[key]:.1f}ms")
        for key, value in metrics.items():
            if key not in ordered_keys:
                parts.append(f"{key}={value:.1f}ms")

        line = "[PERF][viewer] " + " ".join(parts)
        try:
            self.viewer_perf_log_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with self.viewer_perf_log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{timestamp}] {line}\n")
        except Exception:
            pass
        print(line, flush=True)

    def write_viewer_diagnostic(self, message: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        thread = threading.current_thread()
        line = f"[{timestamp}] [thread={thread.name}:{thread.ident}] {message}"
        try:
            self.viewer_diagnostic_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.viewer_diagnostic_log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            pass
        print(f"[VIEWER-DIAG] {line}", flush=True)

    def schedule_viewer_hang_dump(self, generation: int, post_id: int) -> None:
        def dump_if_still_active() -> None:
            if not self._viewer_load_active or generation != self._viewer_load_generation:
                return
            self.write_viewer_diagnostic(
                f"HANG WATCHDOG fired generation={generation} post_id={post_id}; dumping all Python threads"
            )
            try:
                self.viewer_diagnostic_log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.viewer_diagnostic_log_path.open("a", encoding="utf-8") as handle:
                    handle.write("\n--- PYTHON THREAD DUMP ---\n")
                    faulthandler.dump_traceback(file=handle, all_threads=True)
                    handle.write("--- END PYTHON THREAD DUMP ---\n\n")
            except Exception:
                self.write_viewer_diagnostic("Watchdog dump failed:\n" + traceback.format_exc())

        QTimer.singleShot(5000, dump_if_still_active)

    def load_current_post(self) -> None:
        perf_enabled = self.viewer_performance_enabled()
        metrics: dict[str, float] | None = {} if perf_enabled else None
        total_started_at = time.perf_counter()

        post_id = self.current_post_id_value()
        if post_id is None:
            self.write_viewer_diagnostic("load_current_post aborted: no current post id")
            return

        self._viewer_load_generation += 1
        load_generation = self._viewer_load_generation
        if self._viewer_load_active:
            self.write_viewer_diagnostic(
                f"REENTRANT load_current_post generation={load_generation} post_id={post_id}"
            )
        self._viewer_load_active = True
        self.write_viewer_diagnostic(
            f"BEGIN load_current_post generation={load_generation} post_id={post_id} "
            f"index={self.current_index} visible_posts={len(self.post_ids)}"
        )
        self.schedule_viewer_hang_dump(load_generation, post_id)

        self.current_post_id = post_id
        self.last_saved_path = None

        started_at = time.perf_counter()
        self.write_viewer_diagnostic(f"STEP get_post_detail begin post_id={post_id}")
        row = self.db.get_post_detail(post_id)
        self.write_viewer_diagnostic(f"STEP get_post_detail end post_id={post_id} found={row is not None}")
        self.perf_add(metrics, "get_post_detail", started_at)
        if row is None:
            self._viewer_load_active = False
            self.write_viewer_diagnostic(f"END load_current_post missing row post_id={post_id}")
            return

        started_at = time.perf_counter()
        self.write_viewer_diagnostic(f"STEP get_related_posts begin post_id={post_id}")
        related = self.db.get_related_posts(post_id)
        self.write_viewer_diagnostic(f"STEP get_related_posts end post_id={post_id} count={len(related)}")
        self.perf_add(metrics, "get_related_posts", started_at)

        related_total_count = len(related)
        started_at = time.perf_counter()
        related_local_count = sum(1 for related_row in related if self.local_path_for_post(int(related_row["id"])))
        self.perf_add(metrics, "related_local_paths", started_at)

        started_at = time.perf_counter()
        self.setWindowTitle(self.t("viewer.window_title_post", "Danbooru Manager - Viewer - {post_id}", post_id=post_id))

        rating_html_value = rating_html(row["rating"])
        score_value = row["score"] if row["score"] is not None else None

        parent_text = row['parent_id'] if row['parent_id'] is not None else '-'
        self.header_label.setText(
            self.t(
                "viewer.header",
                "ID {post_id} - {rating} - Score: {score} &nbsp;&nbsp;|&nbsp;&nbsp; Parent: {parent} "
                "&nbsp;&nbsp;|&nbsp;&nbsp; Parent/Child known: {related_total} | locally saved: {related_local}",
                post_id=post_id,
                rating=rating_html_value,
                score=score_value if score_value is not None else "-",
                parent=parent_text,
                related_total=related_total_count,
                related_local=related_local_count,
            )
        )
        self.footer_label.setText(self.t("viewer.position", "Position {current} / {total}", current=self.current_index + 1, total=len(self.post_ids)))

        self.info_label.setText("")
        self.score_label.setText("")

        self.related_list_expanded = False
        if related_total_count:
            if related_local_count:
                self.related_warning_label.setText(
                    self.t(
                        "viewer.related_warning_with_local",
                        "⚠ Parent/Child posts available: {total} known, {local} locally saved. Click to show.",
                        total=related_total_count,
                        local=related_local_count,
                    )
                )
            else:
                self.related_warning_label.setText(
                    self.t(
                        "viewer.related_warning",
                        "⚠ Parent/Child posts available: {total} known. Click to show.",
                        total=related_total_count,
                    )
                )
            self.related_warning_label.show()
            self.related_label.hide()
            self.related_list.hide()
        else:
            self.related_warning_label.hide()
            self.related_label.hide()
            self.related_list.hide()

        status = row["status"] or "new"
        self.write_viewer_diagnostic(
            f"ROW values post_id={post_id} status={status!r} rating={row['rating']!r} "
            f"score={row['score']!r} stars={row['stars']!r} "
            f"parent_id={row['parent_id']!r} final_file_path={row['final_file_path']!r}"
        )
        self.write_viewer_diagnostic(f"STEP status_chips begin status={status!r}")
        self.status_chips.set_status(status)
        self.write_viewer_diagnostic(f"STEP status_chips end status={status!r}")
        self.final_save_button.setEnabled(True)
        local_current_path = self.local_path_for_post(post_id)
        self.open_local_image_button.setEnabled(local_current_path is not None)
        self.delete_final_file_button.setEnabled(bool(row["final_file_path"]))

        stars = row["stars"]
        self.personal_stars_widget.set_rating(stars)
        self.update_personal_rating_label()
        self.perf_add(metrics, "header_status_rating", started_at)

        started_at = time.perf_counter()
        self.write_viewer_diagnostic("STEP update_related_posts begin")
        self.update_related_posts(post_id, related)
        self.write_viewer_diagnostic("STEP update_related_posts end")
        self.perf_add(metrics, "update_related_posts", started_at)

        self.write_viewer_diagnostic("STEP update_category_controls begin")
        self.update_category_controls(post_id, metrics)
        self.write_viewer_diagnostic("STEP update_category_controls end")

        self.write_viewer_diagnostic("STEP populate_tag_lists begin")
        self.populate_tag_lists(post_id, metrics)
        self.write_viewer_diagnostic("STEP populate_tag_lists end")

        started_at = time.perf_counter()
        self.write_viewer_diagnostic("STEP ensure_image_path begin")
        image_path = self.ensure_image_path(post_id, row)
        self.write_viewer_diagnostic(f"STEP ensure_image_path end path={str(image_path)!r}")
        self.perf_add(metrics, "ensure_image_path", started_at)
        if image_path:
            started_at = time.perf_counter()
            pixmap = self.load_pixmap_cached(image_path)
            self.perf_add(metrics, "qpixmap_load", started_at)
            if pixmap is not None and not pixmap.isNull():
                self.current_pixmap = pixmap
            else:
                self.current_pixmap = None
                self.image_label.setText(self.t("viewer.image_load_failed_path", "Image could not be loaded:\n{path}", path=image_path))
        else:
            self.current_pixmap = None
            self.image_label.setText(self.t("viewer.no_local_image_download_failed", "No local image file and download failed."))

        started_at = time.perf_counter()
        self.write_viewer_diagnostic("STEP refresh_image begin")
        self.refresh_image()
        self.write_viewer_diagnostic("STEP refresh_image end")
        self.perf_add(metrics, "refresh_image", started_at)

        started_at = time.perf_counter()
        self.write_viewer_diagnostic("STEP schedule_next_image_prefetch begin")
        self.schedule_next_image_prefetch()
        self.write_viewer_diagnostic("STEP schedule_next_image_prefetch end")
        self.perf_add(metrics, "prefetch_schedule", started_at)

        if metrics is not None:
            metrics["total"] = (time.perf_counter() - total_started_at) * 1000.0
            self.write_viewer_performance_log(post_id, metrics)

        self._viewer_load_active = False
        elapsed_ms = (time.perf_counter() - total_started_at) * 1000.0
        self.write_viewer_diagnostic(
            f"END load_current_post generation={load_generation} post_id={post_id} elapsed={elapsed_ms:.1f}ms"
        )

    def populate_tag_lists(self, post_id: int, metrics: dict[str, float] | None = None) -> None:
        self.tags_widget.show_loading_message(self.t("viewer.tags_loading", "Loading tags…"))
        self.statusBar().showMessage(self.t("viewer.tags_loading", "Loading tags…"))
        QApplication.processEvents()

        started_at = time.perf_counter()
        typed_tags = typed_tags_for_post(self.db, post_id)
        self.perf_add(metrics, "tags_typed", started_at)

        all_tags = [tag for tags in typed_tags.values() for tag in tags]

        started_at = time.perf_counter()
        filename_excluded_tags = self.db.filename_excluded_tag_set()
        self.perf_add(metrics, "tags_filename_exclude", started_at)

        started_at = time.perf_counter()
        tag_metadata = self.db.fetch_tag_display_metadata(all_tags)
        self.perf_add(metrics, "tags_metadata", started_at)

        started_at = time.perf_counter()
        self.tags_widget.set_typed_tags(
            typed_tags,
            filename_excluded_tags=filename_excluded_tags,
            tag_metadata=tag_metadata,
        )
        self.perf_add(metrics, "tags_widget_ui", started_at)
        self.statusBar().showMessage(self.t("viewer.tags_loaded", "Tags loaded."), 2000)


    def toggle_related_posts_visible(self) -> None:
        if self.related_list.count() <= 0:
            return

        first_item = self.related_list.item(0)
        if first_item is not None and not (first_item.flags() & Qt.ItemIsEnabled):
            return

        self.related_list_expanded = not self.related_list_expanded
        self.related_label.setVisible(self.related_list_expanded)
        self.related_list.setVisible(self.related_list_expanded)

    def update_related_posts(self, post_id: int, related: list[Any] | None = None) -> None:
        self.related_list.clear()

        if related is None:
            related = self.db.get_related_posts(post_id)

        for row in related:
            relation = str(row["relation"])
            relation_label = "Parent" if relation == "parent" else "Child"
            related_id = int(row["id"])
            local_path = self.local_path_for_post(related_id)

            local_marker = self.t("viewer.related_local_available", "local available") if local_path else self.t("viewer.related_db_remote_only", "DB/remote only")
            text = self.t(
                "viewer.related_item",
                "⚠ {relation}: {post_id} | Status: {status} | {marker}",
                relation=relation_label,
                post_id=related_id,
                status=row["status"] or "-",
                marker=local_marker,
            )

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, related_id)
            item.setData(Qt.UserRole + 1, relation)
            item.setData(Qt.UserRole + 2, str(local_path) if local_path else "")

            font = QFont()
            font.setBold(True)
            item.setFont(font)

            if local_path:
                item.setForeground(QBrush(QColor("#ffd166")))
                item.setBackground(QBrush(QColor("#3a2a00")))
            else:
                item.setForeground(QBrush(QColor("#ffb000")))
                item.setBackground(QBrush(QColor("#242424")))

            self.related_list.addItem(item)

        if not related:
            item = QListWidgetItem(self.t("viewer.no_known_related_posts", "No known parent/child posts"))
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.related_list.addItem(item)

    def local_path_for_post(self, post_id: int) -> Path | None:
        row = self.db.get_post_detail(post_id)
        if row is None:
            return None

        final_path = row["final_file_path"]
        if not final_path:
            return None

        path = Path(str(final_path))
        if path.exists():
            return path

        return None

    def build_post_url(self, post_id: int) -> str:
        base_url = str(self.config.get("base_url", "https://danbooru.donmai.us")).rstrip("/")
        return f"{base_url}/posts/{post_id}"

    def open_related_item(self, item: QListWidgetItem) -> None:
        post_id = item.data(Qt.UserRole)
        if not post_id:
            return

        post_id_int = int(post_id)
        if self.local_path_for_post(post_id_int) is not None:
            self.open_related_in_viewer(post_id_int)
            return

        webbrowser.open(self.build_post_url(post_id_int))

    def open_related_context_menu(self, position) -> None:  # noqa: ANN001
        item = self.related_list.itemAt(position)
        if item is None or not (item.flags() & Qt.ItemIsEnabled):
            return

        post_id = item.data(Qt.UserRole)
        if not post_id:
            return

        post_id = int(post_id)
        local_path = self.local_path_for_post(post_id)

        menu = QMenu(self)
        self._related_context_menu = menu

        viewer_action = QAction(self.t("viewer.open_in_separate_viewer", "Open in separate viewer"), menu)
        viewer_action.setEnabled(local_path is not None)
        viewer_action.triggered.connect(lambda checked=False, pid=post_id: self.open_related_in_viewer(pid))
        menu.addAction(viewer_action)

        local_action = QAction(self.t("viewer.open_local_file_system", "Open local file in system"), menu)
        local_action.setEnabled(local_path is not None)
        local_action.triggered.connect(
            lambda checked=False, p=local_path: self.open_local_path(p) if p is not None else None
        )
        menu.addAction(local_action)

        folder_action = QAction(self.t("viewer.open_local_folder", "Open local folder"), menu)
        folder_action.setEnabled(local_path is not None)
        folder_action.triggered.connect(
            lambda checked=False, p=local_path: self.open_local_folder(p) if p is not None else None
        )
        menu.addAction(folder_action)

        menu.addSeparator()

        remote_action = QAction(self.t("viewer.open_remote_original", "Open remote original post"), menu)
        remote_action.triggered.connect(lambda checked=False, pid=post_id: webbrowser.open(self.build_post_url(pid)))
        menu.addAction(remote_action)

        copy_remote_action = QAction(self.t("viewer.copy_remote_link", "Copy remote link"), menu)
        copy_remote_action.triggered.connect(
            lambda checked=False, pid=post_id: QGuiApplication.clipboard().setText(self.build_post_url(pid))
        )
        menu.addAction(copy_remote_action)

        if local_path is not None:
            copy_local_action = QAction(self.t("viewer.copy_local_path", "Copy local path"), menu)
            copy_local_action.triggered.connect(
                lambda checked=False, p=local_path: QGuiApplication.clipboard().setText(str(p))
            )
            menu.addAction(copy_local_action)

        menu.popup(self.related_list.viewport().mapToGlobal(position))

    def open_related_in_viewer(self, post_id: int) -> None:
        post_id = int(post_id)
        if self.local_path_for_post(post_id) is None:
            QMessageBox.information(
                self,
                self.t("viewer.open_parent_child_title", "Open Parent/Child"),
                self.t("viewer.related_no_local_path_open_remote", "Post {post_id} has no local path. Opening original post in browser.", post_id=post_id),
            )
            webbrowser.open(self.build_post_url(post_id))
            return

        related_ids = [post_id]
        try:
            related = self.db.get_related_posts(post_id)
            for row in related:
                rid = int(row["id"])
                if rid not in related_ids and self.local_path_for_post(rid) is not None:
                    related_ids.append(rid)
        except Exception:
            pass

        viewer = ImageViewerWindow(self.config, self.db, related_ids, post_id)
        viewer.status_changed.connect(self.status_changed.emit)
        viewer.query_requested.connect(self.query_requested.emit)
        viewer.destroyed.connect(lambda *_args, v=viewer: self._forget_related_viewer(v))
        self._related_viewers.append(viewer)
        viewer.resize(1350, 900)
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()

    def _forget_related_viewer(self, viewer: "ImageViewerWindow") -> None:
        try:
            self._related_viewers.remove(viewer)
        except ValueError:
            pass

    def open_local_path(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.warning(self, self.t("viewer.local_file_missing_title", "Local File Missing"), self.t("viewer.file_does_not_exist", "File does not exist:\n{path}", path=path))
            return

        os.startfile(path)

    def open_local_folder(self, path: Path) -> None:
        folder = path.parent if path.is_file() else path
        if not folder.exists():
            QMessageBox.warning(self, self.t("viewer.folder_missing_title", "Folder Missing"), self.t("viewer.folder_does_not_exist", "Folder does not exist:\n{folder}", folder=folder))
            return

        os.startfile(folder)

    def update_category_controls(self, post_id: int, metrics: dict[str, float] | None = None) -> None:
        started_at = time.perf_counter()
        suggested = self.final_save_service.suggest_category(post_id)
        self.perf_add(metrics, "category_suggest", started_at)
        self.suggested_category_name = suggested.name

        started_at = time.perf_counter()
        assigned = self.db.get_assigned_category_for_post(post_id)
        self.perf_add(metrics, "category_assigned", started_at)
        assigned_name = str(assigned["name"]) if assigned is not None else None
        assigned_source = str(assigned["assignment_source"] or "manual") if assigned is not None else None

        self.category_combo.blockSignals(True)
        self.category_combo.clear()

        started_at = time.perf_counter()
        influences = self.final_save_service.category_engine.category_influence_for_post(post_id)
        self.perf_add(metrics, "category_influence", started_at)
        self.category_influence_by_name = {entry.name: entry.score for entry in influences}
        top_influence_name = influences[0].name if influences else None

        started_at = time.perf_counter()
        categories = self.final_save_service.list_categories()
        self.perf_add(metrics, "category_list", started_at)

        started_at = time.perf_counter()
        for category in categories:
            label = category.name
            suffixes: list[str] = []
            if category.name == suggested.name:
                suffixes.append(self.t("viewer.category_suffix_suggested", "suggested"))
            if category.name == top_influence_name:
                suffixes.append(self.t("viewer.category_suffix_tag_hint", "tag hint"))
            if assigned_name and category.name == assigned_name:
                suffixes.append(self.t("viewer.category_suffix_assigned", "assigned"))
            if suffixes:
                label = f"{category.name}  ← {', '.join(suffixes)}"
            self.category_combo.addItem(label, category.name)

        target_name = assigned_name or suggested.name
        target_index = self.category_combo.findData(target_name)
        if target_index >= 0:
            self.category_combo.setCurrentIndex(target_index)

        self.category_combo.blockSignals(False)

        if assigned_name:
            self.category_label.setText(self.t("viewer.category_assigned_source", "Category: assigned ({source})", source=assigned_source))
        else:
            influence_text = ""
            if top_influence_name and top_influence_name != suggested.name:
                influence_text = self.t("viewer.category_tag_hint_append", " | tag hint: {name}", name=top_influence_name)
            self.category_label.setText(self.t("viewer.category_suggestion", "Category: suggestion {name}{hint}", name=suggested.name, hint=influence_text))
        self.perf_add(metrics, "category_combo_ui", started_at)
        self.update_final_path_preview(metrics)

    def selected_category(self) -> CategoryMatch | None:
        name = self.category_combo.currentData()
        if name is None:
            return None
        return self.final_save_service.category_by_name(str(name))

    def show_category_decision_reason(self) -> None:
        if self.current_post_id is None:
            QMessageBox.information(self, self.t("viewer.category_details_title", "Category Details"), self.t("viewer.no_post_loaded", "No post loaded."))
            return

        category = self.selected_category()
        selected_name = category.name if category is not None else None
        report = self.final_save_service.category_engine.build_category_decision_report_for_post(
            self.current_post_id,
            selected_category_name=selected_name,
        )
        dialog = CategoryDecisionDialog(report, self)
        dialog.exec()

    def on_category_changed(self, *args) -> None:  # noqa: ANN002
        if self.current_post_id is not None:
            category = self.selected_category()
            if category is not None and category.id is not None:
                self.db.assign_post_category(self.current_post_id, category.id, "manual")
                self.final_save_service.category_engine.clear_category_influence_cache()
                self.category_label.setText(self.t("viewer.category_assigned_manual", "Category: assigned (manual)"))
                self.status_changed.emit(self.current_post_id, str(self.db.get_post_detail(self.current_post_id)["status"] or "new"))
        self.update_final_path_preview()

    def update_final_path_preview(self, metrics: dict[str, float] | None = None) -> None:
        if self.current_post_id is None:
            return

        category = self.selected_category()
        started_at = time.perf_counter()
        preview = self.final_save_service.final_path_preview_details(self.current_post_id, category)
        self.perf_add(metrics, "final_path_preview", started_at)

        if preview:
            final_preview, details = preview
            source = "auto"
            if category is not None and category.name != self.suggested_category_name:
                source = "manual"
            self.final_path_label.setText(f"{source}: {final_preview}")
            self.filename_preview_label.setText(self.format_filename_preview(details))
        else:
            self.final_path_label.setText(self.t("viewer.path_not_known_yet", "Not known yet; file will be loaded when pressing F."))
            self.filename_preview_label.setText(self.t("viewer.filename_not_known_yet", "Filename: not known yet"))

    def format_filename_preview(self, details) -> str:  # noqa: ANN001
        def count_tags(key: str) -> int:
            return len(details.included_tags.get(key, []))

        excluded_total = sum(len(tags) for tags in details.excluded_tags.values())
        general_used = details.included_tags.get("general", [])[: int(self.config.get("filename", {}).get("tags_count", 8))]
        general_text = ", ".join(general_used[:10]) if general_used else "-"
        if len(general_used) > 10:
            general_text += f" … +{len(general_used) - 10}"

        return (
            self.t("viewer.filename_preview_title", "Filename Preview:\n")
            + f"{details.filename}\n"
            + f"Pattern: {details.pattern}\n"
            + self.t(
                "viewer.filename_tags_in_name",
                "Tags in name: Artist {artist}, Character {character}, Series {series}, General {general}, Meta {meta}\n",
                artist=count_tags("artist"),
                character=count_tags("character"),
                series=count_tags("copyright"),
                general=len(general_used),
                meta=count_tags("meta"),
            )
            + self.t("viewer.filename_general_in_name", "General in name: {general}\n", general=general_text)
            + self.t("viewer.filename_excluded_removed", "Removed by filename exclude: {count}", count=excluded_total)
        )

    def existing_image_path_from_row(self, row) -> str | None:  # noqa: ANN001
        for candidate in (
            row["original_cache_path"],
            row["original_path"],
            row["final_file_path"],
            row["thumbnail_path"],
            row["rejected_thumbnail_path"],
        ):
            if candidate and Path(str(candidate)).exists():
                return str(candidate)
        return None

    def ensure_image_path(self, post_id: int, row) -> str | None:  # noqa: ANN001
        existing = self.existing_image_path_from_row(row)
        if existing:
            return existing

        return self.download_service.ensure_original_cached(post_id)

    @staticmethod
    def _load_prefetch_image(image_path: str) -> QImage:
        # QImage is safe to create outside the GUI thread. QPixmap is not, because
        # Qt apparently enjoys turning simple image loading into a trapdoor.
        return QImage(image_path)

    def _trim_prefetch_image_cache(self) -> None:
        max_items = max(1, self._pixmap_cache_max_items)
        while len(self._prefetch_image_cache) > max_items:
            self._prefetch_image_cache.popitem(last=False)

    def _store_prefetched_image(self, key: str, future: Future[QImage]) -> None:
        self._prefetch_futures.pop(key, None)
        if key in self._pixmap_cache:
            return
        try:
            image = future.result()
        except Exception:
            return
        if image.isNull():
            return
        self._prefetch_image_cache[key] = image
        self._prefetch_image_cache.move_to_end(key)
        self._trim_prefetch_image_cache()

    def collect_finished_prefetches(self) -> None:
        for key, future in list(self._prefetch_futures.items()):
            if future.done():
                self._store_prefetched_image(key, future)

    def schedule_next_image_prefetch(self) -> None:
        if not self._image_prefetch_enabled or self._image_prefetch_items <= 0:
            return

        self.collect_finished_prefetches()
        scheduled = 0
        for offset in range(1, self._image_prefetch_items + 1):
            next_index = self.current_index + offset
            if next_index >= len(self.post_ids):
                break

            next_post_id = int(self.post_ids[next_index])
            row = self.db.get_post_detail(next_post_id)
            if row is None:
                continue

            image_path = self.existing_image_path_from_row(row)
            if not image_path:
                continue

            key = str(image_path)
            if key in self._pixmap_cache or key in self._prefetch_image_cache or key in self._prefetch_futures:
                continue

            future = self._prefetch_executor.submit(self._load_prefetch_image, key)
            self._prefetch_futures[key] = future
            scheduled += 1

        if scheduled:
            self.statusBar().showMessage(self.t("viewer.image_prefetch_scheduled", "Image prefetch scheduled: {count}", count=scheduled), 1200)


    def load_pixmap_cached(self, image_path: Path | str) -> QPixmap | None:
        """Load a pixmap with a tiny LRU cache for back/forward navigation.

        This does not make the first decode of a huge image free. Physics remains
        rude. But going back to recently viewed posts no longer decodes the same
        file again, and repeated viewer refreshes avoid disk/decoder work.
        """
        key = str(image_path)
        cached = self._pixmap_cache.get(key)
        if cached is not None:
            self._pixmap_cache.move_to_end(key)
            return cached

        prefetched_image = self._prefetch_image_cache.pop(key, None)
        if prefetched_image is not None and not prefetched_image.isNull():
            pixmap = QPixmap.fromImage(prefetched_image)
        else:
            future = self._prefetch_futures.get(key)
            if future is not None and future.done():
                self._prefetch_futures.pop(key, None)
                try:
                    prefetched_image = future.result()
                except Exception:
                    prefetched_image = QImage()
                if prefetched_image is not None and not prefetched_image.isNull():
                    pixmap = QPixmap.fromImage(prefetched_image)
                else:
                    pixmap = QPixmap(key)
            else:
                pixmap = QPixmap(key)

        if pixmap.isNull():
            return pixmap

        self._pixmap_cache[key] = pixmap
        self._pixmap_cache.move_to_end(key)
        while len(self._pixmap_cache) > max(1, self._pixmap_cache_max_items):
            self._pixmap_cache.popitem(last=False)
        return pixmap

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

    def closeEvent(self, event) -> None:  # noqa: ANN001
        try:
            self._prefetch_executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            self._prefetch_executor.shutdown(wait=False)
        super().closeEvent(event)

    def previous_post(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_post()

    def next_post(self) -> None:
        if self.current_index < len(self.post_ids) - 1:
            self.current_index += 1
            self.load_current_post()

    def on_status_chip_clicked(self, status: str) -> None:
        if self.current_post_id is None:
            return

        current = self.status_chips.active_status or "new"
        # There is still exactly one status. Clicking the active status
        # clears the marker in practice, so it goes back to "New".
        # A completely empty status would just be another special case from Qt hell.
        target = "new" if status == current and current != "new" else status
        self.set_status(target)

    def set_status(self, status: str) -> None:
        if self.current_post_id is None:
            return

        self.db.set_post_status(self.current_post_id, status, self.config)
        self.status_chips.set_status(status)
        self.status_changed.emit(self.current_post_id, status)

        if status == "rejected" and self.auto_advance_after_reject:
            self.next_post()

    def set_stars(self, stars: int) -> None:
        self.set_personal_rating(int(stars))

    def update_personal_rating_label(self) -> None:
        self.personal_rating_label.setText(self.t("viewer.personal_rating_value", "Personal Rating: {rating}/10", rating=self.personal_stars_widget.rating()))

    def set_personal_rating(self, rating: int | float) -> None:
        if self.current_post_id is None:
            return

        rating_int = max(0, min(10, int(round(float(rating)))))
        self.db.set_post_review(self.current_post_id, stars=rating_int)
        self.personal_stars_widget.set_rating(rating_int)
        self.update_personal_rating_label()

    def final_save_current_post(self) -> None:
        if self.current_post_id is None:
            return

        post_id = self.current_post_id
        category = self.selected_category()
        row = self.db.get_post_detail(post_id)
        existing_path = Path(str(row["final_file_path"])) if row is not None and row["final_file_path"] else None
        existing_is_local = existing_path is not None and existing_path.exists()
        overwrite_existing = False

        if existing_path is not None:
            message = (
                self.t("viewer.replace_existing_intro", "This post already has a local target path.\n\n")
                + f"{existing_path}\n\n"
                + self.t("viewer.replace_existing_question", "Reload using Danbooru file_url and overwrite/resave locally?")
            )
            if not existing_is_local:
                message = (
                    self.t("viewer.repair_missing_local_intro", "This post has a local target path in the database, but the file is missing locally.\n\n")
                    + f"{existing_path}\n\n"
                    + self.t("viewer.repair_missing_local_question", "Reload original and repair target path?")
                )

            answer = QMessageBox.question(self, self.t("viewer.replace_local_file_title", "Replace Local File"), message)
            if answer != QMessageBox.StandardButton.Yes:
                return
            overwrite_existing = True

        try:
            result = self.final_save_service.save_post(post_id, category, overwrite_existing=overwrite_existing)
        except AlreadySavedError as exc:
            self.status_chips.set_status("saved")
            self.final_path_label.setText(str(exc))
            QMessageBox.information(self, self.t("viewer.already_saved_title", "Already Saved"), str(exc))
            return
        except Exception as exc:
            self.final_path_label.setText(self.t("viewer.save_failed_label", "Save failed: {error}", error=exc))
            QMessageBox.critical(self, self.t("viewer.save_failed_title", "Save Failed"), str(exc))
            return

        self.last_saved_path = result.final_path

        self.status_chips.set_status("saved")
        self.category_label.setText(self.t("viewer.category_result", "Category: {name} ({source})", name=result.category.name, source=result.category_source))
        self.final_path_label.setText(self.t("viewer.saved_path", "Saved: {path}", path=result.final_path))
        self.status_changed.emit(post_id, "saved")

        if self.auto_advance_after_save:
            self.next_post()
        else:
            self.load_current_post()

    def delete_current_final_file(self) -> None:
        if self.current_post_id is None:
            return

        post_id = self.current_post_id
        row = self.db.get_post_detail(post_id)
        if row is None or not row["final_file_path"]:
            QMessageBox.information(self, self.t("viewer.delete_local_file_title", "Delete Local File"), self.t("viewer.no_local_save_path", "No local save path is stored for this post."))
            return

        path = Path(str(row["final_file_path"]))
        answer = QMessageBox.question(
            self,
            self.t("viewer.delete_local_file_title", "Delete Local File"),
            (
                self.t("viewer.confirm_delete_local_file_intro", "Really delete this locally saved file?\n\n")
                + f"Post {post_id}\n{path}\n\n"
                + self.t("viewer.confirm_delete_local_file_note", "The DB record remains, but the local file path will be cleared.")
            ),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            if path.exists():
                if not path.is_file():
                    raise RuntimeError(self.t("viewer.path_is_not_file", "Path is not a file"))
                path.unlink()
            new_status = "new" if str(row["status"] or "") == "saved" else None
            self.db.clear_post_final_file_path(post_id, new_status=new_status)
            if new_status:
                self.status_chips.set_status(new_status)
                self.status_changed.emit(post_id, new_status)
            self.final_path_label.setText(self.t("viewer.local_file_deleted", "Local file deleted; local path was cleared."))
            self.open_local_image_button.setEnabled(False)
            self.delete_final_file_button.setEnabled(False)
            self.load_current_post()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self.t("viewer.delete_local_file_failed_title", "Delete Local File Failed"), str(exc))

    def refetch_current_post(self) -> None:
        if self.current_post_id is None:
            return

        self.refetch_button.setEnabled(False)
        try:
            post = self.api.get_post(self.current_post_id)
            self.post_import_service.store_post(post)
            self.download_service.ensure_original_cached(self.current_post_id, force=True)
            self.load_current_post()
            QMessageBox.information(self, self.t("viewer.post_refetched_title", "Post Refetched"), self.t("viewer.post_refetched_message", "Post {post_id} was updated from Danbooru.", post_id=self.current_post_id))
        except Exception as exc:
            QMessageBox.critical(self, self.t("viewer.refetch_failed_title", "Refetch Failed"), str(exc))
        finally:
            self.refetch_button.setEnabled(True)

    def delete_current_post_from_database(self) -> None:
        if self.current_post_id is None:
            return

        post_id = self.current_post_id
        row = self.db.get_post_detail(post_id)
        final_path = str(row["final_file_path"] or "") if row is not None else ""

        answer = QMessageBox.question(
            self,
            self.t("viewer.remove_from_db_title", "Remove Post from DB"),
            self.t(
                "viewer.remove_from_db_confirm",
                "Really remove post {post_id} from the local database?\n\n",
                post_id=post_id,
            )
            + self.t("viewer.remove_from_db_note", "Image files are NOT deleted. Only the DB record, tags, review and category assignment are removed."),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.db.delete_post_record(post_id)
        self.status_changed.emit(post_id, "deleted")

        if post_id in self.post_ids:
            removed_index = self.post_ids.index(post_id)
            self.post_ids.pop(removed_index)
            if self.post_ids:
                self.current_index = min(removed_index, len(self.post_ids) - 1)
                self.load_current_post()
            else:
                self.current_post_id = None
                self.current_pixmap = None
                self.image_label.clear()
                self.info_label.setText(self.t("viewer.no_posts_left", "No posts left in viewer."))
                self.header_label.setText("")
                self.footer_label.setText("")
                self.score_label.setText("")
                self.final_path_label.setText("")
                self.filename_preview_label.setText("")

        QMessageBox.information(
            self,
            "Removed from DB",
            self.t("viewer.post_removed_from_db", "Post {post_id} was removed from the DB. Files were left untouched.\n{final_path}", post_id=post_id, final_path=final_path),
        )

    def selected_viewer_tags(self) -> list[str]:
        tags: list[str] = []
        seen: set[str] = set()

        for tag in self.tags_widget.selected_tags():
            tag = tag.strip()
            if tag and tag not in seen:
                tags.append(tag)
                seen.add(tag)

        return tags

    def tag_list_for_context_sender(self) -> QListWidget | None:
        sender = self.sender()
        return sender if isinstance(sender, QListWidget) else None

    def tags_for_context_position(self, position, list_widget: QListWidget | None = None) -> list[str]:  # noqa: ANN001
        if list_widget is None:
            list_widget = self.tag_list_for_context_sender()
        if list_widget is None:
            return []

        item = list_widget.itemAt(position)

        if item is not None and not item.isSelected():
            for other_list in self.tags_widget.lists.values():
                other_list.clearSelection()
            item.setSelected(True)
            return [str(item.data(Qt.UserRole) or item.text())]

        selected = self.selected_viewer_tags()
        if selected:
            return selected

        if item is not None:
            return [str(item.data(Qt.UserRole) or item.text())]

        return []

    def open_tag_context_menu(self, position) -> None:  # noqa: ANN001
        list_widget = self.tag_list_for_context_sender()
        tags = self.tags_for_context_position(position, list_widget)
        if not tags or list_widget is None:
            return

        frozen_tags = list(tags)
        menu = QMenu(self)
        self._tag_context_menu = menu

        category_menu = QMenu(self.t("viewer.add_to_category", "Add to Category"), menu)
        category_names = self.db.list_category_names()

        if not category_names:
            disabled = QAction(self.t("viewer.no_categories_available", "No categories available"), menu)
            disabled.setEnabled(False)
            category_menu.addAction(disabled)

        for category_name in category_names:
            include_action = QAction(f"{category_name} / include", menu)
            include_action.triggered.connect(
                lambda checked=False, c=category_name, t=list(frozen_tags): QTimer.singleShot(
                    0,
                    lambda: self.safe_tag_action(lambda: self.add_tags_to_category(t, c, "include")),
                )
            )
            category_menu.addAction(include_action)

            exclude_action = QAction(f"{category_name} / exclude", menu)
            exclude_action.triggered.connect(
                lambda checked=False, c=category_name, t=list(frozen_tags): QTimer.singleShot(
                    0,
                    lambda: self.safe_tag_action(lambda: self.add_tags_to_category(t, c, "exclude")),
                )
            )
            category_menu.addAction(exclude_action)

            category_menu.addSeparator()

        menu.addMenu(category_menu)
        menu.addSeparator()

        exclude_state = self.filename_exclude_state(frozen_tags)

        if exclude_state in {"none", "mixed"}:
            add_exclude_action = QAction(self.t("viewer.exclude_from_filename", "Exclude from Filename"), menu)
            add_exclude_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                    0,
                    lambda: self.safe_tag_action(lambda: self.add_tags_to_filename_exclude(t)),
                )
            )
            menu.addAction(add_exclude_action)

        if exclude_state in {"all", "mixed"}:
            remove_exclude_action = QAction("Remove filename exclude", menu)
            remove_exclude_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                    0,
                    lambda: self.safe_tag_action(lambda: self.remove_tags_from_filename_exclude(t)),
                )
            )
            menu.addAction(remove_exclude_action)

        fetch_state = self.fetch_exclude_state(frozen_tags)
        if fetch_state in {"none", "mixed"}:
            action = QAction(self.t("viewer.exclude_from_fetch", "Exclude from fetch"), menu)
            action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                    0, lambda: self.safe_tag_action(lambda: self.add_tags_to_fetch_exclude(t))
                )
            )
            menu.addAction(action)
        if fetch_state in {"all", "mixed"}:
            action = QAction(self.t("viewer.remove_fetch_exclude", "Remove fetch exclude"), menu)
            action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                    0, lambda: self.safe_tag_action(lambda: self.remove_tags_from_fetch_exclude(t))
                )
            )
            menu.addAction(action)

        menu.addSeparator()
        scoring_menu = QMenu("Scoring / usage", menu)
        scoring_actions = [
            (
                self.t("viewer.ignore_category_hint", "Ignore Category Hint"),
                "ignore_category_influence",
                True,
            ),
            (
                self.t("viewer.use_category_hint_again", "Use Category Hint Again"),
                "ignore_category_influence",
                False,
            ),
            (
                "Ignore preselection",
                "ignore_recommendation_score",
                True,
            ),
            (
                "Use preselection again",
                "ignore_recommendation_score",
                False,
            ),
            (
                "Ignore LLM input",
                "ignore_llm_input",
                True,
            ),
            (
                "Use LLM input again",
                "ignore_llm_input",
                False,
            ),
        ]
        for label, flag_name, flag_value in scoring_actions:
            action = QAction(label, menu)
            action.triggered.connect(
                lambda checked=False, t=list(frozen_tags), name=flag_name, value=flag_value: QTimer.singleShot(
                    0,
                    lambda: self.safe_tag_action(lambda: self.set_tag_scoring_flag(t, name, value)),
                )
            )
            scoring_menu.addAction(action)

        scoring_menu.addSeparator()
        ignore_all_action = QAction(self.t("viewer.ignore_all_auto_scores", "Ignore for All Automatic Scores"), menu)
        ignore_all_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                0,
                lambda: self.safe_tag_action(lambda: self.set_all_tag_scoring_flags(t, True)),
            )
        )
        scoring_menu.addAction(ignore_all_action)

        use_all_action = QAction(self.t("viewer.use_all_auto_scores_again", "Use for All Automatic Scores Again"), menu)
        use_all_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                0,
                lambda: self.safe_tag_action(lambda: self.set_all_tag_scoring_flags(t, False)),
            )
        )
        scoring_menu.addAction(use_all_action)
        menu.addMenu(scoring_menu)

        menu.addSeparator()

        alias_action = QAction("Edit alias", menu)
        alias_action.triggered.connect(
            lambda checked=False, tag=frozen_tags[0]: QTimer.singleShot(
                0,
                lambda: self.safe_tag_action(lambda: self.edit_tag_alias(tag)),
            )
        )
        menu.addAction(alias_action)

        score_action = QAction("Edit manual score", menu)
        score_action.triggered.connect(
            lambda checked=False, tag=frozen_tags[0]: QTimer.singleShot(
                0,
                lambda: self.safe_tag_action(lambda: self.edit_tag_score(tag)),
            )
        )
        menu.addAction(score_action)

        menu.addSeparator()

        copy_action = QAction("Copy tag(s)", menu)
        copy_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                0,
                lambda: self.copy_tags_to_clipboard(t),
            )
        )
        menu.addAction(copy_action)

        query_clipboard_action = QAction("Copy as query", menu)
        query_clipboard_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                0,
                lambda: self.copy_tags_to_clipboard(t),
            )
        )
        menu.addAction(query_clipboard_action)

        query_preview_action = QAction("Search as query in preview", menu)
        query_preview_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                0,
                lambda: self.query_requested.emit(" ".join(t)),
            )
        )
        menu.addAction(query_preview_action)

        menu.popup(list_widget.viewport().mapToGlobal(position))

    def safe_tag_action(self, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as exc:
            QMessageBox.critical(self, "Tag Action Failed", str(exc))

    def add_tags_to_category(self, tags: list[str], category_name: str, rule_type: str) -> None:
        for tag in tags:
            self.db.add_tag_to_category_rule(category_name, tag, rule_type)

        QMessageBox.information(
            self,
            self.t("viewer.category_updated_title", "Category Updated"),
            self.t("viewer.tags_added_to_category", "{count} tag(s) added to {category}/{rule_type}.", count=len(tags), category=category_name, rule_type=rule_type),
        )

        if self.current_post_id is not None:
            self.update_category_controls(self.current_post_id)

    def filename_exclude_state(self, tags: list[str]) -> str:
        excluded = self.db.filename_excluded_tag_set()
        count = sum(1 for tag in tags if tag in excluded)

        if count == 0:
            return "none"
        if count == len(tags):
            return "all"
        return "mixed"

    def fetch_exclude_state(self, tags: list[str]) -> str:
        excluded = self.db.fetch_excluded_tag_set()
        count = sum(1 for tag in tags if tag in excluded)
        if count == 0:
            return "none"
        if count == len(tags):
            return "all"
        return "mixed"

    def add_tags_to_fetch_exclude(self, tags: list[str]) -> None:
        for tag in tags:
            self.db.add_fetch_excluded_tag(tag, "viewer-manual")
        QMessageBox.information(
            self,
            self.t("viewer.fetch_exclude_title", "Fetch exclude"),
            self.t("viewer.tags_excluded_from_fetch", "{count} tag(s) excluded from future fetches.", count=len(tags)),
        )
        if self.current_post_id is not None:
            self.populate_tag_lists(self.current_post_id)

    def remove_tags_from_fetch_exclude(self, tags: list[str]) -> None:
        for tag in tags:
            self.db.remove_fetch_excluded_tag(tag)
        QMessageBox.information(
            self,
            self.t("viewer.fetch_exclude_title", "Fetch exclude"),
            self.t("viewer.fetch_excludes_removed", "{count} fetch exclude(s) removed.", count=len(tags)),
        )
        if self.current_post_id is not None:
            self.populate_tag_lists(self.current_post_id)

    def set_tag_scoring_flag(self, tags: list[str], flag_name: str, value: bool) -> None:
        allowed = {
            "ignore_category_influence",
            "ignore_recommendation_score",
            "ignore_llm_input",
        }
        if flag_name not in allowed:
            raise ValueError(f"Unknown scoring flag: {flag_name}")

        kwargs = {
            "ignore_category_influence": None,
            "ignore_recommendation_score": None,
            "ignore_llm_input": None,
        }
        kwargs[flag_name] = value
        for tag in tags:
            self.db.set_tag_scoring_flags(tag, **kwargs)
        self.final_save_service.category_engine.clear_category_influence_cache()

        if self.current_post_id is not None:
            self.populate_tag_lists(self.current_post_id)
            self.update_category_controls(self.current_post_id)

    def set_all_tag_scoring_flags(self, tags: list[str], value: bool) -> None:
        for tag in tags:
            self.db.set_tag_scoring_flags(
                tag,
                ignore_category_influence=value,
                ignore_recommendation_score=value,
                ignore_llm_input=value,
            )
        self.final_save_service.category_engine.clear_category_influence_cache()

        if self.current_post_id is not None:
            self.populate_tag_lists(self.current_post_id)
            self.update_category_controls(self.current_post_id)

    def add_tags_to_filename_exclude(self, tags: list[str], show_message: bool = True) -> None:
        for tag in tags:
            self.db.add_filename_excluded_tag(tag, "viewer-manual")

        if show_message:
            QMessageBox.information(
                self,
                self.t("viewer.filename_exclude_title", "Filename Exclude"),
                self.t("viewer.tags_excluded_from_filename", "{count} tag(s) excluded from filename.", count=len(tags)),
            )
        self.update_final_path_preview()
        if self.current_post_id is not None:
            self.populate_tag_lists(self.current_post_id)

    def remove_tags_from_filename_exclude(self, tags: list[str]) -> None:
        for tag in tags:
            self.db.remove_filename_excluded_tag(tag)

        QMessageBox.information(
            self,
            "Filename-Exclude",
            self.t("viewer.filename_excludes_removed", "{count} filename exclude(s) removed.", count=len(tags)),
        )
        self.update_final_path_preview()
        if self.current_post_id is not None:
            self.populate_tag_lists(self.current_post_id)

    def edit_tag_alias(self, tag: str) -> None:
        current_alias = ""
        rows = self.db.fetch_tag_overview(search_text=tag, limit=100)
        for row in rows:
            if str(row["tag"]) == tag:
                current_alias = str(row["alias_tag"] or "")
                break

        text, ok = QInputDialog.getText(
            self,
            "Edit alias",
            self.t("viewer.llm_alias_prompt", "LLM alias for tag '{tag}'\nLeave empty to remove:", tag=tag),
            text=current_alias,
        )

        if not ok:
            return

        self.db.set_tag_alias(tag, text.strip())
        self.final_save_service.category_engine.clear_category_influence_cache()
        if self.current_post_id is not None:
            self.populate_tag_lists(self.current_post_id)
            self.update_category_controls(self.current_post_id)

    def edit_tag_score(self, tag: str) -> None:
        current_value = 0.0
        rows = self.db.fetch_tag_overview(search_text=tag, limit=100)
        for row in rows:
            if str(row["tag"]) == tag and str(row["manual_score"]) not in {"", "None"}:
                try:
                    current_value = float(row["manual_score"])
                except ValueError:
                    current_value = 0.0
                break

        value, ok = QInputDialog.getDouble(
            self,
            "Manual score",
            self.t("viewer.manual_score_prompt", "Manual score for '{tag}' (-10 to +10):", tag=tag),
            current_value,
            -10.0,
            10.0,
            3,
        )

        if not ok:
            return

        self.db.set_tag_manual_score(tag, value)
        self.final_save_service.category_engine.clear_category_influence_cache()
        if self.current_post_id is not None:
            self.populate_tag_lists(self.current_post_id)
            self.update_category_controls(self.current_post_id)

    def copy_single_tag_from_item(self, item: QListWidgetItem) -> None:
        tag = str(item.data(Qt.UserRole) or item.text())
        self.copy_tags_to_clipboard([tag])

    def copy_tags_to_clipboard(self, tags: list[str]) -> None:
        QGuiApplication.clipboard().setText(" ".join(tags))

    def build_original_post_url(self) -> str:
        post_id = self.current_post_id_value()
        base_url = str(self.config.get("base_url", "https://danbooru.donmai.us")).rstrip("/")
        return f"{base_url}/posts/{post_id}"

    def open_original_post(self) -> None:
        webbrowser.open(self.build_original_post_url())

    def copy_original_post_url(self) -> None:
        QGuiApplication.clipboard().setText(self.build_original_post_url())

    def open_saved_folder(self) -> None:
        path: Path | None = None

        if self.last_saved_path is not None:
            path = self.last_saved_path.parent
        elif self.current_post_id is not None:
            row = self.db.get_post_detail(self.current_post_id)
            if row and row["final_directory"]:
                path = Path(str(row["final_directory"]))
            elif row and row["final_file_path"]:
                path = Path(str(row["final_file_path"])).parent

        if path is None:
            QMessageBox.information(self, self.t("viewer.no_target_folder_title", "No Target Folder"), self.t("viewer.no_target_folder_message", "No target folder known yet."))
            return

        if not path.exists():
            QMessageBox.warning(self, self.t("viewer.folder_missing_title", "Folder Missing"), self.t("viewer.folder_does_not_exist", "Folder does not exist:\n{folder}", folder=path))
            return

        os.startfile(path)

    def open_current_local_image(self) -> None:
        if self.current_post_id is None:
            return

        path = self.local_path_for_post(self.current_post_id)
        if path is None:
            QMessageBox.information(self, self.t("viewer.no_local_image_title", "No Local Image"), self.t("viewer.no_local_image_message", "No locally saved file exists for this post."))
            return

        self.open_local_path(path)
