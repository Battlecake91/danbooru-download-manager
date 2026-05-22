from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QGridLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

TAG_TYPE_LABELS = {
    "artist": "Artist",
    "character": "Character",
    "copyright": "Serie / Copyright",
    "meta": "Meta",
    "general": "General",
}

TAG_TYPE_COLORS = {
    "artist": "#ff9f1c",
    "character": "#2ec4b6",
    "copyright": "#e71d36",
    "meta": "#9b5de5",
    "general": "#dddddd",
}


class ToggleSelectListWidget(QListWidget):
    """QListWidget variant where a plain second click deselects a selected tag."""

    def mousePressEvent(self, event):  # noqa: ANN001
        item = self.itemAt(event.position().toPoint())
        plain_left_click = event.button() == Qt.LeftButton and event.modifiers() == Qt.NoModifier

        if plain_left_click and item is not None and item.isSelected():
            item.setSelected(False)
            event.accept()
            return

        super().mousePressEvent(event)


def typed_tags_for_post(db, post_id: int) -> dict[str, list[str]]:  # noqa: ANN001
    rows = db.execute(
        """
        SELECT tag, tag_type
        FROM post_tags
        WHERE post_id = ?
        ORDER BY
            CASE tag_type
                WHEN 'artist' THEN 1
                WHEN 'character' THEN 2
                WHEN 'copyright' THEN 3
                WHEN 'meta' THEN 4
                WHEN 'general' THEN 5
                ELSE 9
            END,
            tag ASC
        """,
        (post_id,),
    ).fetchall()

    result = {"artist": [], "character": [], "copyright": [], "meta": [], "general": []}
    for row in rows:
        tag_type = str(row["tag_type"] or "general")
        tag = str(row["tag"] or "").strip()
        if not tag:
            continue
        if tag_type not in result:
            tag_type = "general"
        result[tag_type].append(tag)
    return result


def parse_typed_tag_fields(row_or_dict: Any) -> dict[str, list[str]]:
    def value(key: str) -> str:
        try:
            return str(row_or_dict[key] or "")
        except Exception:
            if isinstance(row_or_dict, dict):
                return str(row_or_dict.get(key, "") or "")
            return ""

    return {
        "artist": value("tags_artist").split(),
        "character": value("tags_character").split(),
        "copyright": value("tags_copyright").split(),
        "meta": value("tags_meta").split(),
        "general": value("tags_general").split(),
    }


def compact_typed_tags_text(typed_tags: dict[str, list[str]], general_limit: int = 14) -> str:
    lines: list[str] = []
    for tag_type in ("artist", "character", "copyright", "general", "meta"):
        tags = typed_tags.get(tag_type, [])
        if not tags:
            continue
        shown = tags
        suffix = ""
        if tag_type == "general" and len(tags) > general_limit:
            shown = tags[:general_limit]
            suffix = f" ... (+{len(tags) - general_limit})"
        lines.append(f"{TAG_TYPE_LABELS[tag_type]}: {' '.join(shown)}{suffix}")
    return "\n".join(lines) if lines else "Tags: -"


class TypedTagListWidget(QWidget):
    """Compact tag view for the image viewer.

    Artist, copyright and character are shown next to each other because they are
    the important identity tags. General/meta stay below. The general list can be
    filtered to show only tags which are still allowed for filename generation.
    """

    def __init__(self) -> None:
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)
        self.lists: dict[str, QListWidget] = {}
        self._typed_tags: dict[str, list[str]] = {"artist": [], "character": [], "copyright": [], "meta": [], "general": []}
        self._filename_excluded_tags: set[str] = set()

        top_grid = QGridLayout()
        top_grid.setContentsMargins(0, 0, 0, 0)
        top_grid.setHorizontalSpacing(4)
        top_grid.setVerticalSpacing(2)
        self.layout.addLayout(top_grid)

        for column, tag_type in enumerate(("artist", "copyright", "character")):
            label = QLabel(TAG_TYPE_LABELS[tag_type])
            label.setStyleSheet(f"QLabel {{ color: {TAG_TYPE_COLORS[tag_type]}; font-weight: bold; }}")
            top_grid.addWidget(label, 0, column)

            list_widget = self._create_list(tag_type)
            self.lists[tag_type] = list_widget
            top_grid.addWidget(list_widget, 1, column)
            top_grid.setColumnStretch(column, 1)

        self.general_filter_checkbox = QCheckBox("General: nur nicht ausgeschlossene Filename-Tags anzeigen")
        self.general_filter_checkbox.setToolTip(
            "Blendet General-Tags aus, die bereits im Filename-Exclude stehen. Praktisch zum Aussortieren, leider."
        )
        self.general_filter_checkbox.toggled.connect(self._refresh_general_list)
        self.layout.addWidget(self.general_filter_checkbox)

        for tag_type in ("general", "meta"):
            label = QLabel(TAG_TYPE_LABELS[tag_type])
            label.setStyleSheet(f"QLabel {{ color: {TAG_TYPE_COLORS[tag_type]}; font-weight: bold; }}")
            self.layout.addWidget(label)
            list_widget = self._create_list(tag_type)
            self.lists[tag_type] = list_widget
            self.layout.addWidget(list_widget)

    def _create_list(self, tag_type: str) -> QListWidget:
        list_widget = ToggleSelectListWidget()
        list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        list_widget.setUniformItemSizes(True)
        list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_widget.setMaximumHeight(90)
        list_widget.setStyleSheet(
            f"""
            QListWidget {{
                border: 1px solid {TAG_TYPE_COLORS[tag_type]};
                border-radius: 4px;
                background: #1f1f1f;
                color: #eeeeee;
            }}
            QListWidget::item {{ padding: 1px 4px; }}
            QListWidget::item:selected {{
                background: {TAG_TYPE_COLORS[tag_type]};
                color: #000000;
            }}
            """
        )
        return list_widget

    def set_typed_tags(self, typed_tags: dict[str, list[str]], filename_excluded_tags: set[str] | None = None) -> None:
        self._typed_tags = {
            "artist": list(typed_tags.get("artist", [])),
            "character": list(typed_tags.get("character", [])),
            "copyright": list(typed_tags.get("copyright", [])),
            "meta": list(typed_tags.get("meta", [])),
            "general": list(typed_tags.get("general", [])),
        }
        self._filename_excluded_tags = set(filename_excluded_tags or set())

        for tag_type in ("artist", "copyright", "character", "meta"):
            self._fill_list(tag_type, self._typed_tags.get(tag_type, []))
        self._refresh_general_list()
        self._autosize_lists()

    def _refresh_general_list(self) -> None:
        tags = self._typed_tags.get("general", [])
        if self.general_filter_checkbox.isChecked():
            tags = [tag for tag in tags if tag not in self._filename_excluded_tags]
        self._fill_list("general", tags)
        self._autosize_lists()

    def _fill_list(self, tag_type: str, tags: list[str]) -> None:
        list_widget = self.lists[tag_type]
        list_widget.clear()
        for tag in tags:
            item = QListWidgetItem(tag)
            item.setData(Qt.UserRole, tag)
            item.setData(Qt.UserRole + 1, tag_type)
            item.setForeground(QColor(TAG_TYPE_COLORS[tag_type]))
            list_widget.addItem(item)

    def _autosize_lists(self) -> None:
        for tag_type, list_widget in self.lists.items():
            rows = max(1, min(8 if tag_type in {"general", "meta"} else 5, list_widget.count()))
            row_height = max(20, list_widget.sizeHintForRow(0) if list_widget.count() else 20)
            header_padding = 10
            list_widget.setMaximumHeight(rows * row_height + header_padding)
            list_widget.setMinimumHeight(min(rows, 2) * row_height + header_padding)

    def selected_tags(self) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for list_widget in self.lists.values():
            for item in list_widget.selectedItems():
                tag = str(item.data(Qt.UserRole) or item.text())
                if tag and tag not in seen:
                    result.append(tag)
                    seen.add(tag)
        return result
