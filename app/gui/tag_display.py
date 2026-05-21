from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

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
    def __init__(self) -> None:
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)
        self.lists: dict[str, QListWidget] = {}

        for tag_type in ("artist", "character", "copyright", "general", "meta"):
            label = QLabel(TAG_TYPE_LABELS[tag_type])
            label.setStyleSheet(f"QLabel {{ color: {TAG_TYPE_COLORS[tag_type]}; font-weight: bold; }}")
            self.layout.addWidget(label)
            list_widget = QListWidget()
            list_widget.setSelectionMode(QListWidget.ExtendedSelection)
            list_widget.setMaximumHeight(95 if tag_type != "general" else 170)
            list_widget.setStyleSheet(
                f"""
                QListWidget {{
                    border: 1px solid {TAG_TYPE_COLORS[tag_type]};
                    border-radius: 4px;
                    background: #1f1f1f;
                    color: #eeeeee;
                }}
                QListWidget::item:selected {{
                    background: {TAG_TYPE_COLORS[tag_type]};
                    color: #000000;
                }}
                """
            )
            self.lists[tag_type] = list_widget
            self.layout.addWidget(list_widget)

    def set_typed_tags(self, typed_tags: dict[str, list[str]]) -> None:
        for tag_type, list_widget in self.lists.items():
            list_widget.clear()
            for tag in typed_tags.get(tag_type, []):
                item = QListWidgetItem(tag)
                item.setData(Qt.UserRole, tag)
                item.setData(Qt.UserRole + 1, tag_type)
                item.setForeground(QColor(TAG_TYPE_COLORS[tag_type]))
                list_widget.addItem(item)

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
