from __future__ import annotations

import copy
import logging
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget

from app.core.database import Database
from app.gui.fetch_tab import FetchTab
from app.gui.icon_utils import ensure_app_icon
from app.i18n.i18n import tr


LOGGER = logging.getLogger(__name__)


class RejectedCachePurgeWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, database_file: Path, config: dict[str, Any]) -> None:
        super().__init__()
        self.database_file = Path(database_file)
        self.config = copy.deepcopy(config)

    @Slot()
    def run(self) -> None:
        worker_db: Database | None = None
        try:
            worker_db = Database(self.database_file)
            worker_db.connect()
            self.finished.emit(worker_db.purge_rejected_cache_files(self.config))
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            if worker_db is not None:
                try:
                    worker_db.close()
                except Exception:
                    pass


class AppWindow(QMainWindow):
    """Main window with lazy tab creation.

    Fetch and Preview are created during startup so existing/saved posts can
    be searched immediately without running a Fetch first. The heavier admin
    tabs are still built on first use, because constructors doing database
    workouts remain one of humanity's stranger little rituals.
    """

    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.debug_startup = bool(config.get("debug_startup"))

        self.fetch_tab: FetchTab | None = None
        self.preview_window: QWidget | None = None
        self.import_tab: QWidget | None = None
        self.tag_tab: QWidget | None = None
        self.category_tab: QWidget | None = None
        self.config_tab: QWidget | None = None
        self.maintenance_tab: QWidget | None = None
        self.help_tab: QWidget | None = None

        self._tab_widgets: dict[str, QWidget] = {}
        self._tab_indices: dict[str, int] = {}
        self._pending_preview_reload = False
        self._pending_fetch_running = False
        self._cache_purge_thread: QThread | None = None
        self._cache_purge_worker: RejectedCachePurgeWorker | None = None

        self.setWindowTitle(tr("app.title", config=self.config))
        self.setWindowIcon(ensure_app_icon(config))

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self._startup_log("AppWindow: begin")

        self._startup_log("FetchTab: begin")
        self.fetch_tab = FetchTab(config, db)
        self._startup_log("FetchTab: end")
        self.tabs.addTab(self.fetch_tab, self._tab_title("fetch"))
        self._tab_widgets["fetch"] = self.fetch_tab
        self._tab_indices["fetch"] = 0

        self._startup_log("PreviewTab: begin")
        self.preview_window = self._create_preview_tab()
        self._startup_log("PreviewTab: end")
        self.tabs.addTab(self.preview_window, self._tab_title("preview"))
        self._tab_widgets["preview"] = self.preview_window
        self._tab_indices["preview"] = 1

        self.fetch_tab.fetch_started.connect(self.on_fetch_started)
        self.fetch_tab.fetch_finished.connect(self.on_fetch_finished)
        self.fetch_tab.fetch_failed_signal.connect(self.on_fetch_failed)
        self.fetch_tab.open_preview_requested.connect(self.open_preview_tab)

        self._add_lazy_tab("import", self._tab_title("import"))
        self._add_lazy_tab("tags", self._tab_title("tags"))
        self._add_lazy_tab("categories", self._tab_title("categories"))
        self._add_lazy_tab("config", self._tab_title("config"))
        self._ensure_maintenance_tab_registered()
        self._add_lazy_tab("help", self._tab_title("help"))

        self._create_menu_bar()

        self.tabs.currentChanged.connect(self.on_tab_changed)
        QTimer.singleShot(1000, self.start_rejected_cache_purge)
        self._startup_log("AppWindow: shown-ready")


    def refresh_layout_after_show(self) -> None:
        """Recalculate nested tab layouts after the outer window has its final size."""
        central = self.centralWidget()
        if central is not None:
            central.updateGeometry()
            layout = central.layout()
            if layout is not None:
                layout.invalidate()
                layout.activate()

        current = self.tabs.currentWidget()
        if current is not None:
            current.updateGeometry()
            layout = current.layout()
            if layout is not None:
                layout.invalidate()
                layout.activate()

            refresh = getattr(current, "refresh_host_layout", None)
            if callable(refresh):
                refresh()

        self.tabs.updateGeometry()
        self.tabs.update()
        self.updateGeometry()
        self.update()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        QTimer.singleShot(0, self.refresh_layout_after_show)
        QTimer.singleShot(150, self.refresh_layout_after_show)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        thread = self._cache_purge_thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(3000)
        super().closeEvent(event)

    def start_rejected_cache_purge(self) -> None:
        if self._cache_purge_thread is not None:
            return

        database_file = Path(str(self.config["database_file"]))
        self._cache_purge_thread = QThread(self)
        self._cache_purge_worker = RejectedCachePurgeWorker(database_file, self.config)
        self._cache_purge_worker.moveToThread(self._cache_purge_thread)

        self._cache_purge_thread.started.connect(self._cache_purge_worker.run)
        self._cache_purge_worker.finished.connect(self.on_rejected_cache_purge_finished)
        self._cache_purge_worker.failed.connect(self.on_rejected_cache_purge_failed)
        self._cache_purge_worker.finished.connect(self._cache_purge_thread.quit)
        self._cache_purge_worker.failed.connect(self._cache_purge_thread.quit)
        self._cache_purge_worker.finished.connect(self._cache_purge_worker.deleteLater)
        self._cache_purge_worker.failed.connect(self._cache_purge_worker.deleteLater)
        self._cache_purge_thread.finished.connect(self._cache_purge_thread.deleteLater)
        self._cache_purge_thread.finished.connect(self._clear_rejected_cache_purge_worker)
        self._cache_purge_thread.start()

    @Slot(object)
    def on_rejected_cache_purge_finished(self, result: object) -> None:
        purge_result = dict(result) if isinstance(result, dict) else {}
        deleted_files = int(purge_result.get("deleted_files", 0) or 0)
        cleared_rows = int(purge_result.get("cleared_rows", 0) or 0)
        retention_days = int(purge_result.get("retention_days", 0) or 0)
        if deleted_files:
            LOGGER.info(
                "Purged rejected cache files: deleted=%s, posts=%s, retention_days=%s",
                deleted_files,
                cleared_rows,
                retention_days,
            )

    @Slot(str)
    def on_rejected_cache_purge_failed(self, error: str) -> None:
        LOGGER.error("Rejected cache purge failed:\n%s", error)

    @Slot()
    def _clear_rejected_cache_purge_worker(self) -> None:
        self._cache_purge_thread = None
        self._cache_purge_worker = None

    def _create_menu_bar(self) -> None:
        # The former top-level Help menu was intentionally removed. Help,
        # About and Update now live in the dedicated Help tab. One place for
        # support content, because scattering UI entry points around like
        # confetti is how software turns into archaeology.
        self.menuBar().clear()

    def _tab_title(self, key: str) -> str:
        # Internal tab ids are not always identical to translation ids.
        # Keep the legacy internal key "import" stable, but translate it as
        # "importer" so the visible tab title never falls back to a raw key.
        translation_key = {
            "import": "importer",
        }.get(key, key)
        return tr(f"tabs.{translation_key}", config=self.config)

    def _startup_log(self, message: str) -> None:
        if not self.debug_startup:
            return
        print(f"[STARTUP {time.perf_counter():.3f}] {message}", flush=True)

    def _make_placeholder(self, title: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        label = QLabel(tr("lazy.not_loaded", config=self.config, title=title))
        label.setObjectName("lazyTabPlaceholderLabel")
        label.setWordWrap(True)
        label.setStyleSheet("color: #9aa0a6; font-size: 14px;")
        layout.addWidget(label)
        layout.addStretch(1)
        return widget

    def _set_lazy_tab_loading_message(self, key: str, title: str) -> None:
        placeholder = self._tab_widgets.get(key)
        if placeholder is None:
            return

        label = placeholder.findChild(QLabel, "lazyTabPlaceholderLabel")
        if label is None:
            return

        label.setText(tr("lazy.loading", config=self.config, title=title))
        label.setStyleSheet(
            "color: #ffd166; font-size: 15px; font-weight: bold;"
        )
        self.statusBar().showMessage(tr("lazy.loading", config=self.config, title=title))
        placeholder.update()
        self.tabs.update()
        QApplication.processEvents()

    def _add_lazy_tab(self, key: str, title: str) -> None:
        if key in self._tab_widgets:
            return
        placeholder = self._make_placeholder(title)
        index = self.tabs.addTab(placeholder, title)
        self._tab_widgets[key] = placeholder
        self._tab_indices[key] = index

    def _ensure_maintenance_tab_registered(self) -> None:
        """Add the maintenance tab if an older patched window missed it."""
        if "maintenance" in self._tab_widgets:
            return
        self._add_lazy_tab("maintenance", self._tab_title("maintenance"))

    def _ensure_tab(self, key: str) -> QWidget:
        existing = self._tab_widgets.get(key)
        if existing is not None and not self._is_placeholder(key, existing):
            return existing

        factories: dict[str, Callable[[], QWidget]] = {
            "preview": self._create_preview_tab,
            "import": self._create_import_tab,
            "tags": self._create_tag_tab,
            "categories": self._create_category_tab,
            "config": self._create_config_tab,
            "maintenance": self._create_maintenance_tab,
            "help": self._create_help_tab,
        }
        factory = factories.get(key)
        if factory is None:
            raise KeyError(tr("error.unknown_tab", config=self.config, key=key))

        index = self._tab_indices[key]
        title = self.tabs.tabText(index)
        self._set_lazy_tab_loading_message(key, title)
        self._startup_log(f"Lazy tab create: {key} begin")
        widget = factory()
        self._startup_log(f"Lazy tab create: {key} end")

        old_widget = self.tabs.widget(index)
        signals_blocked = self.tabs.blockSignals(True)
        try:
            self.tabs.removeTab(index)
            old_widget.deleteLater()
            self.tabs.insertTab(index, widget, title)
            self.tabs.setCurrentIndex(index)
        finally:
            self.tabs.blockSignals(signals_blocked)
        self._tab_widgets[key] = widget
        self._rebuild_tab_indices()
        self.statusBar().showMessage(tr("lazy.loaded", config=self.config, title=title), 3000)
        return widget

    def _is_placeholder(self, key: str, widget: QWidget) -> bool:
        if key == "fetch":
            return False
        return (
            (key == "preview" and self.preview_window is None)
            or (key == "import" and self.import_tab is None)
            or (key == "tags" and self.tag_tab is None)
            or (key == "categories" and self.category_tab is None)
            or (key == "config" and self.config_tab is None)
            or (key == "maintenance" and self.maintenance_tab is None)
            or (key == "help" and self.help_tab is None)
        )

    def _rebuild_tab_indices(self) -> None:
        self._ensure_maintenance_tab_registered()
        for key, widget in list(self._tab_widgets.items()):
            index = self.tabs.indexOf(widget)
            if index >= 0:
                self._tab_indices[key] = index

    def _create_preview_tab(self) -> QWidget:
        from app.gui.preview_window import PreviewWindow

        widget = PreviewWindow(self.config, self.db)
        self.preview_window = widget
        if self._pending_fetch_running:
            widget.set_fetch_running(True)
        if self._pending_preview_reload:
            self._pending_preview_reload = False
            widget.schedule_reload()
        return widget

    def _create_import_tab(self) -> QWidget:
        from app.gui.import_tab import ImportTab

        widget = ImportTab(self.config, self.db)
        widget.import_finished.connect(self.on_import_finished)
        self.import_tab = widget
        return widget

    def _create_tag_tab(self) -> QWidget:
        from app.gui.tag_tab import TagTab

        widget = TagTab(self.config, self.db)
        self.tag_tab = widget
        return widget

    def _create_category_tab(self) -> QWidget:
        from app.gui.category_tab import CategoryTab

        widget = CategoryTab(self.config, self.db)
        self.category_tab = widget
        return widget

    def _create_config_tab(self) -> QWidget:
        from app.gui.config_tab import ConfigTab

        widget = ConfigTab(self.config, self.db)
        widget.config_changed.connect(self.on_config_changed)
        self.config_tab = widget
        return widget

    def _create_maintenance_tab(self) -> QWidget:
        from app.gui.maintenance_tab import MaintenanceTab

        widget = MaintenanceTab(self.config, self.db)
        self.maintenance_tab = widget
        return widget

    def _create_help_tab(self) -> QWidget:
        from app.gui.help_tab import HelpTab

        widget = HelpTab(self.config)
        self.help_tab = widget
        return widget

    def on_tab_changed(self, index: int) -> None:
        self._rebuild_tab_indices()
        for key, tab_index in list(self._tab_indices.items()):
            if tab_index != index or key == "fetch":
                continue
            widget = self._ensure_tab(key)
            self.tabs.setCurrentIndex(index)
            if key == "preview":
                widget.on_tab_activated()
            QTimer.singleShot(0, self.refresh_layout_after_show)
            return

    def on_fetch_started(self) -> None:
        self._pending_fetch_running = True
        if self.preview_window is not None:
            self.preview_window.set_fetch_running(True)
        index = self._tab_indices.get("preview", -1)
        if index >= 0:
            self.tabs.setTabText(index, self._tab_title("preview_fetch_running"))

    def on_fetch_finished(self) -> None:
        self._pending_fetch_running = False
        index = self._tab_indices.get("preview", -1)
        if index >= 0:
            self.tabs.setTabText(index, self._tab_title("preview"))
        if self.preview_window is not None:
            self.preview_window.set_fetch_running(False)
            self.preview_window.schedule_reload()
        else:
            self._pending_preview_reload = True

    def on_fetch_failed(self) -> None:
        self._pending_fetch_running = False
        if self.preview_window is not None:
            self.preview_window.set_fetch_running(False)
        index = self._tab_indices.get("preview", -1)
        if index >= 0:
            self.tabs.setTabText(index, self._tab_title("preview"))

    def open_preview_tab(self) -> None:
        self._ensure_tab("preview")
        index = self._tab_indices.get("preview", -1)
        if index >= 0:
            self.tabs.setCurrentIndex(index)

    def on_import_finished(self) -> None:
        if self.preview_window is not None:
            self.preview_window.schedule_reload()
        else:
            self._pending_preview_reload = True

    def on_config_changed(self) -> None:
        # Active widgets keep a reference to the same config dict. Do not
        # trigger Preview database work while Fetch is still writing. Some
        # Preview refresh paths can perform maintenance/recommendation updates,
        # and running those synchronously from the Qt main thread can otherwise
        # contend with the Fetch writer and stall the write queue.
        if self._pending_fetch_running:
            self._pending_preview_reload = True
            return

        if self.preview_window is not None:
            self.preview_window.reload_category_filter()
            self.preview_window.schedule_reload()
        else:
            self._pending_preview_reload = True
