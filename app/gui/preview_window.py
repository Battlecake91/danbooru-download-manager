from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
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
from app.gui.image_viewer import ImageViewerWindow
from app.gui.thumbnail_grid import ThumbnailGrid


STATUS_LABELS: dict[str, str] = {
    "all": "Alle",
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


VIEW_LABELS: dict[str, str] = {
    "worklist": "Arbeitsliste",
    "saved": "Gespeichert",
    "rejected": "Aussortiert",
    "known": "Bekannte/importierte",
    "all": "Alle bekannten Posts",
}


class PreviewWindow(QMainWindow):
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.current_limit = 500
        self.current_offset = 0

        # Nur noch ein Viewer pro Post-ID.
        # Falls Qt Signale mehrfach feuert, wird kein Fensterzoo mehr gezüchtet.
        self.viewer_windows_by_post_id: dict[int, ImageViewerWindow] = {}

        self._applying_viewer_query = False
        self._pending_viewer_query: str | None = None
        self._is_reloading = False
        self._reload_pending = False

        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.setInterval(250)
        self.reload_timer.timeout.connect(self.reload_posts)

        gui_config = config.get("gui", {}) or {}

        self.setWindowTitle("Danbooru Manager - Preview")

        self.toolbar = QToolBar("Preview")
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.reload_button = QPushButton("Neu laden")
        self.reload_button.clicked.connect(self.reload_posts)
        self.toolbar.addWidget(self.reload_button)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Ansicht: "))
        self.view_mode = QComboBox()
        for view_mode, label in VIEW_LABELS.items():
            self.view_mode.addItem(label, view_mode)

        default_view = str((config.get("viewer", {}) or {}).get("default_view", "worklist"))
        index = self.view_mode.findData(default_view)
        if index >= 0:
            self.view_mode.setCurrentIndex(index)

        self.view_mode.currentIndexChanged.connect(self.schedule_reload)
        self.toolbar.addWidget(self.view_mode)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Status: "))
        self.status_filter = QComboBox()
        for status, label in STATUS_LABELS.items():
            self.status_filter.addItem(label, status)
        self.status_filter.currentIndexChanged.connect(self.schedule_reload)
        self.toolbar.addWidget(self.status_filter)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Suche: "))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("ID, Tag oder Pfad suchen...")
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

        # Wichtig:
        # Beim Tippen von "500" soll nicht erst 5, dann 50, dann 500 reloaden.
        # QSpinBox ist sonst ein kleiner Reload-Vulkan.
        self.limit_spin.setKeyboardTracking(False)
        self.limit_spin.valueChanged.connect(self.schedule_reload)
        self.limit_spin.editingFinished.connect(self.schedule_reload)

        self.toolbar.addWidget(self.limit_spin)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Thumbnail: "))
        self.thumbnail_size_spin = QSpinBox()
        self.thumbnail_size_spin.setRange(
            int(gui_config.get("thumbnail_size_min", 120)),
            int(gui_config.get("thumbnail_size_max", 600)),
        )
        self.thumbnail_size_spin.setSingleStep(int(gui_config.get("thumbnail_size_step", 20)))
        self.thumbnail_size_spin.setSuffix(" px")
        self.thumbnail_size_spin.setValue(int(gui_config.get("thumbnail_size", 280)))
        self.thumbnail_size_spin.setKeyboardTracking(False)
        self.thumbnail_size_spin.valueChanged.connect(self.on_thumbnail_size_changed)
        self.toolbar.addWidget(self.thumbnail_size_spin)

        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout(self.main_widget)

        self.info_label = QLabel("")
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.main_layout.addWidget(self.info_label)

        self.grid = ThumbnailGrid(self.db, self.config)
        self.grid.status_changed.connect(self.on_status_changed)
        self.grid.request_reload.connect(self.schedule_reload)
        self.grid.open_viewer_requested.connect(self.open_viewer)
        self.main_layout.addWidget(self.grid)

        self.setCentralWidget(self.main_widget)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.reload_posts()

    def schedule_reload(self, *_args) -> None:
        if self._applying_viewer_query:
            return

        # Wenn gerade ein Reload läuft, danach nochmal genau einmal nachziehen.
        if self._is_reloading:
            self._reload_pending = True
            return

        self.reload_timer.start()

    def selected_view_mode(self) -> str:
        return str(self.view_mode.currentData())

    def selected_status(self) -> str:
        return str(self.status_filter.currentData())

    def current_search_text(self) -> str | None:
        text = self.search_edit.text().strip()
        return text or None

    def worklist_statuses(self) -> list[str]:
        workflow = self.config.get("workflow", {}) or {}
        statuses = workflow.get("worklist_statuses", ["new", "potential", "review", "selected_save"])
        return [str(status) for status in statuses]

    def clear_search(self) -> None:
        self.search_edit.clear()
        self.reload_posts()

    def on_thumbnail_size_changed(self, size: int) -> None:
        self.grid.set_thumbnail_size(int(size))
        self.status_bar.showMessage(f"Thumbnail-Größe: {size}px")

    def reload_posts(self) -> None:
        if self._applying_viewer_query:
            return

        if self._is_reloading:
            self._reload_pending = True
            return

        self.reload_timer.stop()
        self._is_reloading = True

        try:
            view_mode = self.selected_view_mode()
            status = self.selected_status()
            text_filter = self.current_search_text()
            self.current_limit = int(self.limit_spin.value())

            total = self.db.count_preview_posts(
                view_mode=view_mode,
                status_filter=status,
                text_filter=text_filter,
                worklist_statuses=self.worklist_statuses(),
            )
            posts = self.db.fetch_preview_posts(
                view_mode=view_mode,
                status_filter=status,
                text_filter=text_filter,
                worklist_statuses=self.worklist_statuses(),
                limit=self.current_limit,
                offset=self.current_offset,
            )

            self.grid.set_posts(posts)

            status_note = ""
            if status != "all" and view_mode == "worklist":
                status_note = " | Statusfilter global"

            self.info_label.setText(
                f"Ansicht: {VIEW_LABELS.get(view_mode, view_mode)} | "
                f"Angezeigt: {len(posts)} / Treffer: {total} | "
                f"Statusfilter: {STATUS_LABELS.get(status, status)}{status_note} | "
                f"Thumbnail: {self.grid.thumbnail_size}px"
            )
            self.status_bar.showMessage("Preview geladen")

        finally:
            self._is_reloading = False

        if self._reload_pending:
            self._reload_pending = False
            self.schedule_reload()

    def on_status_changed(self, post_id: int, status: str) -> None:
        self.grid.update_card_status(post_id, status)
        self.status_bar.showMessage(f"Post {post_id} → {STATUS_LABELS.get(status, status)}")

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

            view_index = self.view_mode.findData("all")
            status_index = self.status_filter.findData("all")

            self.view_mode.blockSignals(True)
            self.status_filter.blockSignals(True)
            try:
                if view_index >= 0:
                    self.view_mode.setCurrentIndex(view_index)
                if status_index >= 0:
                    self.status_filter.setCurrentIndex(status_index)
            finally:
                self.view_mode.blockSignals(False)
                self.status_filter.blockSignals(False)

        finally:
            self._applying_viewer_query = False

        self.reload_posts()
        self.status_bar.showMessage(f"Query aus Viewer übernommen: {query}")

    def cleanup_viewers(self) -> None:
        # Kompatibilität für alte Aufrufer.
        self.viewer_windows_by_post_id = {
            post_id: viewer
            for post_id, viewer in self.viewer_windows_by_post_id.items()
            if viewer.isVisible()
        }
