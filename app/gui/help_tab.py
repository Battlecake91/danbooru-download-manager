from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
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
            "This section collects the practical workflow notes: setup, fetch, preview review, "
            "tag scoring, troubleshooting and portable updates."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #c7c7c7;")
        root.addWidget(intro)

        self.sub_tabs = QTabWidget()
        self.sub_tabs.addTab(self._create_about_page(), "About")
        self.sub_tabs.addTab(self._create_quick_start_page(), "Quick start")
        self.sub_tabs.addTab(self._create_fetch_page(), "Fetch")
        self.sub_tabs.addTab(self._create_preview_page(), "Preview & Viewer")
        self.sub_tabs.addTab(self._create_tags_page(), "Tags & Scoring")
        self.sub_tabs.addTab(self._create_builds_page(), "Builds & Tests")
        self.sub_tabs.addTab(UpdateTab(config), "Update")
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
            "The README and /docs directory still contain deeper notes. This Help tab is the fast path "
            "for the things you usually need while working in the app."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #9aa0a6;")
        layout.addWidget(note)

        layout.addStretch(1)
        return page

    def _create_guide_page(self, sections: list[tuple[str, list[str]]]) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        for title, lines in sections:
            layout.addWidget(self._make_section(title, lines))

        layout.addStretch(1)
        scroll.setWidget(page)
        return scroll

    def _make_section(self, title: str, lines: list[str]) -> QFrame:
        box = QFrame()
        box.setFrameShape(QFrame.Shape.StyledPanel)
        box.setStyleSheet("QFrame { border: 1px solid #555; border-radius: 6px; padding: 10px; }")
        layout = QVBoxLayout(box)

        heading = QLabel(title)
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)

        text = QLabel("\n".join(f"- {line}" for line in lines))
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(text)
        return box

    def _create_quick_start_page(self) -> QWidget:
        return self._create_guide_page(
            [
                (
                    "First run",
                    [
                        "Set work_dir, database_file and output folders in Config.",
                        "Optional but recommended: enter Danbooru username and API key for higher API limits and saved searches.",
                        "Use Maintenance after large imports or if the database feels slower than usual.",
                    ],
                ),
                (
                    "Normal workflow",
                    [
                        "Fetch creates or refreshes local post records and thumbnails.",
                        "Preview is the review surface: filter, search, save, reject and open the Viewer.",
                        "Viewer is for one-post decisions, ratings, categories, parent/child context and filename preview.",
                    ],
                ),
                (
                    "Where settings live",
                    [
                        "Config saves settings into the local SQLite database.",
                        "Raw app_settings is diagnostic only; prefer the dedicated fields unless you are debugging.",
                    ],
                ),
            ]
        )

    def _create_fetch_page(self) -> QWidget:
        return self._create_guide_page(
            [
                (
                    "Manual tag fetch",
                    [
                        "Enter Danbooru tags exactly as you would search them on the site.",
                        "Rating buttons are tri-state: ignore, include, exclude.",
                        "Resolution filters live behind Advanced Filter so the Fetch tab stays scannable.",
                    ],
                ),
                (
                    "Saved searches",
                    [
                        "Saved Searches need Danbooru credentials with permission to read saved searches.",
                        "Label and query filters narrow which saved searches are used.",
                        "Extra tags are appended to every selected saved search query.",
                    ],
                ),
                (
                    "Fetch exclude",
                    [
                        "Activate Tag-exclude skips posts with locally excluded tags during Fetch.",
                        "Excluded Tags opens the editable list used by Fetch.",
                        "Count excluded posts toward limits controls whether skipped posts consume per-query and total fetch limits.",
                    ],
                ),
            ]
        )

    def _create_preview_page(self) -> QWidget:
        return self._create_guide_page(
            [
                (
                    "Filtering",
                    [
                        "View chooses the broad result set; status checkboxes then narrow it further.",
                        "Search supports exact tags and exclusions, for example brown_eyes -red_hair.",
                        "Preselection filters by local tag-score recommendation when its checkbox is active.",
                    ],
                ),
                (
                    "Review actions",
                    [
                        "Save writes final files using the configured filename pattern.",
                        "Reject keeps a rejected thumbnail for a limited time so decisions remain auditable.",
                        "Reload Thumbnail helps when a thumbnail was missing, stale or gray.",
                    ],
                ),
                (
                    "Viewer strip",
                    [
                        "The strip below the image shows previous/current/next posts from the current Viewer list.",
                        "The active post stays centered; previous/next counts and thumbnail size are configurable.",
                    ],
                ),
            ]
        )

    def _create_tags_page(self) -> QWidget:
        return self._create_guide_page(
            [
                (
                    "Tag tab",
                    [
                        "Saved, Rejected and Rejected % summarize how a tag behaved in reviewed posts.",
                        "Scoring-excluded tags intentionally show no Rejected % because they should not influence this score.",
                        "Alias and Manual score cells can be edited directly; option columns can be clicked to toggle.",
                    ],
                ),
                (
                    "Scoring and privacy flags",
                    [
                        "Category hint ignored removes a tag from category influence.",
                        "Preselection ignored removes a tag from recommendation scoring.",
                        "LLM ignored prevents a tag from being sent as LLM input.",
                    ],
                ),
                (
                    "Categories",
                    [
                        "Category order decides the winner when multiple categories match.",
                        "Include rules are alternatives; inside one rule, all positive tags must match.",
                        "Tags prefixed with '-' block that rule; global conditions apply to every include rule.",
                    ],
                ),
            ]
        )

    def _create_builds_page(self) -> QWidget:
        return self._create_guide_page(
            [
                (
                    "Automatic checks",
                    [
                        "GitHub Actions run tests and build checks on pushed changes.",
                        "scripts/pre_push_check.py runs whitespace checks, compileall and pytest locally.",
                        "Database performance tests guard the preview and tag-statistics queries.",
                    ],
                ),
                (
                    "Portable builds",
                    [
                        "The portable app bundles application code into the executable.",
                        "Database, thumbnails, cache, logs and saved files stay outside the executable by design.",
                        "Linux and Windows build routes are handled through the CI workflows.",
                    ],
                ),
            ]
        )
