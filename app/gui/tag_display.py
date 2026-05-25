from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QSizePolicy, QVBoxLayout, QWidget

from app.i18n.i18n import tr

TAG_TYPE_LABELS = {
    "artist": "Artist",
    "character": "Character",
    "copyright": "Series / Copyright",
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
    the important identity tags. General/meta stay below. The optional filename
    filter applies to all tag groups, not only General.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(3)
        self.lists: dict[str, QListWidget] = {}
        self.group_widgets: dict[str, QWidget] = {}
        self._typed_tags: dict[str, list[str]] = {"artist": [], "character": [], "copyright": [], "meta": [], "general": []}
        self._filename_excluded_tags: set[str] = set()
        self._tag_metadata: dict[str, dict[str, Any]] = {}

        self.identity_group = QWidget()
        self.identity_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.identity_grid = QGridLayout(self.identity_group)
        self.identity_grid.setContentsMargins(0, 0, 0, 0)
        self.identity_grid.setHorizontalSpacing(6)
        self.identity_grid.setVerticalSpacing(2)
        self.layout.addWidget(self.identity_group)

        for column, tag_type in enumerate(("artist", "copyright", "character")):
            label = self._create_group_label(tag_type)
            list_widget = self._create_list(tag_type)
            self.lists[tag_type] = list_widget
            self.identity_grid.addWidget(label, 0, column)
            self.identity_grid.addWidget(list_widget, 1, column)
            self.identity_grid.setColumnStretch(column, 2 if tag_type == "character" else 1)
        self.identity_grid.setRowStretch(0, 0)
        self.identity_grid.setRowStretch(1, 0)

        general_group = self._create_tag_group("general", expanding=True)
        self.layout.addWidget(general_group, stretch=1)

        meta_group = self._create_tag_group("meta", expanding=False)
        self.layout.addWidget(meta_group)

        self.filename_filter_checkbox = QCheckBox(
            tr("viewer.show_only_filename_allowed_tags", "Show only tags not excluded from filenames")
        )
        self.filename_filter_checkbox.setToolTip(
            tr(
                "viewer.show_only_filename_allowed_tags_tooltip",
                "Hides tags that are already listed as filename excludes.",
            )
        )
        self.filename_filter_checkbox.toggled.connect(self._refresh_all_lists)
        self.layout.addWidget(self.filename_filter_checkbox)

    def _create_group_label(self, tag_type: str) -> QLabel:
        label = QLabel(TAG_TYPE_LABELS[tag_type])
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        label.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        label.setStyleSheet(
            f"QLabel {{ color: {TAG_TYPE_COLORS[tag_type]}; font-weight: bold; margin: 0px; padding: 0px; }}"
        )
        return label

    def _create_tag_group(self, tag_type: str, expanding: bool = False) -> QWidget:
        group = QWidget()
        group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding if expanding else QSizePolicy.Fixed)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(2)

        label = self._create_group_label(tag_type)
        group_layout.addWidget(label)

        list_widget = self._create_list(tag_type)
        if expanding:
            list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lists[tag_type] = list_widget
        group_layout.addWidget(list_widget, stretch=1 if expanding else 0)
        self.group_widgets[tag_type] = group
        return group

    def _create_list(self, tag_type: str) -> QListWidget:
        list_widget = ToggleSelectListWidget()
        list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        list_widget.itemSelectionChanged.connect(self._sync_detail_row_selection_colors)
        list_widget.setUniformItemSizes(True)
        list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        list_widget.setMaximumHeight(54)
        list_widget.setStyleSheet(
            f"""
            QListWidget {{
                border: 1px solid {TAG_TYPE_COLORS[tag_type]};
                border-radius: 4px;
                background: #1f1f1f;
                color: #eeeeee;
            }}
            QListWidget::item {{ padding: 1px 4px; font-weight: normal; }}
            QListWidget::item:selected {{
                background: {TAG_TYPE_COLORS[tag_type]};
                color: #000000;
            }}
            """
        )
        return list_widget


    def show_loading_message(self, message: str | None = None) -> None:
        if message is None:
            message = tr("viewer.tags_loading", "Loading tags…")
        self.setUpdatesEnabled(False)
        try:
            for tag_type, list_widget in self.lists.items():
                list_widget.clear()
                if tag_type == "general":
                    item = QListWidgetItem(message)
                    item.setFlags(Qt.NoItemFlags)
                    item.setForeground(QColor("#ffd166"))
                    list_widget.addItem(item)
            self._autosize_lists()
        finally:
            self.setUpdatesEnabled(True)
        self.update()

    def set_typed_tags(
        self,
        typed_tags: dict[str, list[str]],
        filename_excluded_tags: set[str] | None = None,
        tag_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._typed_tags = {
            "artist": list(typed_tags.get("artist", [])),
            "character": list(typed_tags.get("character", [])),
            "copyright": list(typed_tags.get("copyright", [])),
            "meta": list(typed_tags.get("meta", [])),
            "general": list(typed_tags.get("general", [])),
        }
        self._filename_excluded_tags = set(filename_excluded_tags or set())
        self._tag_metadata = dict(tag_metadata or {})
        self._refresh_all_lists()

    def _visible_tags_for_type(self, tag_type: str) -> list[str]:
        tags = self._typed_tags.get(tag_type, [])
        if self.filename_filter_checkbox.isChecked():
            return [tag for tag in tags if tag not in self._filename_excluded_tags]
        return tags

    def _refresh_all_lists(self) -> None:
        # Building General/Meta rows can create many small QLabel/QWidget objects.
        # Freeze repainting while the lists are rebuilt; otherwise Qt gleefully
        # repaints intermediate states like it is paid by the frame.
        self.setUpdatesEnabled(False)
        try:
            for list_widget in self.lists.values():
                list_widget.setUpdatesEnabled(False)
            for tag_type in ("artist", "copyright", "character", "general", "meta"):
                self._fill_list(tag_type, self._visible_tags_for_type(tag_type))
            self._autosize_lists()
            self._sync_detail_row_selection_colors()
        finally:
            for list_widget in self.lists.values():
                list_widget.setUpdatesEnabled(True)
            self.setUpdatesEnabled(True)

    def _fill_list(self, tag_type: str, tags: list[str]) -> None:
        list_widget = self.lists[tag_type]
        list_widget.clear()
        for tag in tags:
            display_text = tag
            tooltip = tag

            # Artist / Series / Character intentionally stay compact. Extra
            # metadata clutter would break the layout we just barely tamed.
            # General and Meta can carry the details.
            meta_item_widget = None
            if tag_type in {"general", "meta"}:
                meta = self._tag_metadata.get(tag, {})
                score_text = self._format_score(meta.get("score"))
                canonical_text = str(meta.get("canonical_tag") or tag)
                llm_token_text = str(meta.get("llm_token") or "")
                excluded = bool(meta.get("filename_excluded", tag in self._filename_excluded_tags))
                excluded_text = "Y" if excluded else "N"
                scoring_excluded = bool(meta.get("scoring_excluded", False))
                ignore_category_influence = bool(meta.get("ignore_category_influence", False))
                ignore_recommendation_score = bool(meta.get("ignore_recommendation_score", False))
                ignore_llm_input = bool(meta.get("ignore_llm_input", False))
                average_text = "off" if scoring_excluded else self._format_average_rating(meta.get("average_rating"))
                display_text = tag
                saved_count = int(meta.get("saved_count") or 0)
                rejected_count = int(meta.get("rejected_count") or 0)
                post_count = int(meta.get("post_count") or 0)
                tooltip = (
                    f"Tag: {tag}\n"
                    f"Canonical/Alias: {canonical_text}\n"
                    f"LLM-Token: {llm_token_text or '-'}\n"
                    f"Score: {score_text}\n"
                    f"Saved/rejected: {saved_count}/{rejected_count} of {post_count} known posts\n"
                    f"Filename-Exclude: {'yes' if excluded else 'no'}\n"
                    f"Legacy tag scoring excluded: {'yes' if scoring_excluded else 'no'}\n"
                    f"Category hint ignored: {'yes' if ignore_category_influence else 'no'}\n"
                    f"Preselection ignored: {'yes' if ignore_recommendation_score else 'no'}\n"
                    f"LLM input ignored: {'yes' if ignore_llm_input else 'no'}\n"
                    f"Average stars: {average_text}"
                )
                meta_item_widget = self._create_detail_row_widget(
                    tag_type=tag_type,
                    tag=tag,
                    score_text=score_text,
                    excluded_text=excluded_text,
                    average_text=average_text,
                )

            # For widget-backed General/Meta rows the QListWidgetItem text must
            # stay empty. Otherwise some styles/delegates still paint the item
            # text behind the widget, which looks like a mysterious bold ghost
            # label. Naturally, text rendering needed an exorcism.
            item = QListWidgetItem("" if meta_item_widget is not None else display_text)
            item.setData(Qt.UserRole, tag)
            item.setData(Qt.UserRole + 1, tag_type)
            item.setToolTip(tooltip)
            item.setForeground(QColor(TAG_TYPE_COLORS[tag_type]))
            if meta_item_widget is not None:
                item.setSizeHint(meta_item_widget.sizeHint())
            list_widget.addItem(item)
            if meta_item_widget is not None:
                list_widget.setItemWidget(item, meta_item_widget)


    def _create_detail_row_widget(
        self,
        tag_type: str,
        tag: str,
        score_text: str,
        excluded_text: str,
        average_text: str,
    ) -> QWidget:
        """Create a compact row: tag left, metadata columns right.

        QListWidget's plain item text is not great for aligned columns with a
        proportional UI font. So General/Meta rows use a small embedded widget:
        tag name gets the free space, the three detail columns stay fixed on
        the right. Because apparently even text needs a layout manager now.
        """
        row = QWidget()
        row.setAutoFillBackground(False)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 0, 4, 0)
        row_layout.setSpacing(6)

        base_font = self.lists[tag_type].font() if tag_type in self.lists else self.font()
        base_font.setBold(False)

        tag_label = QLabel(tag)
        tag_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        tag_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        tag_label.setFont(base_font)
        tag_label.setProperty("tag_row_role", "tag")
        tag_label.setStyleSheet(f"color: {TAG_TYPE_COLORS[tag_type]}; background: transparent;")
        row_layout.addWidget(tag_label, stretch=1)

        columns = (
            ("S:", score_text, 58, "Score"),
            ("✖:", excluded_text, 48, "Filename exclude: Y = yes, N = no"),
            ("⌀☆:", average_text, 76, "Average stars / off = excluded from scoring"),
        )
        for prefix, value, width, tooltip in columns:
            label = QLabel(f"{prefix} {value}")
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            label.setFixedWidth(width)
            label.setToolTip(tooltip)
            label.setFont(base_font)
            # Keep proportional font like the tag lists. The fixed label widths
            # provide alignment; a separate monospace font just made the rows
            # look like they escaped from another UI.
            label.setProperty("tag_row_role", "detail")
            label.setStyleSheet("color: #dddddd; background: transparent;")
            row_layout.addWidget(label)

        row.setStyleSheet("background: transparent;")
        return row

    def _sync_detail_row_selection_colors(self) -> None:
        """Keep custom General/Meta row widgets readable while selected.

        QListWidget::item:selected changes the palette for plain item text, but
        embedded widgets keep their own QLabel stylesheet. Without this sync,
        selected General/Meta rows can end up with purple/grey text on a
        purple/grey selection background. Naturally Qt made the easy thing the
        one thing it refuses to do automatically.
        """
        for tag_type in ("general", "meta"):
            list_widget = self.lists.get(tag_type)
            if list_widget is None:
                continue
            normal_tag_color = TAG_TYPE_COLORS[tag_type]
            for row_index in range(list_widget.count()):
                item = list_widget.item(row_index)
                widget = list_widget.itemWidget(item)
                if widget is None:
                    continue
                selected = item.isSelected()
                for label in widget.findChildren(QLabel):
                    role = label.property("tag_row_role")
                    if selected:
                        color = "#000000"
                    elif role == "tag":
                        color = normal_tag_color
                    else:
                        color = "#dddddd"
                    label.setStyleSheet(f"color: {color}; background: transparent;")

    @staticmethod
    def _format_score(value: Any) -> str:
        if value in {None, "", "None"}:
            return "0"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if number.is_integer():
            return str(int(number))
        return f"{number:.2f}"

    @staticmethod
    def _format_average_rating(value: Any) -> str:
        if value in {None, "", "None"}:
            return "-"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        return f"{number:.1f}"

    def _autosize_lists(self) -> None:
        identity_types = ("artist", "copyright", "character")
        identity_row_height = 18
        for tag_type in identity_types:
            list_widget = self.lists[tag_type]
            if list_widget.count():
                identity_row_height = max(identity_row_height, list_widget.sizeHintForRow(0))
        identity_rows = max(1, min(2, max(self.lists[tag_type].count() for tag_type in identity_types)))
        identity_height = identity_rows * max(18, identity_row_height) + 8

        for tag_type in identity_types:
            list_widget = self.lists[tag_type]
            list_widget.setMinimumHeight(identity_height)
            list_widget.setMaximumHeight(identity_height)

        label_height = 20
        self.identity_group.setMinimumHeight(label_height + identity_height + 2)
        self.identity_group.setMaximumHeight(label_height + identity_height + 2)

        # General is the high-volume tag group. It may expand into all free
        # vertical space instead of becoming a tiny scroll box while the panel
        # below is mostly empty. Yes, layouts should not need babysitting, yet
        # here we are.
        general_widget = self.lists["general"]
        general_row_height = max(18, general_widget.sizeHintForRow(0) if general_widget.count() else 18)
        general_min_rows = max(4, min(10, general_widget.count() or 4))
        general_min_height = general_min_rows * general_row_height + 8
        general_widget.setMinimumHeight(general_min_height)
        general_widget.setMaximumHeight(16777215)
        general_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        meta_widget = self.lists["meta"]
        meta_rows = max(1, min(4, meta_widget.count()))
        meta_row_height = max(18, meta_widget.sizeHintForRow(0) if meta_widget.count() else 18)
        meta_height = meta_rows * meta_row_height + 8
        meta_widget.setMinimumHeight(meta_height)
        meta_widget.setMaximumHeight(meta_height)
        meta_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

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

    def is_filename_filter_active(self) -> bool:
        return self.filename_filter_checkbox.isChecked()
