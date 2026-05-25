from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.gui.update_tab import UpdateTab
from app.version import APP_NAME, GITHUB_REPOSITORY, __version__


class HelpTab(QWidget):
    """Main Help area with sub-pages for About, Updates and future guides."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        self.config = config

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("Help")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        root.addWidget(title)

        intro = QLabel(
            "This section collects application information, portable updates and future built-in help. "
            "More help pages such as How-to guides and workflow notes will follow in later versions."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #c7c7c7;")
        root.addWidget(intro)

        self.sub_tabs = QTabWidget()
        self.sub_tabs.addTab(self._create_about_page(), "About")
        self.sub_tabs.addTab(UpdateTab(config), "Update")
        self.sub_tabs.addTab(self._create_how_to_placeholder(), "How to")
        root.addWidget(self.sub_tabs, 1)

    def _create_about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        heading = QLabel(f"{APP_NAME}")
        heading.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(heading)

        version = QLabel(f"Version: {__version__}")
        version.setStyleSheet("font-weight: bold;")
        layout.addWidget(version)

        text = QLabel(
            "Danbooru Download Manager is a local workflow tool for managing Danbooru downloads, "
            "previewing posts, reviewing metadata, assigning ratings, sorting into categories and "
            "keeping local post data searchable by tags, post ID and original source link."
        )
        text.setWordWrap(True)
        layout.addWidget(text)

        repo_box = QFrame()
        repo_box.setFrameShape(QFrame.Shape.StyledPanel)
        repo_box.setStyleSheet(
            "QFrame { border: 1px solid #555; border-radius: 8px; padding: 10px; }"
        )
        repo_layout = QVBoxLayout(repo_box)

        repo_title = QLabel("Project repository")
        repo_title.setStyleSheet("font-weight: bold;")
        repo_layout.addWidget(repo_title)

        repo = QLabel(f"GitHub: {GITHUB_REPOSITORY}")
        repo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        repo_layout.addWidget(repo)

        layout.addWidget(repo_box)

        note = QLabel(
            "Built-in documentation is still being expanded. For now, the README and /docs directory "
            "contain the more detailed setup, configuration and workflow notes. Yes, documentation is "
            "also a feature, apparently one that has to be wrestled into existence."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #9aa0a6;")
        layout.addWidget(note)

        layout.addStretch(1)
        return page

    def _create_how_to_placeholder(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        heading = QLabel("How to")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(heading)

        text = QLabel(
            "More built-in guides will follow here in a future version, including first-time setup, "
            "configuration, fetching posts, preview review and category workflows. Until then, use the "
            "README and /docs files. Primitive, but effective."
        )
        text.setWordWrap(True)
        layout.addWidget(text)

        layout.addStretch(1)
        return page
