from __future__ import annotations

import json
import shlex
import sqlite3
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QLabel,
    QLineEdit,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QStackedWidget,
)

from app.core.database import Database
from app.core.category_engine import build_category_match_groups
from app.core.recommendation_engine import RecommendationEngine
from app.gui.image_viewer import ImageViewerWindow
from app.gui.icon_utils import ensure_app_icon
from app.gui.fetch_tab import TagQueryLineEdit, TagSuggestionWorker
from app.gui.thumbnail_grid import ThumbnailGrid
from app.danbooru.api import DanbooruApi
from app.danbooru.thumbnail_cache import ThumbnailCache
from app.services.final_save_service import AlreadySavedError, FinalSaveService
from app.i18n.i18n import tr


def parse_preview_search_terms(search_text: str) -> tuple[list[str], list[str]]:
    try:
        tokens = shlex.split(search_text)
    except ValueError:
        tokens = search_text.split()

    positive: list[str] = []
    negative: list[str] = []

    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token.startswith("-") and len(token) > 1:
            negative.append(token[1:].strip())
        else:
            positive.append(token)

    return positive, negative


STATUS_LABELS: dict[str, str] = {
    "new": "New",
    "potential": "High Potential",
    "rejected": "Rejected",
    "already_known": "Already Known",
    "saved": "Saved",
}

STATUS_I18N_KEYS: dict[str, str] = {
    "new": "common.status.new",
    "potential": "common.status.potential",
    "rejected": "common.status.rejected",
    "already_known": "common.status.already_known",
    "saved": "common.status.saved",
}


STATUS_ORDER: list[str] = [
    "new",
    "potential",
    "rejected",
    "already_known",
    "saved",
]


DEFAULT_VISIBLE_STATUSES: set[str] = {
    "new",
    "potential",
}


VIEW_LABELS: dict[str, str] = {
    "filtered": "Status Filter",
    "worklist": "Worklist",
    "saved": "Saved",
    "rejected": "Rejected",
    "known": "Already Known",
    "all": "All Known Posts",
}

VIEW_I18N_KEYS: dict[str, str] = {
    "filtered": "preview.view.filtered",
    "worklist": "preview.view.worklist",
    "saved": "preview.view.saved",
    "rejected": "preview.view.rejected",
    "known": "preview.view.known",
    "all": "preview.view.all",
}


SORT_LABELS: dict[str, str] = {
    "id_desc": "Post ID: newest first",
    "id_asc": "Post ID: oldest first",
    "score_desc": "Danbooru Score: high → low",
    "score_asc": "Danbooru Score: low → high",
    "recommendation_desc": "Preselection: high → low",
    "recommendation_asc": "Preselection: low → high",
    "llm_score_desc": "LLM Score: high → low",
    "llm_score_asc": "LLM Score: low → high",
    "personal_desc": "Personal Rating: high → low",
    "personal_asc": "Personal Rating: low → high",
    "rating": "Danbooru Rating: general → explicit",
    "status": "Status",
    "category": "Category",
    "saved_desc": "Last saved",
    "seen_desc": "Last seen",
    "resolution_desc": "Resolution: large → small",
    "filesize_desc": "File size: large → small",
}

SORT_I18N_KEYS: dict[str, str] = {
    key: f"preview.sort.{key}" for key in SORT_LABELS
}


SQL_SORT_ORDER: dict[str, str] = {
    "id_desc": "p.id DESC",
    "id_asc": "p.id ASC",
    "score_desc": "COALESCE(p.score, -999999) DESC, p.id DESC",
    "score_asc": "COALESCE(p.score, 999999) ASC, p.id DESC",
    "llm_score_desc": "COALESCE(p.llm_score, -999999) DESC, p.id DESC",
    "llm_score_asc": "COALESCE(p.llm_score, 999999) ASC, p.id DESC",
    "personal_desc": "COALESCE(pr.stars, -1) DESC, p.id DESC",
    "personal_asc": "COALESCE(pr.stars, 999) ASC, p.id DESC",
    "rating": "CASE p.rating WHEN 'g' THEN 0 WHEN 's' THEN 1 WHEN 'q' THEN 2 WHEN 'e' THEN 3 ELSE 9 END ASC, p.id DESC",
    "status": "CASE p.status WHEN 'new' THEN 0 WHEN 'potential' THEN 1 WHEN 'saved' THEN 2 WHEN 'already_known' THEN 3 WHEN 'rejected' THEN 4 ELSE 9 END ASC, p.id DESC",
    "saved_desc": "COALESCE(p.saved_at, '') DESC, p.id DESC",
    "seen_desc": "COALESCE(p.last_seen_at, '') DESC, p.id DESC",
    "resolution_desc": "COALESCE(p.image_width, 0) * COALESCE(p.image_height, 0) DESC, p.id DESC",
    "filesize_desc": "COALESCE(p.file_size, 0) DESC, p.id DESC",
}


def preview_status_label(config: dict[str, Any], status: str) -> str:
    return tr(STATUS_I18N_KEYS.get(status, ""), STATUS_LABELS.get(status, status), config=config)


def preview_view_label(config: dict[str, Any], view_mode: str) -> str:
    return tr(VIEW_I18N_KEYS.get(view_mode, ""), VIEW_LABELS.get(view_mode, view_mode), config=config)


def preview_sort_label(config: dict[str, Any], sort_key: str) -> str:
    return tr(SORT_I18N_KEYS.get(sort_key, ""), SORT_LABELS.get(sort_key, sort_key), config=config)


class PreviewWindow(QMainWindow):
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.final_save_service = FinalSaveService(config, db)
        self.recommendation_engine = RecommendationEngine(db)
        self.current_limit = int((config.get("gui", {}) or {}).get("preview_limit", 100))
        self.current_offset = 0

        self.viewer_windows_by_post_id: dict[int, ImageViewerWindow] = {}

        self._applying_viewer_query = False
        self._pending_viewer_query: str | None = None
        self._is_reloading = False
        self._reload_pending = False
        self._syncing_status_checkboxes = False
        self._fetch_running = False
        self._has_loaded_once = False
        self._filters_dirty = True

        self.status_checkboxes: dict[str, QCheckBox] = {}
        self.category_rule_cache: list[dict[str, Any]] = []
        self.suggestion_thread: QThread | None = None
        self.suggestion_worker: TagSuggestionWorker | None = None
        self.pending_suggestion_token: str | None = None

        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.setInterval(250)
        self.reload_timer.timeout.connect(self.reload_posts)

        gui_config = config.get("gui", {}) or {}

        self.setWindowTitle("Danbooru Manager - Preview")
        self.setWindowIcon(ensure_app_icon(config))
        self.setAutoFillBackground(True)
        self.setStyleSheet("QMainWindow { background: #151515; }")

        self.toolbar_actions = QToolBar(tr("preview.toolbar.actions", "Preview Actions", config=self.config))
        self.toolbar_actions.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar_actions)

        self.reload_button = QPushButton(tr("preview.reload", "Reload", config=self.config))
        self.reload_button.clicked.connect(self.reload_posts)
        self.toolbar_actions.addWidget(self.reload_button)

        self.reload_thumbnails_button = QPushButton(tr("preview.reload_thumbnails", "Reload Thumbnail", config=self.config))
        self.reload_thumbnails_button.setToolTip(tr("preview.reload_thumbnails.tooltip", "Reloads thumbnails for the selected posts. Useful against gray placeholders.", config=self.config))
        self.reload_thumbnails_button.clicked.connect(self.reload_selected_thumbnails)
        self.toolbar_actions.addWidget(self.reload_thumbnails_button)

        self.final_save_button = QPushButton(tr("common.save", "Save", config=self.config))
        self.final_save_button.setToolTip(tr("preview.save.tooltip", "Save (F)", config=self.config))
        self.final_save_button.clicked.connect(self.final_save_selected_posts)
        self.toolbar_actions.addWidget(self.final_save_button)


        self.fetch_status_label = QLabel(tr("preview.fetch_running", "Fetch running…", config=self.config))
        self.fetch_status_label.setToolTip(tr("preview.fetch_running.tooltip", "Posts are currently being fetched from Danbooru. The preview may still be incomplete.", config=self.config))
        self.fetch_status_label.setStyleSheet(
            "QLabel { padding: 3px 8px; border: 1px solid #d6a000; "
            "border-radius: 6px; color: #ffd166; background: rgba(214, 160, 0, 0.12); }"
        )
        self.fetch_status_label.setVisible(False)
        self.toolbar_actions.addSeparator()
        self.toolbar_actions.addWidget(self.fetch_status_label)

        self.addToolBarBreak(Qt.TopToolBarArea)
        self.toolbar_filters = QToolBar(tr("preview.toolbar.filters", "Preview Filters", config=self.config))
        self.toolbar_filters.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar_filters)

        self.view_mode = QComboBox()
        self.view_mode.setToolTip(tr("preview.view.tooltip", "View / preset", config=self.config))
        for view_mode, label in VIEW_LABELS.items():
            self.view_mode.addItem(preview_view_label(self.config, view_mode), view_mode)

        self.view_mode.setCurrentIndex(self.view_mode.findData("filtered"))
        self.view_mode.currentIndexChanged.connect(self.on_view_mode_changed)
        self.toolbar_filters.addWidget(self.view_mode)

        self.toolbar_filters.addSeparator()

        self.all_status_checkbox = QCheckBox(tr("common.all", "All", config=self.config))
        self.all_status_checkbox.setToolTip(tr("preview.status.all.tooltip", "Show all statuses", config=self.config))
        self.all_status_checkbox.setChecked(False)
        self.all_status_checkbox.stateChanged.connect(self.on_all_status_changed)
        self.toolbar_filters.addWidget(self.all_status_checkbox)

        for status in STATUS_ORDER:
            checkbox = QCheckBox(preview_status_label(self.config, status))
            checkbox.setChecked(status in DEFAULT_VISIBLE_STATUSES)
            checkbox.stateChanged.connect(self.on_status_checkbox_changed)
            self.status_checkboxes[status] = checkbox
            self.toolbar_filters.addWidget(checkbox)

        self.toolbar_filters.addSeparator()

        self.category_filter = QComboBox()
        self.category_filter.setToolTip(tr("preview.category_filter.tooltip", "Category filter", config=self.config))
        self.category_filter.setMinimumWidth(180)
        self.category_filter.currentIndexChanged.connect(self.on_passive_filter_changed)
        self.toolbar_filters.addWidget(self.category_filter)

        self.toolbar_filters.addSeparator()

        self.toolbar_filters.addWidget(QLabel(tr("preview.preselection.label", "Preselection: ", config=self.config)))
        self.recommendation_filter_checkbox = QCheckBox("≥")
        self.recommendation_filter_checkbox.setToolTip(
            tr("preview.preselection.tooltip", "Filters the loaded preview candidates by local preselection score. Disabled means no score filter.", config=self.config)
        )
        self.recommendation_filter_checkbox.stateChanged.connect(self.on_passive_filter_changed)
        self.toolbar_filters.addWidget(self.recommendation_filter_checkbox)

        self.recommendation_min_spin = QDoubleSpinBox()
        self.recommendation_min_spin.setRange(-10.0, 10.0)
        self.recommendation_min_spin.setSingleStep(0.5)
        self.recommendation_min_spin.setDecimals(1)
        self.recommendation_min_spin.setValue(0.0)
        self.recommendation_min_spin.setKeyboardTracking(False)
        self.recommendation_min_spin.setToolTip(
            tr("preview.preselection_min.tooltip", "Minimum value for local preselection. The filter only applies when the checkbox on the left is enabled.", config=self.config)
        )
        self.recommendation_min_spin.valueChanged.connect(self.on_passive_filter_changed)
        self.toolbar_filters.addWidget(self.recommendation_min_spin)

        self.toolbar_filters.addSeparator()

        self.toolbar_filters.addWidget(QLabel(tr("common.search.label", "Search: ", config=self.config)))
        self.search_edit = TagQueryLineEdit()
        self.search_edit.setPlaceholderText(tr("preview.search.placeholder", "Search exact tags, e.g. brown_eyes -red_hair", config=self.config))
        self.search_edit.suggestions_requested.connect(self.request_tag_suggestions)
        self.search_edit.returnPressed.connect(self.reload_posts)
        self.search_edit.setMinimumWidth(280)
        self.toolbar_filters.addWidget(self.search_edit)

        self.search_button = QPushButton(tr("common.search", "Search", config=self.config))
        self.search_button.clicked.connect(self.reload_posts)
        self.toolbar_filters.addWidget(self.search_button)

        self.clear_search_button = QPushButton(tr("common.clear", "Clear", config=self.config))
        self.clear_search_button.clicked.connect(self.clear_search)
        self.toolbar_filters.addWidget(self.clear_search_button)

        self.addToolBarBreak(Qt.TopToolBarArea)
        self.toolbar_sort = QToolBar(tr("preview.toolbar.sort", "Preview Sorting", config=self.config))
        self.toolbar_sort.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar_sort)

        self.sort_combo = QComboBox()
        self.sort_combo.setToolTip(tr("preview.sort.tooltip", "Sorting", config=self.config))
        self.sort_combo.setMinimumWidth(240)
        for sort_key, sort_label in SORT_LABELS.items():
            self.sort_combo.addItem(preview_sort_label(self.config, sort_key), sort_key)
        saved_sort_key = str(gui_config.get("preview_sort_order", "id_desc") or "id_desc")
        saved_sort_index = self.sort_combo.findData(saved_sort_key)
        if saved_sort_index < 0:
            saved_sort_index = self.sort_combo.findData("id_desc")
        self.sort_combo.setCurrentIndex(saved_sort_index)
        self.sort_combo.currentIndexChanged.connect(self.on_sort_order_changed)
        self.toolbar_sort.addWidget(self.sort_combo)

        self.toolbar_sort.addSeparator()

        self.toolbar_sort.addWidget(QLabel(tr("common.limit.label", "Limit: ", config=self.config)))
        self.limit_spin = QSpinBox()
        self.limit_spin.setToolTip(tr("preview.limit.tooltip", "Limit / maximum number of displayed posts", config=self.config))
        self.limit_spin.setRange(50, 5000)
        self.limit_spin.setSingleStep(50)
        self.limit_spin.setValue(self.current_limit)
        self.limit_spin.setKeyboardTracking(False)
        self.limit_spin.lineEdit().returnPressed.connect(self.reload_posts)
        self.limit_spin.valueChanged.connect(self.on_passive_filter_changed)
        self.toolbar_sort.addWidget(self.limit_spin)

        self.toolbar_sort.addSeparator()

        self.toolbar_sort.addWidget(QLabel(tr("preview.thumbnail.label", "Thumbnail: ", config=self.config)))
        self.thumbnail_size_spin = QSpinBox()
        self.thumbnail_size_spin.setToolTip(tr("preview.thumbnail_size.tooltip", "Thumbnail size", config=self.config))
        self.thumbnail_size_spin.setRange(
            int(gui_config.get("thumbnail_size_min", 120)),
            int(gui_config.get("thumbnail_size_max", 600)),
        )
        self.thumbnail_size_spin.setSingleStep(int(gui_config.get("thumbnail_size_step", 20)))
        self.thumbnail_size_spin.setSuffix(" px")
        self.thumbnail_size_spin.setValue(int(gui_config.get("thumbnail_size", 280)))
        self.thumbnail_size_spin.setKeyboardTracking(False)
        self.thumbnail_size_spin.valueChanged.connect(self.on_thumbnail_size_changed)
        self.toolbar_sort.addWidget(self.thumbnail_size_spin)

        self.main_widget = QWidget()
        self.main_widget.setAutoFillBackground(True)
        self.main_widget.setStyleSheet("QWidget { background: #151515; }")
        self.main_layout = QVBoxLayout(self.main_widget)

        self.info_label = QLabel("")
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_label.setStyleSheet("QLabel { color: #dddddd; }")
        self.main_layout.addWidget(self.info_label)

        self.content_stack = QStackedWidget()
        self.content_stack.setAutoFillBackground(True)
        self.content_stack.setStyleSheet("QStackedWidget { background: #151515; }")

        self.loading_panel = self.create_loading_panel()

        self.grid = ThumbnailGrid(self.db, self.config)
        self.grid.status_changed.connect(self.on_status_changed)
        self.grid.statuses_changed.connect(self.on_statuses_changed)
        self.grid.request_reload.connect(self.schedule_reload)
        self.grid.open_viewer_requested.connect(self.open_viewer)
        self.grid.final_save_requested.connect(self.final_save_posts)
        self.grid.final_delete_requested.connect(self.delete_final_files_for_posts)
        self.grid.category_assign_requested.connect(self.assign_category_to_posts)
        self.grid.thumbnail_reload_requested.connect(self.reload_thumbnails_for_posts)
        self.grid.build_started.connect(self.on_grid_build_started)
        self.grid.build_progress.connect(self.on_grid_build_progress)
        self.grid.build_finished.connect(self.on_grid_build_finished)

        self.content_stack.addWidget(self.loading_panel)
        self.content_stack.addWidget(self.grid)
        self.content_stack.setCurrentWidget(self.loading_panel)
        self.main_layout.addWidget(self.content_stack, stretch=1)

        self.setCentralWidget(self.main_widget)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.sync_all_checkbox_from_statuses()
        self.reload_category_filter()
        self.show_preview_loading(tr("preview.ready_hint", "Preview ready. Choose a view or click Reload.", config=self.config))



    def create_loading_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("previewMainLoadingPanel")
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        panel.setStyleSheet(
            "QFrame#previewMainLoadingPanel { background: #151515; }"
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        layout.addStretch(1)

        self.loading_label = QLabel(tr("preview.loading", "Loading preview…", config=self.config))
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet(
            "QLabel { color: #eeeeee; font-size: 20px; font-weight: bold; }"
        )
        layout.addWidget(self.loading_label)

        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setMinimumHeight(20)
        self.loading_bar.setMaximumWidth(520)
        layout.addWidget(self.loading_bar, alignment=Qt.AlignHCenter)

        layout.addStretch(1)
        return panel

    def show_preview_loading(self, message: str = "") -> None:
        if not message:
            message = tr("preview.loading", "Loading preview…", config=self.config)
        self.loading_label.setText(message)
        self.loading_bar.setRange(0, 0)
        self.content_stack.setCurrentWidget(self.loading_panel)
        self.loading_panel.show()
        self.loading_panel.raise_()
        self.content_stack.update()
        self.main_widget.update()
        self.update()
        QApplication.processEvents()

    def hide_preview_loading(self) -> None:
        self.content_stack.setCurrentWidget(self.grid)
        self.grid.setVisible(True)
        self.grid.viewport().setVisible(True)
        self.grid.container.setVisible(True)
        self.grid.setUpdatesEnabled(True)
        self.grid.viewport().setUpdatesEnabled(True)
        self.grid.container.setUpdatesEnabled(True)
        self.grid.update_columns()
        if self.grid.items:
            self.grid.relayout()
        self.grid.container.adjustSize()
        self.grid.container.updateGeometry()
        self.grid.viewport().update()
        self.grid.updateGeometry()
        self.grid.update()
        self.content_stack.updateGeometry()
        self.content_stack.update()
        self.main_widget.updateGeometry()
        self.main_widget.update()
        self.update()
        QTimer.singleShot(0, self._force_preview_grid_repaint)

    def _force_preview_grid_repaint(self) -> None:
        if self.content_stack.currentWidget() is not self.grid:
            self.content_stack.setCurrentWidget(self.grid)
        self.grid.update_columns()
        if self.grid.items:
            self.grid.relayout()
        self.grid.viewport().update()
        self.grid.container.update()
        self.grid.update()
        self.content_stack.update()



    def request_tag_suggestions(self, token: str) -> None:
        token = str(token or "").strip()
        if len(token) < 2:
            return

        if self.suggestion_thread is not None:
            self.pending_suggestion_token = token
            return

        self.start_tag_suggestion_worker(token)

    def start_tag_suggestion_worker(self, token: str) -> None:
        database_file = Path(str(self.config["database_file"]))
        self.suggestion_thread = QThread(self)
        self.suggestion_worker = TagSuggestionWorker(database_file, token, limit=120)
        self.suggestion_worker.moveToThread(self.suggestion_thread)
        self.suggestion_thread.started.connect(self.suggestion_worker.run)
        self.suggestion_worker.finished.connect(self.on_tag_suggestions_loaded)
        self.suggestion_worker.failed.connect(self.on_tag_suggestions_failed)
        self.suggestion_worker.finished.connect(self.suggestion_thread.quit)
        self.suggestion_worker.failed.connect(self.suggestion_thread.quit)
        self.suggestion_thread.finished.connect(self.cleanup_suggestion_thread)
        self.suggestion_thread.start()

    def on_tag_suggestions_loaded(self, token: str, tags: list[str]) -> None:
        self.search_edit.set_tag_suggestions(token, tags)

    def on_tag_suggestions_failed(self, token: str, traceback_text: str) -> None:
        if bool(self.config.get("debug_startup")):
            self.status_bar.showMessage(tr("preview.tag_suggestions_failed", "Tag suggestions for '{token}' could not be loaded.", config=self.config, token=token), 5000)
            print(traceback_text, flush=True)

    def cleanup_suggestion_thread(self) -> None:
        self.suggestion_thread = None
        self.suggestion_worker = None
        pending = self.pending_suggestion_token
        self.pending_suggestion_token = None
        if pending and pending != self.search_edit.current_token():
            pending = self.search_edit.current_token()
        if pending and len(pending) >= 2 and self.search_edit.hasFocus():
            self.start_tag_suggestion_worker(pending)

    def on_grid_build_started(self, total: int) -> None:
        if total > 0:
            self.show_preview_loading(tr("preview.loading_thumbnails_progress", "Loading thumbnails… {current}/{total}", config=self.config, current=0, total=total))
            self.status_bar.showMessage(tr("preview.loading_cards_progress", "Loading preview cards… {current}/{total}", config=self.config, current=0, total=total))

    def on_grid_build_progress(self, current: int, total: int) -> None:
        if total > 0:
            self.loading_label.setText(tr("preview.loading_thumbnails_progress", "Loading thumbnails… {current}/{total}", config=self.config, current=current, total=total))
            self.status_bar.showMessage(tr("preview.loading_cards_progress", "Loading preview cards… {current}/{total}", config=self.config, current=current, total=total))
            QApplication.processEvents()

    def on_grid_build_finished(self, total: int) -> None:
        self.status_bar.showMessage(tr("preview.loaded_thumbnails", "Preview loaded: {total} thumbnail(s)", config=self.config, total=total), 5000)
        QTimer.singleShot(0, self.hide_preview_loading)

    @staticmethod
    def is_path_like_search_term(term: str) -> bool:
        return any(marker in term for marker in ("/", "\\", "."))

    def set_fetch_running(self, running: bool) -> None:
        self._fetch_running = bool(running)
        self.fetch_status_label.setVisible(self._fetch_running)

        if self._fetch_running:
            self.status_bar.showMessage(tr("preview.fetch_running_status", "Fetch running: preview will update as soon as new posts are loaded.", config=self.config))
            if not self.grid.has_visible_content():
                self.grid.show_empty_message(tr("preview.fetch_running_empty", "Fetch running… No posts in this view yet.", config=self.config))
        else:
            self.status_bar.showMessage(tr("preview.fetch_finished_status", "Fetch finished. Preview will update.", config=self.config), 5000)

        self.grid.viewport().update()
        self.grid.update()
        self.update()

    def preview_needs_reload(self) -> bool:
        if self._is_reloading or self._reload_pending:
            return True
        if self._filters_dirty or not self._has_loaded_once:
            return True
        if not self.grid.items and not self.grid.current_posts:
            return True
        return False

    def show_preview_grid_without_reload(self) -> None:
        self.content_stack.setCurrentWidget(self.grid)
        self.grid.setVisible(True)
        self.grid.viewport().setVisible(True)
        self.grid.container.setVisible(True)
        self.grid.update_columns()
        if self.grid.items:
            self.grid.relayout()
        self.grid.viewport().update()
        self.grid.container.update()
        self.grid.update()
        self.content_stack.update()
        self.main_widget.update()
        self.update()

    def on_tab_activated(self) -> None:
        # Stop blindly reloading on every tab switch. If valid thumbnails already
        # exist, just show them again. Reload only on first open or changed filters.
        # Revolutionary concept: do not do pointless work.
        if not self.preview_needs_reload():
            self.show_preview_grid_without_reload()
            self.status_bar.showMessage(tr("preview.ready", "Preview ready.", config=self.config), 3000)
            return

        self.show_preview_loading(tr("preview.loading", "Loading preview…", config=self.config))
        self.content_stack.setCurrentWidget(self.loading_panel)
        self.loading_panel.raise_()
        self.content_stack.repaint()
        self.main_widget.repaint()
        self.repaint()
        QTimer.singleShot(80, self.reload_posts)



    # Category filter / category suggestion
    # -------------------------------------------------------------------------

    def reload_category_filter(self) -> None:
        current_value = self.category_filter.currentData()

        self.category_filter.blockSignals(True)
        try:
            self.category_filter.clear()
            self.category_filter.addItem(tr("preview.category.all", "All Categories", config=self.config), "__all__")
            self.category_filter.addItem(tr("preview.category.unmatched", "_unmatched / no category", config=self.config), "__unmatched__")

            for row in self.db.list_categories_full():
                name = str(row["name"])
                self.category_filter.addItem(name, name)

            if current_value is not None:
                index = self.category_filter.findData(current_value)
                if index >= 0:
                    self.category_filter.setCurrentIndex(index)
        finally:
            self.category_filter.blockSignals(False)

    def selected_category_filter(self) -> str:
        value = self.category_filter.currentData()
        return str(value) if value is not None else "__all__"

    def selected_sort_key(self) -> str:
        value = self.sort_combo.currentData()
        return str(value) if value is not None else "id_desc"

    def selected_recommendation_minimum(self) -> float | None:
        if not self.recommendation_filter_checkbox.isChecked():
            return None
        return float(self.recommendation_min_spin.value())

    def load_category_rule_cache(self) -> None:
        categories = self.db.list_categories_full()
        rules = self.db.list_category_rules()

        by_category: dict[int, dict[str, Any]] = {}

        for category in categories:
            category_id = int(category["id"])
            by_category[category_id] = {
                "id": category_id,
                "name": str(category["name"]),
                "folder_name": str(category["folder_name"]),
                "sort_order": int(category["sort_order"] or 0),
                "include": set(),
                "exclude": set(),
                "groups": {},
            }

        rules_by_category: dict[int, list[Any]] = {}
        for rule in rules:
            category_id = int(rule["category_id"])
            if category_id not in by_category:
                continue
            rules_by_category.setdefault(category_id, []).append(rule)

        for category_id, category_rules in rules_by_category.items():
            by_category[category_id]["match_groups"] = build_category_match_groups(category_rules)

        self.category_rule_cache = sorted(
            by_category.values(),
            key=lambda entry: (entry["sort_order"], entry["name"]),
        )

    def suggest_category_from_tags(self, tags_text: str) -> str:
        tags = set(tags_text.split())

        for category in self.category_rule_cache:
            name = category["name"]

            match_groups = category.get("match_groups", [])
            if not match_groups:
                continue

            for required_tags, forbidden_tags in match_groups:
                if forbidden_tags.intersection(tags):
                    continue
                if required_tags and required_tags.issubset(tags):
                    return name

        return "_unmatched"

    def enrich_preview_rows_with_categories(self, rows: list[Any]) -> list[dict[str, Any]]:
        self.load_category_rule_cache()

        enriched: list[dict[str, Any]] = []

        for row in rows:
            data = dict(row)
            tags_text = str(data.get("tags") or "")
            tags = {tag for tag in tags_text.split() if tag}

            assigned_category = data.get("assigned_category_name")
            assigned_source = data.get("assigned_category_source")

            if assigned_category:
                data["preview_category_name"] = str(assigned_category)
                data["preview_category_source"] = str(assigned_source or "manual")
            else:
                data["preview_category_name"] = self.suggest_category_from_tags(tags_text)
                data["preview_category_source"] = "auto"

            recommendation = self.recommendation_engine.score_tags(tags)
            data["local_score"] = recommendation.score
            data["recommendation_score"] = recommendation.score
            data["recommendation_positive"] = ", ".join(recommendation.positive)
            data["recommendation_negative"] = ", ".join(recommendation.negative)
            data["recommendation_ignored_count"] = len(recommendation.ignored)
            data["recommendation_used_count"] = recommendation.used_count

            # Until a later LLM scorer exists, final_score mirrors the local
            # recommendation value when no explicit final_score was persisted.
            if data.get("final_score") is None:
                data["final_score"] = recommendation.score

            enriched.append(data)

        return enriched

    def sort_preview_rows_in_python(self, rows: list[dict[str, Any]], sort_key: str) -> list[dict[str, Any]]:
        if sort_key == "category":
            return sorted(
                rows,
                key=lambda row: (
                    str(row.get("preview_category_name") or "_unmatched").lower(),
                    -int(row.get("id") or 0),
                ),
            )

        if sort_key == "recommendation_desc":
            return sorted(
                rows,
                key=lambda row: (
                    -float(row.get("recommendation_score") or 0.0),
                    -int(row.get("id") or 0),
                ),
            )

        if sort_key == "recommendation_asc":
            return sorted(
                rows,
                key=lambda row: (
                    float(row.get("recommendation_score") or 0.0),
                    -int(row.get("id") or 0),
                ),
            )

        return rows

    def preview_relation_group_key(self, row: dict[str, Any]) -> int:
        try:
            parent_id = row.get("parent_id")
            return int(parent_id) if parent_id is not None else int(row.get("id") or 0)
        except Exception:
            return int(row.get("id") or 0)

    def group_related_preview_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep Parent/Child posts adjacent while preserving the chosen sort order by first hit.

        This only groups rows that are already in the fetched/filtered result set. It avoids the
        classic review annoyance where a child shows up 20 cards later and pretends to be new.
        """
        if len(rows) < 2:
            return rows

        grouped: dict[int, list[dict[str, Any]]] = {}
        order: list[int] = []
        for row in rows:
            key = self.preview_relation_group_key(row)
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(row)

        result: list[dict[str, Any]] = []
        for key in order:
            group = grouped[key]
            if len(group) > 1:
                group = sorted(
                    group,
                    key=lambda row: (
                        0 if int(row.get("id") or 0) == key else 1,
                        -int(row.get("id") or 0),
                    ),
                )
            result.extend(group)
        return result

    def category_matches_filter(self, row: dict[str, Any], category_filter: str) -> bool:
        if category_filter == "__all__":
            return True

        category_name = str(row.get("preview_category_name") or "_unmatched")

        if category_filter == "__unmatched__":
            return category_name in {"", "_unmatched", "None"}

        return category_name == category_filter

    def recommendation_matches_filter(self, row: dict[str, Any], minimum: float | None) -> bool:
        if minimum is None:
            return True
        try:
            score = float(row.get("recommendation_score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        return score >= minimum

    def preview_score_summary(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "Best – | Worst – | Average –"

        scores: list[float] = []
        for row in rows:
            try:
                scores.append(float(row.get("recommendation_score") or 0.0))
            except (TypeError, ValueError):
                scores.append(0.0)

        best = max(scores) if scores else 0.0
        worst = min(scores) if scores else 0.0
        average = sum(scores) / len(scores) if scores else 0.0
        return (
            f"Best {best:+.1f} | Worst {worst:+.1f} | Average {average:+.1f}"
        )

    def assign_category_to_posts(self, post_ids: list[int], category_name: str) -> None:
        if not post_ids:
            return

        category = self.db.get_category_by_name(category_name)
        if category is None:
            self.status_bar.showMessage(tr("preview.category_not_found", "Category not found: {category}", config=self.config, category=category_name))
            return

        category_id = int(category["id"])

        for post_id in post_ids:
            self.db.execute(
                """
                DELETE FROM post_categories
                WHERE post_id = ?
                """,
                (int(post_id),),
            )
            self.db.execute(
                """
                INSERT INTO post_categories (post_id, category_id, source)
                VALUES (?, ?, ?)
                """,
                (int(post_id), category_id, "manual"),
            )

            self.grid.update_card_category(int(post_id), category_name, "manual")

        self.db.commit()

        # Intentionally no popup. The review workflow should not be shredded by dialogs.
        self.status_bar.showMessage(tr("preview.category_assigned", "{count} post(s) → category {category}", config=self.config, count=len(post_ids), category=category_name))

    # -------------------------------------------------------------------------
    # Status-Checkbox-Filter
    # -------------------------------------------------------------------------

    def on_view_mode_changed(self, *_args) -> None:
        mode = self.selected_view_mode()

        if mode == "filtered":
            self.schedule_reload()
            return

        presets: dict[str, set[str]] = {
            "worklist": {"new", "potential"},
            "saved": {"saved"},
            "rejected": {"rejected"},
            "known": {"already_known"},
            "all": set(STATUS_ORDER),
        }

        statuses = presets.get(mode, DEFAULT_VISIBLE_STATUSES)
        self.set_checked_statuses(statuses)
        self.schedule_reload()

    def on_all_status_changed(self, state: int) -> None:
        if self._syncing_status_checkboxes:
            return

        checked = state == Qt.Checked

        self._syncing_status_checkboxes = True
        try:
            for checkbox in self.status_checkboxes.values():
                checkbox.setChecked(checked)
        finally:
            self._syncing_status_checkboxes = False
        self._fetch_running = False

        self.on_passive_filter_changed()

    def on_status_checkbox_changed(self, *_args) -> None:
        if self._syncing_status_checkboxes:
            return

        self.sync_all_checkbox_from_statuses()

        if self.selected_view_mode() != "filtered":
            filtered_index = self.view_mode.findData("filtered")
            if filtered_index >= 0:
                self.view_mode.blockSignals(True)
                try:
                    self.view_mode.setCurrentIndex(filtered_index)
                finally:
                    self.view_mode.blockSignals(False)

        self.on_passive_filter_changed()

    def sync_all_checkbox_from_statuses(self) -> None:
        all_checked = all(checkbox.isChecked() for checkbox in self.status_checkboxes.values())

        self._syncing_status_checkboxes = True
        try:
            self.all_status_checkbox.setChecked(all_checked)
        finally:
            self._syncing_status_checkboxes = False
        self._fetch_running = False

    def set_checked_statuses(self, statuses: set[str]) -> None:
        self._syncing_status_checkboxes = True
        try:
            for status, checkbox in self.status_checkboxes.items():
                checkbox.setChecked(status in statuses)
        finally:
            self._syncing_status_checkboxes = False
        self._fetch_running = False

        self.sync_all_checkbox_from_statuses()

    def selected_statuses(self) -> list[str]:
        return [
            status
            for status in STATUS_ORDER
            if self.status_checkboxes[status].isChecked()
        ]

    # -------------------------------------------------------------------------
    # Reload / Filter
    # -------------------------------------------------------------------------

    def on_sort_order_changed(self, *_args) -> None:
        sort_key = self.selected_sort_key()
        gui_config = self.config.setdefault("gui", {})
        if isinstance(gui_config, dict):
            gui_config["preview_sort_order"] = sort_key

        try:
            self.db.set_app_setting("gui.preview_sort_order", json.dumps(sort_key, ensure_ascii=False))
        except Exception as exc:
            # Sorting should not tear down the whole previewer just because SQLite
            # is currently offended. The visible reload still stays correct.
            self.status_bar.showMessage(tr("preview.sort_save_failed", "Sorting could not be saved: {error}", config=self.config, error=exc), 8000)

        self.on_passive_filter_changed()

    def on_passive_filter_changed(self, *_args) -> None:
        self._filters_dirty = True
        self.status_bar.showMessage(tr("preview.filter_changed", "Filter changed. Preview reloads automatically…", config=self.config), 3000)
        self.schedule_reload()

    def schedule_reload(self, *_args) -> None:
        if self._applying_viewer_query:
            return

        if self._is_reloading:
            self._reload_pending = True
            return

        self.reload_timer.start()

    def selected_view_mode(self) -> str:
        return str(self.view_mode.currentData())

    def current_search_text(self) -> str | None:
        text = self.search_edit.text().strip()
        return text or None

    def clear_search(self) -> None:
        self.search_edit.clear()
        self.reload_posts()

    def on_thumbnail_size_changed(self, size: int) -> None:
        self.grid.set_thumbnail_size(int(size))
        self.status_bar.showMessage(tr("preview.thumbnail_size_status", "Thumbnail size: {size}px", config=self.config, size=size))

    def reload_posts(self) -> None:
        if self._applying_viewer_query:
            return

        if self._is_reloading:
            self._reload_pending = True
            return

        self.reload_timer.stop()
        self._is_reloading = True
        self.show_preview_loading(tr("preview.loading", "Loading preview…", config=self.config))
        self.status_bar.showMessage(tr("preview.loading", "Loading preview…", config=self.config))
        QApplication.processEvents()

        try:
            statuses = self.selected_statuses()
            text_filter = self.current_search_text()
            category_filter = self.selected_category_filter()
            recommendation_minimum = self.selected_recommendation_minimum()
            sort_key = self.selected_sort_key()
            self.current_limit = int(self.limit_spin.value())

            base_total = self.count_preview_posts_by_statuses(
                statuses=statuses,
                text_filter=text_filter,
            )

            python_filtered_or_sorted = (
                category_filter != "__all__"
                or recommendation_minimum is not None
                or sort_key in {"category", "recommendation_desc", "recommendation_asc"}
            )

            # Category and preselection are currently calculated in Python. This needs
            # more than just the visible 50 rows, otherwise "Shown: 50/256" would be
            # another pretty lie with a UI frame. The upper bound prevents a huge DB
            # from taking the previewer hostage.
            analysis_cap = 10000
            if python_filtered_or_sorted:
                internal_limit = max(self.current_limit, min(base_total, analysis_cap))
            else:
                internal_limit = self.current_limit

            candidates = self.fetch_preview_posts_by_statuses(
                statuses=statuses,
                text_filter=text_filter,
                limit=internal_limit,
                offset=self.current_offset,
                sort_key=sort_key,
            )
            enriched = self.enrich_preview_rows_with_categories(candidates)
            filtered = [
                row
                for row in enriched
                if self.category_matches_filter(row, category_filter)
                and self.recommendation_matches_filter(row, recommendation_minimum)
            ]
            filtered = self.sort_preview_rows_in_python(filtered, sort_key)
            filtered = self.group_related_preview_rows(filtered)

            posts = filtered[: self.current_limit]
            total_filtered = len(filtered) if python_filtered_or_sorted else base_total
            total_suffix = ""
            if python_filtered_or_sorted and base_total > internal_limit:
                total_suffix = "+"

            self.grid.set_posts(posts)
            self._has_loaded_once = True
            self._filters_dirty = False

            score_summary = self.preview_score_summary(filtered if python_filtered_or_sorted else enriched)

            self.info_label.setText(
                tr("preview.info_displayed", "Displayed: {shown}/{total}{suffix}", config=self.config, shown=len(posts), total=total_filtered, suffix=total_suffix)
                + "\n"
                + score_summary
            )
            if posts:
                self.status_bar.showMessage(tr("preview.loading_cards_progress", "Loading preview cards… {current}/{total}", config=self.config, current=0, total=len(posts)))
            else:
                self.hide_preview_loading()
                self.status_bar.showMessage(tr("preview.loaded_no_hits", "Preview loaded: no hits", config=self.config), 5000)

        except sqlite3.OperationalError as exc:
            if "database is locked" in str(exc).lower() or "database table is locked" in str(exc).lower():
                self.show_preview_loading(
                    tr("preview.database_busy", "Database is busy. Fetch or save is still running. Please reload again shortly.", config=self.config)
                )
                self.loading_bar.setRange(0, 1)
                self.loading_bar.setValue(0)
                self.status_bar.showMessage(tr("preview.database_locked", "Database is locked. Preview is waiting for the next reload.", config=self.config), 8000)
                self._reload_pending = True
            else:
                raise
        finally:
            self._is_reloading = False

        if self._reload_pending:
            self._reload_pending = False
            self.schedule_reload()

    def status_filter_description(self, statuses: list[str]) -> str:
        if not statuses:
            return tr("common.none", "None", config=self.config)

        if set(statuses) == set(STATUS_ORDER):
            return tr("common.all", "All", config=self.config)

        return ", ".join(preview_status_label(self.config, status) for status in statuses)

    def build_preview_where(
        self,
        statuses: list[str],
        text_filter: str | None,
    ) -> tuple[str, list[Any]]:
        where_parts: list[str] = []
        parameters: list[Any] = []

        # Statusfilter gilt immer, auch bei Tag-/Textsuche.
        # Wer gespeicherte lokale Bilder suchen will, aktiviert den Status "saved"
        # or the "All known posts" view. Revolutionary concept: filters filter.
        if not statuses:
            where_parts.append("1 = 0")
        elif set(statuses) != set(STATUS_ORDER):
            placeholders = ", ".join("?" for _ in statuses)
            where_parts.append(f"p.status IN ({placeholders})")
            parameters.extend(statuses)

        if text_filter:
            positive_terms, negative_terms = parse_preview_search_terms(text_filter)

            for term in positive_terms:
                pattern = f"%{term}%"
                if self.is_path_like_search_term(term):
                    where_parts.append(
                        """
                        (
                            CAST(p.id AS TEXT) LIKE ?
                            OR p.final_file_path LIKE ?
                            OR p.final_directory LIKE ?
                            OR EXISTS (
                                SELECT 1
                                FROM post_tags pt
                                WHERE pt.post_id = p.id
                                  AND pt.tag = ? COLLATE NOCASE
                            )
                        )
                        """
                    )
                    parameters.extend([pattern, pattern, pattern, term])
                else:
                    where_parts.append(
                        """
                        (
                            CAST(p.id AS TEXT) LIKE ?
                            OR EXISTS (
                                SELECT 1
                                FROM post_tags pt
                                WHERE pt.post_id = p.id
                                  AND pt.tag = ? COLLATE NOCASE
                            )
                        )
                        """
                    )
                    parameters.extend([pattern, term])

            for term in negative_terms:
                where_parts.append(
                    """
                    NOT EXISTS (
                        SELECT 1
                        FROM post_tags pt_excl
                        WHERE pt_excl.post_id = p.id
                          AND pt_excl.tag = ? COLLATE NOCASE
                    )
                    """
                )
                parameters.append(term)

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        return where_sql, parameters

    def count_preview_posts_by_statuses(
        self,
        statuses: list[str],
        text_filter: str | None,
    ) -> int:
        where_sql, parameters = self.build_preview_where(statuses, text_filter)
        row = self.db.execute(
            f"""
            SELECT COUNT(DISTINCT p.id) AS total
            FROM posts p
            LEFT JOIN post_reviews pr ON pr.post_id = p.id
            {where_sql}
            """,
            parameters,
        ).fetchone()
        if row is None:
            return 0
        return int(row["total"] or 0)

    def fetch_preview_posts_by_statuses(
        self,
        statuses: list[str],
        text_filter: str | None,
        limit: int,
        offset: int,
        sort_key: str = "id_desc",
    ) -> list[Any]:
        where_sql, parameters = self.build_preview_where(statuses, text_filter)
        order_sql = SQL_SORT_ORDER.get(sort_key, SQL_SORT_ORDER["id_desc"])
        parameters.extend([limit, offset])

        return list(
            self.db.execute(
                f"""
                SELECT
                    p.id,
                    p.rating,
                    p.score,
                    p.fav_count,
                    p.thumbnail_path,
                    p.rejected_thumbnail_path,
                    p.file_url,
                    p.large_file_url,
                    p.preview_url,
                    p.file_ext,
                    p.parent_id,
                    p.has_children,
                    p.status,
                    p.local_score,
                    p.llm_score,
                    p.llm_decision,
                    p.llm_category,
                    p.llm_reason,
                    p.llm_model,
                    p.llm_reviewed_at,
                    p.final_score,
                    p.final_file_path,
                    p.final_directory,
                    p.rejected_at,
                    p.saved_at,
                    p.already_known_at,

                    assigned_category.name AS assigned_category_name,
                    pc.source AS assigned_category_source,

                    CASE
                        WHEN p.parent_id IS NOT NULL
                         AND EXISTS (SELECT 1 FROM posts parent WHERE parent.id = p.parent_id)
                        THEN 1
                        ELSE 0
                    END AS known_parent_loaded,

                    (
                        SELECT COUNT(*)
                        FROM posts child
                        WHERE child.parent_id = p.id
                    ) AS known_child_count,

                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id
                        ORDER BY
                            CASE pt.tag_type
                                WHEN 'copyright' THEN 1
                                WHEN 'character' THEN 2
                                WHEN 'artist' THEN 3
                                WHEN 'general' THEN 4
                                WHEN 'meta' THEN 5
                                ELSE 9
                            END,
                            pt.tag
                    ) AS tags,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'general'
                        ORDER BY pt.tag
                    ) AS tags_general,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'character'
                        ORDER BY pt.tag
                    ) AS tags_character,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'copyright'
                        ORDER BY pt.tag
                    ) AS tags_copyright,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'artist'
                        ORDER BY pt.tag
                    ) AS tags_artist,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'meta'
                        ORDER BY pt.tag
                    ) AS tags_meta
                FROM posts p
                LEFT JOIN post_categories pc ON pc.post_id = p.id
                LEFT JOIN categories assigned_category ON assigned_category.id = pc.category_id
                LEFT JOIN post_reviews pr ON pr.post_id = p.id
                {where_sql}
                GROUP BY p.id
                ORDER BY {order_sql}
                LIMIT ?
                OFFSET ?
                """,
                parameters,
            ).fetchall()
        )

    # -------------------------------------------------------------------------
    # Thumbnail repair from preview
    # -------------------------------------------------------------------------

    def reload_selected_thumbnails(self) -> None:
        post_ids = self.grid.selected_or_current_post_ids()
        self.reload_thumbnails_for_posts(post_ids)

    def reload_thumbnails_for_posts(self, post_ids: list[int]) -> None:
        clean_ids = [int(post_id) for post_id in post_ids if post_id]
        if not clean_ids:
            self.status_bar.showMessage(tr("preview.reload_thumbnail.none", "Reload thumbnail: no post selected.", config=self.config), 4000)
            return

        self.reload_thumbnails_button.setEnabled(False)
        self.status_bar.showMessage(f"Reloading {len(clean_ids)} thumbnail(s)…")
        QApplication.processEvents()

        api = DanbooruApi(self.config)
        cache = ThumbnailCache(self.config, api.session)
        updated = 0
        failed: list[str] = []

        try:
            for post_id in clean_ids:
                try:
                    post = self.thumbnail_post_payload_from_db(post_id)
                    thumbnail_path = cache.cache_thumbnail(post, force=True)
                    if not thumbnail_path:
                        failed.append(str(post_id))
                        continue

                    self.db.execute(
                        "UPDATE posts SET thumbnail_path = ? WHERE id = ?",
                        (thumbnail_path, post_id),
                    )
                    self.db.commit()
                    self.grid.update_card_thumbnail(post_id, thumbnail_path)
                    updated += 1
                except Exception as exc:  # noqa: BLE001
                    failed.append(f"{post_id}: {exc}")
        finally:
            self.reload_thumbnails_button.setEnabled(True)

        if failed:
            self.status_bar.showMessage(
                tr("preview.reload_thumbnail.done_with_errors", "Thumbnails reloaded: {updated}, errors: {errors}", config=self.config, updated=updated, errors=len(failed)),
                8000,
            )
            QMessageBox.warning(
                self,
                tr("preview.reload_thumbnails", "Reload Thumbnail", config=self.config),
                tr("preview.reload_thumbnail.some_failed", "Some thumbnails could not be reloaded:\n", config=self.config) + "\n".join(failed[:12]),
            )
        else:
            self.status_bar.showMessage(tr("preview.reload_thumbnail.done", "Thumbnails reloaded: {updated}", config=self.config, updated=updated), 5000)

    def thumbnail_post_payload_from_db(self, post_id: int) -> dict[str, Any]:
        row = self.db.execute(
            """
            SELECT id, file_url, large_file_url, preview_url, file_ext
            FROM posts
            WHERE id = ?
            """,
            (int(post_id),),
        ).fetchone()
        if row is None:
            raise RuntimeError(tr("preview.post_not_in_db", "Post {post_id} is not in the database", config=self.config, post_id=post_id))

        post = {
            "id": int(row["id"]),
            "file_url": row["file_url"],
            "large_file_url": row["large_file_url"],
            "preview_file_url": row["preview_url"],
            "file_ext": row["file_ext"],
        }

        if not (post["file_url"] or post["large_file_url"] or post["preview_file_url"]):
            # Old DB rows can contain broken or missing URLs. In that case, refetch
            # the post. Sometimes data needs to be asked again because it acted
            # clueless the first time.
            post = api_post = DanbooruApi(self.config).get_post(int(post_id))
            self.db.execute(
                """
                UPDATE posts
                SET file_url = ?, large_file_url = ?, preview_url = ?, file_ext = ?
                WHERE id = ?
                """,
                (
                    api_post.get("file_url"),
                    api_post.get("large_file_url"),
                    api_post.get("preview_file_url"),
                    api_post.get("file_ext"),
                    int(post_id),
                ),
            )
            self.db.commit()

        return post

    # -------------------------------------------------------------------------
    # Save from preview
    # -------------------------------------------------------------------------

    def final_save_selected_posts(self) -> None:
        post_ids = self.grid.selected_or_current_post_ids()
        self.final_save_posts(post_ids)

    def final_save_posts(self, post_ids: list[int]) -> None:
        if not post_ids:
            self.status_bar.showMessage(tr("preview.save.none", "Save: no posts selected.", config=self.config))
            return

        saved: list[str] = []
        skipped: list[str] = []
        failed: list[str] = []

        self.final_save_button.setEnabled(False)
        try:
            for post_id in post_ids:
                try:
                    result = self.final_save_service.save_post(int(post_id), category=None)
                    saved.append(f"{post_id}: {result.final_path}")
                    self.grid.update_card_status(int(post_id), "saved")
                    self.grid.update_card_category(int(post_id), result.category.name, result.category_source)
                except AlreadySavedError as exc:
                    skipped.append(str(exc))
                    self.grid.update_card_status(int(post_id), "saved")
                except Exception as exc:
                    failed.append(f"{post_id}: {exc}")
        finally:
            self.final_save_button.setEnabled(True)

        parts: list[str] = []

        if saved:
            parts.append(tr("preview.save.saved_count", "Saved: {count}", config=self.config, count=len(saved)))
        if skipped:
            parts.append(tr("preview.save.skipped_count", "Already saved/skipped: {count}", config=self.config, count=len(skipped)))
        if failed:
            parts.append(tr("preview.errors_count", "Errors: {count}", config=self.config, count=len(failed)))

        summary = " | ".join(parts) if parts else tr("preview.no_action_done", "Nothing done.", config=self.config)
        self.status_bar.showMessage(summary)

        if failed:
            QMessageBox.warning(
                self,
                tr("common.save", "Save", config=self.config),
                summary + tr("preview.error_block", "\n\nErrors:\n", config=self.config) + "\n".join(failed[:10]),
            )

    def delete_final_files_for_posts(self, post_ids: list[int]) -> None:
        clean_ids = []
        seen: set[int] = set()
        for post_id in post_ids:
            post_id_int = int(post_id)
            if post_id_int in seen:
                continue
            seen.add(post_id_int)
            clean_ids.append(post_id_int)

        if not clean_ids:
            self.status_bar.showMessage(tr("preview.delete_local.none", "Delete local file: no post selected.", config=self.config), 4000)
            return

        rows = []
        missing = []
        for post_id in clean_ids:
            row = self.db.get_post_detail(post_id)
            final_path = Path(str(row["final_file_path"])) if row is not None and row["final_file_path"] else None
            if final_path is None:
                missing.append(f"{post_id}: " + tr("preview.delete_local.no_path_short", "no local path", config=self.config))
                continue
            rows.append((post_id, row, final_path))

        if not rows:
            QMessageBox.information(
                self,
                tr("preview.delete_local.title", "Delete Local File", config=self.config),
                tr("preview.delete_local.no_path", "No local storage path is set for the selection.\n", config=self.config) + "\n".join(missing[:10]),
            )
            return

        preview_lines = [f"{post_id}: {path}" for post_id, _row, path in rows[:12]]
        if len(rows) > 12:
            preview_lines.append(tr("preview.and_more", "... and {count} more", config=self.config, count=len(rows) - 12))

        answer = QMessageBox.question(
            self,
            tr("preview.delete_local.title_plural", "Delete Local Files", config=self.config),
            (
                tr("preview.delete_local.confirm", "These local file(s) will be deleted.\nThe database entries stay in place, but local file paths will be cleared.\n\n", config=self.config)
                + "\n".join(preview_lines)
            ),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        deleted = 0
        failed: list[str] = []
        for post_id, row, path in rows:
            try:
                if path.exists():
                    if not path.is_file():
                        raise RuntimeError(tr("preview.delete_local.path_not_file", "Path is not a file", config=self.config))
                    path.unlink()
                new_status = "new" if str(row["status"] or "") == "saved" else None
                self.db.clear_post_final_file_path(post_id, new_status=new_status)
                deleted += 1
                self.grid.update_card_status(post_id, new_status or str(row["status"] or "new"))
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{post_id}: {exc}")

        self.schedule_reload()
        self.status_bar.showMessage(tr("preview.delete_local.done", "Local files deleted: {deleted}, errors: {errors}", config=self.config, deleted=deleted, errors=len(failed)), 8000)
        if failed:
            QMessageBox.warning(
                self,
                tr("preview.delete_local.title_plural", "Delete Local Files", config=self.config),
                tr("preview.delete_local.error_summary", "Deleted: {deleted}\nErrors: {errors}\n\n", config=self.config, deleted=deleted, errors=len(failed)) + "\n".join(failed[:12]),
            )

    # -------------------------------------------------------------------------
    # Viewer / Status
    # -------------------------------------------------------------------------

    def on_status_changed(self, post_id: int, status: str) -> None:
        if status == "deleted":
            self.status_bar.showMessage(tr("preview.post_removed", "Post {post_id} was removed from the database", config=self.config, post_id=post_id))
            self.schedule_reload()
            return

        self.grid.update_card_status(post_id, status)
        self.status_bar.showMessage(tr("preview.status_changed", "Post {post_id} → {status}", config=self.config, post_id=post_id, status=preview_status_label(self.config, status)))


    def on_statuses_changed(self, post_ids: list[int], status: str) -> None:
        count = len(post_ids)
        self.status_bar.showMessage(tr("preview.statuses_changed", "{count} post(s) → {status}", config=self.config, count=count, status=preview_status_label(self.config, status)))

    def open_viewer(self, post_id: int) -> None:
        post_id = int(post_id)

        existing = self.viewer_windows_by_post_id.get(post_id)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return

        post_ids = self.grid.visible_post_ids()
        viewer = ImageViewerWindow(self.config, self.db, post_ids, post_id)
        viewer.status_changed.connect(self.on_status_changed)
        viewer.query_requested.connect(self.schedule_viewer_query)
        viewer.destroyed.connect(lambda *_args, pid=post_id: self.remove_viewer(pid))

        self.viewer_windows_by_post_id[post_id] = viewer

        viewer.resize(1500, 950)
        viewer.show()

    def remove_viewer(self, post_id: int) -> None:
        self.viewer_windows_by_post_id.pop(int(post_id), None)

    def schedule_viewer_query(self, query: str) -> None:
        query = query.strip()
        if not query:
            return

        self._pending_viewer_query = query
        QTimer.singleShot(0, self.apply_pending_viewer_query)

    def apply_pending_viewer_query(self) -> None:
        query = self._pending_viewer_query
        self._pending_viewer_query = None

        if not query:
            return

        self._applying_viewer_query = True
        try:
            self.search_edit.setText(query)

            filtered_index = self.view_mode.findData("filtered")
            if filtered_index >= 0:
                self.view_mode.blockSignals(True)
                try:
                    self.view_mode.setCurrentIndex(filtered_index)
                finally:
                    self.view_mode.blockSignals(False)

            self.set_checked_statuses(set(STATUS_ORDER))

        finally:
            self._applying_viewer_query = False

        self.reload_posts()
        self.status_bar.showMessage(tr("preview.query_from_viewer", "Query from viewer applied: {query}", config=self.config, query=query))

    def cleanup_viewers(self) -> None:
        self.viewer_windows_by_post_id = {
            post_id: viewer
            for post_id, viewer in self.viewer_windows_by_post_id.items()
            if viewer.isVisible()
        }
