from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMainWindow, QTabWidget

from app.core.database import Database
from app.gui.category_tab import CategoryTab
from app.gui.config_tab import ConfigTab
from app.gui.fetch_tab import FetchTab
from app.gui.icon_utils import ensure_app_icon
from app.gui.preview_window import PreviewWindow
from app.gui.tag_tab import TagTab


class AppWindow(QMainWindow):
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db

        self.setWindowTitle("Danbooru Manager")
        self.setWindowIcon(ensure_app_icon(config))

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.fetch_tab = FetchTab(config, db)
        self.preview_window = PreviewWindow(config, db)
        self.tag_tab = TagTab(config, db)
        self.category_tab = CategoryTab(config, db)
        self.config_tab = ConfigTab(config, db)

        self.tabs.addTab(self.fetch_tab, "Fetch / Suche")
        self.tabs.addTab(self.preview_window, "Preview / Review")
        self.tabs.addTab(self.tag_tab, "Tags")
        self.tabs.addTab(self.category_tab, "Kategorien")
        self.tabs.addTab(self.config_tab, "Konfiguration")

        self.fetch_tab.fetch_finished.connect(self.on_fetch_finished)
        self.fetch_tab.open_preview_requested.connect(self.open_preview_tab)
        self.config_tab.config_changed.connect(self.on_config_changed)
        self.tabs.currentChanged.connect(self.on_tab_changed)

    def on_tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is self.preview_window:
            self.preview_window.on_tab_activated()

    def on_fetch_finished(self) -> None:
        self.preview_window.schedule_reload()

    def open_preview_tab(self) -> None:
        index = self.tabs.indexOf(self.preview_window)
        if index >= 0:
            self.tabs.setCurrentIndex(index)

    def on_config_changed(self) -> None:
        # Laufende Widgets haben Referenz auf dasselbe config-dict.
        # Nach Config-Änderungen reicht für jetzt ein Preview-Reload.
        self.preview_window.reload_category_filter()
        self.preview_window.schedule_reload()
