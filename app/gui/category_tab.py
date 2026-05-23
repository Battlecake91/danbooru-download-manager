from __future__ import annotations

import re
import traceback
from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QCompleter,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.database import Database


_GROUP_INCLUDE_RE = re.compile(r"^group_(\d+)_include$")
_GROUP_EXCLUDE_RE = re.compile(r"^group_(\d+)_exclude$")
_GLOBAL_INCLUDE_RE = re.compile(r"^global_(\d+)_include$")
_GLOBAL_EXCLUDE_RE = re.compile(r"^global_(\d+)_exclude$")
_LEGACY_INCLUDE_GROUP_RE = re.compile(r"^include_group_(\d+)$")


@dataclass
class RuleGroup:
    index: int
    includes: list[str]
    excludes: list[str]

    def expression(self) -> str:
        parts = list(self.includes)
        parts.extend(f"-{tag}" for tag in self.excludes)
        return " ".join(parts)


def split_tag_input(text: str) -> list[str]:
    """Accept copied tag blocks, comma lists or normal space separated Danbooru tags."""
    tags = [part.strip() for part in re.split(r"[\s,;]+", text.strip()) if part.strip()]
    return list(dict.fromkeys(tags))


def parse_group_expression(text: str) -> tuple[list[str], list[str]]:
    includes: list[str] = []
    excludes: list[str] = []

    for token in split_tag_input(text):
        if token == "-":
            continue
        if token.startswith("-") and len(token) > 1:
            tag = token[1:].strip()
            if tag and tag not in excludes:
                excludes.append(tag)
        else:
            if token not in includes:
                includes.append(token)

    return includes, excludes


def expression_from_parts(includes: list[str], excludes: list[str]) -> str:
    parts = list(dict.fromkeys(includes))
    parts.extend(f"-{tag}" for tag in dict.fromkeys(excludes))
    return " ".join(parts)


def _sorted_groups(groups: dict[int, RuleGroup]) -> list[RuleGroup]:
    return [groups[index] for index in sorted(groups)]


def legacy_rules_to_rule_sets(rules: list[Any]) -> tuple[list[RuleGroup], list[RuleGroup]]:
    """Convert existing rule styles into include groups and global conditions.

    New model:
      - group_N_include/group_N_exclude: OR branches for positive category matches.
      - global_N_include/global_N_exclude: AND conditions applied to every OR branch.

    Legacy model:
      - include tags were OR rules, therefore each include becomes its own group.
      - include_group_N were AND groups.
      - exclude tags were global blockers.
    """
    include_groups: dict[int, RuleGroup] = {}
    global_groups: dict[int, RuleGroup] = {}
    legacy_groups: dict[int, list[str]] = {}
    legacy_includes: list[str] = []
    legacy_excludes: list[str] = []

    for row in rules:
        rule_type = str(row["rule_type"])
        tag = str(row["tag"])

        include_match = _GROUP_INCLUDE_RE.match(rule_type)
        exclude_match = _GROUP_EXCLUDE_RE.match(rule_type)
        global_include_match = _GLOBAL_INCLUDE_RE.match(rule_type)
        global_exclude_match = _GLOBAL_EXCLUDE_RE.match(rule_type)
        legacy_group_match = _LEGACY_INCLUDE_GROUP_RE.match(rule_type)

        if include_match:
            index = int(include_match.group(1))
            group = include_groups.setdefault(index, RuleGroup(index=index, includes=[], excludes=[]))
            if tag not in group.includes:
                group.includes.append(tag)
        elif exclude_match:
            index = int(exclude_match.group(1))
            group = include_groups.setdefault(index, RuleGroup(index=index, includes=[], excludes=[]))
            if tag not in group.excludes:
                group.excludes.append(tag)
        elif global_include_match:
            index = int(global_include_match.group(1))
            group = global_groups.setdefault(index, RuleGroup(index=index, includes=[], excludes=[]))
            if tag not in group.includes:
                group.includes.append(tag)
        elif global_exclude_match:
            index = int(global_exclude_match.group(1))
            group = global_groups.setdefault(index, RuleGroup(index=index, includes=[], excludes=[]))
            if tag not in group.excludes:
                group.excludes.append(tag)
        elif legacy_group_match:
            index = int(legacy_group_match.group(1))
            legacy_groups.setdefault(index, []).append(tag)
        elif rule_type == "include":
            if tag not in legacy_includes:
                legacy_includes.append(tag)
        elif rule_type == "exclude":
            if tag not in legacy_excludes:
                legacy_excludes.append(tag)

    if include_groups or global_groups:
        return _sorted_groups(include_groups), _sorted_groups(global_groups)

    result: list[RuleGroup] = []
    next_index = 0

    for legacy_index in sorted(legacy_groups):
        includes = list(dict.fromkeys(legacy_groups[legacy_index]))
        result.append(RuleGroup(index=next_index, includes=includes, excludes=[]))
        next_index += 1

    # Legacy include semantics were ANY, so each include becomes a single OR group.
    for tag in legacy_includes:
        result.append(RuleGroup(index=next_index, includes=[tag], excludes=[]))
        next_index += 1

    global_result: list[RuleGroup] = []
    if legacy_excludes:
        global_result.append(RuleGroup(index=0, includes=[], excludes=list(legacy_excludes)))

    return result, global_result


class CategoryTab(QWidget):
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.current_category_id: int | None = None
        self._known_tags_model = QStringListModel(self)
        self._loading_groups = False

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(8)

        self.top_buttons = QHBoxLayout()

        self.reload_button = QPushButton("Neu laden")
        self.reload_button.clicked.connect(self.reload_all)
        self.top_buttons.addWidget(self.reload_button)

        self.top_buttons.addStretch(1)
        self.main_layout.addLayout(self.top_buttons)

        self.splitter = QSplitter(Qt.Horizontal)

        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setContentsMargins(0, 0, 6, 0)
        self.left_layout.setSpacing(6)
        self.left_title = QLabel("Kategorien (Priorität: oben gewinnt)")
        self.left_title.setStyleSheet("font-weight: 600;")
        self.left_layout.addWidget(self.left_title)

        self.category_table = QTableWidget()
        self.category_table.setColumnCount(4)
        self.category_table.setHorizontalHeaderLabels(["ID", "Name", "Ordner", "Hotkey"])
        self.category_table.setColumnHidden(0, True)
        self.category_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.category_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.category_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.category_table.setSortingEnabled(False)
        self.category_table.itemSelectionChanged.connect(self.on_category_selection_changed)
        self.category_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.category_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.category_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.left_layout.addWidget(self.category_table, stretch=1)

        self.priority_buttons = QHBoxLayout()
        self.category_up_button = QPushButton("↑ Kategorie hoch")
        self.category_up_button.clicked.connect(lambda: self.safe(lambda: self.move_selected_category(-1)))
        self.priority_buttons.addWidget(self.category_up_button)
        self.category_down_button = QPushButton("↓ Kategorie runter")
        self.category_down_button.clicked.connect(lambda: self.safe(lambda: self.move_selected_category(1)))
        self.priority_buttons.addWidget(self.category_down_button)
        self.left_layout.addLayout(self.priority_buttons)

        self.category_action_buttons = QHBoxLayout()
        self.category_action_buttons.setSpacing(4)

        self.add_category_button = QPushButton("Kategorie hinzufügen")
        self.add_category_button.clicked.connect(lambda: self.safe(self.add_category))
        self.category_action_buttons.addWidget(self.add_category_button)

        self.save_category_button = QPushButton("Kategorie speichern")
        self.save_category_button.clicked.connect(lambda: self.safe(self.save_selected_category))
        self.category_action_buttons.addWidget(self.save_category_button)

        self.delete_category_button = QPushButton("Kategorie löschen")
        self.delete_category_button.clicked.connect(lambda: self.safe(self.delete_selected_category))
        self.category_action_buttons.addWidget(self.delete_category_button)

        self.left_layout.addLayout(self.category_action_buttons)

        self.splitter.addWidget(self.left_panel)

        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(6, 0, 0, 0)
        self.right_layout.setSpacing(8)

        self.details_box = QGroupBox("Kategorie")
        self.details_layout = QFormLayout(self.details_box)
        self.details_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("z. B. Favorites")
        self.details_layout.addRow("Name", self.name_edit)

        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Ordnername, leer = Name")
        self.details_layout.addRow("Ordner", self.folder_edit)

        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Optionaler Zielpfad nur fuer diese Kategorie")
        self.details_layout.addRow("Zielpfad", self.output_path_edit)

        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setPlaceholderText("Optional, z. B. F")
        self.hotkey_edit.setMaxLength(24)
        self.details_layout.addRow("Hotkey", self.hotkey_edit)

        self.sort_order_edit = QLineEdit()
        self.sort_order_edit.setPlaceholderText("wird ueber die Kategorienliste links gesetzt")
        self.sort_order_edit.setReadOnly(True)
        self.details_layout.addRow("Position", self.sort_order_edit)

        self.right_layout.addWidget(self.details_box)

        self.rules_box = QGroupBox("Wann passt diese Kategorie?")
        self.rules_layout = QVBoxLayout(self.rules_box)
        self.rules_layout.setSpacing(6)

        self.rule_hint = QLabel(
            "Jede Include-Regel ist ein alternativer Trefferweg. Tags ohne '-' müssen vorhanden sein, "
            "Tags mit '-' schließen aus. Beispiel: 'maid apron -comic' oder 'school_uniform ribbon'."
        )
        self.rule_hint.setWordWrap(True)
        self.rule_hint.setStyleSheet("color: #9aa0a6;")
        self.rules_layout.addWidget(self.rule_hint)

        self.group_buttons = QHBoxLayout()
        self.add_group_button = QPushButton("+ Include-Regel")
        self.add_group_button.clicked.connect(lambda: self.safe(self.add_group_row))
        self.group_buttons.addWidget(self.add_group_button)

        self.delete_group_button = QPushButton("Include-Regel löschen")
        self.delete_group_button.clicked.connect(lambda: self.safe(self.delete_selected_group_rows))
        self.group_buttons.addWidget(self.delete_group_button)

        self.move_group_up_button = QPushButton("↑ Include-Regel")
        self.move_group_up_button.clicked.connect(lambda: self.safe(lambda: self.move_selected_rule_rows(self.groups_table, -1)))
        self.group_buttons.addWidget(self.move_group_up_button)

        self.move_group_down_button = QPushButton("↓ Include-Regel")
        self.move_group_down_button.clicked.connect(lambda: self.safe(lambda: self.move_selected_rule_rows(self.groups_table, 1)))
        self.group_buttons.addWidget(self.move_group_down_button)

        self.save_groups_button = QPushButton("Regeln speichern")
        self.save_groups_button.clicked.connect(lambda: self.safe(self.save_rule_groups))
        self.group_buttons.addWidget(self.save_groups_button)

        self.group_buttons.addStretch(1)
        self.rules_layout.addLayout(self.group_buttons)

        self.new_group_row = QHBoxLayout()
        self.new_group_edit = QLineEdit()
        self.new_group_edit.setPlaceholderText("Neue Include-Regel, z. B. maid apron -comic")
        self.new_group_edit.returnPressed.connect(lambda: self.safe(self.add_group_from_input))
        self.new_group_row.addWidget(self.new_group_edit, stretch=1)

        self.add_group_from_input_button = QPushButton("Hinzufügen")
        self.add_group_from_input_button.clicked.connect(lambda: self.safe(self.add_group_from_input))
        self.new_group_row.addWidget(self.add_group_from_input_button)
        self.rules_layout.addLayout(self.new_group_row)

        self.groups_table = QTableWidget()
        self.groups_table.setColumnCount(2)
        self.groups_table.setHorizontalHeaderLabels(["Include-Regel", "Tags (UND, '-' = Ausschluss)"])
        self.groups_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.groups_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.groups_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked
        )
        self.groups_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.groups_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.groups_table.itemChanged.connect(self.on_group_item_changed)
        self.rules_layout.addWidget(self.groups_table, stretch=2)

        self.global_hint = QLabel(
            "Globale Bedingungen gelten zusätzlich zu jeder Include-Regel. Nutze sie nur für echte Pflicht- oder Sperr-Tags, "
            "sonst baust du dir eine Kategorie mit Türsteherkomplex."
        )
        self.global_hint.setWordWrap(True)
        self.global_hint.setStyleSheet("color: #9aa0a6;")
        self.rules_layout.addWidget(self.global_hint)

        self.global_buttons = QHBoxLayout()
        self.add_global_button = QPushButton("+ Globale Bedingung")
        self.add_global_button.clicked.connect(lambda: self.safe(self.add_global_row))
        self.global_buttons.addWidget(self.add_global_button)

        self.delete_global_button = QPushButton("Bedingung löschen")
        self.delete_global_button.clicked.connect(lambda: self.safe(self.delete_selected_global_rows))
        self.global_buttons.addWidget(self.delete_global_button)

        self.move_global_up_button = QPushButton("↑ Bedingung")
        self.move_global_up_button.clicked.connect(lambda: self.safe(lambda: self.move_selected_rule_rows(self.global_table, -1)))
        self.global_buttons.addWidget(self.move_global_up_button)

        self.move_global_down_button = QPushButton("↓ Bedingung")
        self.move_global_down_button.clicked.connect(lambda: self.safe(lambda: self.move_selected_rule_rows(self.global_table, 1)))
        self.global_buttons.addWidget(self.move_global_down_button)

        self.global_buttons.addStretch(1)
        self.rules_layout.addLayout(self.global_buttons)

        self.new_global_row = QHBoxLayout()
        self.new_global_edit = QLineEdit()
        self.new_global_edit.setPlaceholderText("Globale Bedingung, z. B. solo -comic")
        self.new_global_edit.returnPressed.connect(lambda: self.safe(self.add_global_from_input))
        self.new_global_row.addWidget(self.new_global_edit, stretch=1)

        self.add_global_from_input_button = QPushButton("Hinzufügen")
        self.add_global_from_input_button.clicked.connect(lambda: self.safe(self.add_global_from_input))
        self.new_global_row.addWidget(self.add_global_from_input_button)
        self.rules_layout.addLayout(self.new_global_row)

        self.global_table = QTableWidget()
        self.global_table.setColumnCount(2)
        self.global_table.setHorizontalHeaderLabels(["Globale Bedingung", "Tags (Pflicht / '-' = Sperre)"])
        self.global_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.global_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.global_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked
        )
        self.global_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.global_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.global_table.itemChanged.connect(self.on_global_item_changed)
        self.rules_layout.addWidget(self.global_table, stretch=1)

        self.right_layout.addWidget(self.rules_box, stretch=1)

        self.show_advanced_check = QCheckBox("Erweiterte Felder anzeigen")
        self.show_advanced_check.setChecked(True)
        self.show_advanced_check.stateChanged.connect(self.apply_advanced_visibility)
        self.right_layout.addWidget(self.show_advanced_check)

        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 4)

        self.main_layout.addWidget(self.splitter, stretch=1)

        self.hint_label = QLabel(
            "Links bestimmt die Kategorie-Reihenfolge den Gewinner. Rechts gilt: mehrere Include-Regeln sind Alternativen; "
            "innerhalb einer Zeile müssen alle positiven Tags passen, Tags mit '-' dürfen nicht vorkommen. "
            "Globale Bedingungen werden zusätzlich auf jede Include-Regel gelegt."
        )
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #9aa0a6;")
        self.main_layout.addWidget(self.hint_label)

        self.setup_tag_completer()
        self.reload_all()
        self.apply_advanced_visibility()

    def safe(self, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Fehler im Kategorie-Tab",
                f"{exc}\n\nDetails:\n{traceback.format_exc()}",
            )


    def setup_tag_completer(self) -> None:
        try:
            rows = self.db.fetch_tag_overview(limit=5000)
            tags = sorted({str(row["tag"]) for row in rows if row["tag"]})
        except Exception:
            tags = []

        self._known_tags_model.setStringList(tags)
        for line_edit in (self.new_group_edit, self.new_global_edit):
            completer = QCompleter(self._known_tags_model, self)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            completer.setCompletionMode(QCompleter.PopupCompletion)
            completer.popup().setMinimumWidth(420)
            line_edit.setCompleter(completer)

    def reload_all(self) -> None:
        self.reload_categories()
        self.reload_groups()
        self.setup_tag_completer()

    def reload_categories(self) -> None:
        selected_id = self.current_category_id
        self.category_table.setSortingEnabled(False)
        self.db.normalize_category_sort_order()
        categories = self.db.list_categories_full()
        self.category_table.setRowCount(len(categories))

        selected_row: int | None = None
        for row_index, row in enumerate(categories):
            values = [
                row["id"],
                row["name"],
                row["folder_name"],
                row["hotkey"] or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, int(row["id"]))
                if column == 0:
                    item.setData(Qt.EditRole, int(value))
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.category_table.setItem(row_index, column, item)
            if selected_id is not None and int(row["id"]) == selected_id:
                selected_row = row_index

        self.category_table.setSortingEnabled(False)
        if selected_row is not None:
            self.category_table.selectRow(selected_row)
        elif len(categories) > 0 and self.current_category_id is None:
            self.category_table.selectRow(0)

    def reload_groups(self) -> None:
        self._loading_groups = True
        try:
            rules = self.db.list_category_rules(self.current_category_id) if self.current_category_id else []
            groups, global_groups = legacy_rules_to_rule_sets(rules)
            self.groups_table.setRowCount(len(groups))
            self.global_table.setRowCount(len(global_groups))

            for row_index, group in enumerate(groups):
                name_item = QTableWidgetItem(f"Include-Regel {row_index + 1}")
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
                name_item.setTextAlignment(Qt.AlignCenter)
                self.groups_table.setItem(row_index, 0, name_item)

                expression_item = QTableWidgetItem(group.expression())
                expression_item.setToolTip(
                    "Include-Regel: Tags ohne '-' müssen vorhanden sein, Tags mit '-' dürfen nicht vorhanden sein."
                )
                self.groups_table.setItem(row_index, 1, expression_item)

            for row_index, group in enumerate(global_groups):
                name_item = QTableWidgetItem(f"Globale Bedingung {row_index + 1}")
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
                name_item.setTextAlignment(Qt.AlignCenter)
                self.global_table.setItem(row_index, 0, name_item)

                expression_item = QTableWidgetItem(group.expression())
                expression_item.setToolTip(
                    "Diese globale Bedingung wird zusätzlich mit jeder Include-Regel kombiniert."
                )
                self.global_table.setItem(row_index, 1, expression_item)
        finally:
            self._loading_groups = False

    def selected_category_id(self) -> int | None:
        selected = self.category_table.selectedItems()
        if not selected:
            return None
        return int(selected[0].data(Qt.UserRole))

    def selected_group_rows(self) -> list[int]:
        return sorted({item.row() for item in self.groups_table.selectedItems()})

    def on_category_selection_changed(self) -> None:
        category_id = self.selected_category_id()
        self.current_category_id = category_id

        if category_id is None:
            self.clear_details()
            self.reload_groups()
            return

        row_items = self.category_table.selectedItems()
        if not row_items:
            self.clear_details()
            self.reload_groups()
            return

        row = row_items[0].row()
        self.name_edit.setText(self.category_table.item(row, 1).text())
        self.folder_edit.setText(self.category_table.item(row, 2).text())
        self.hotkey_edit.setText(self.category_table.item(row, 3).text())
        self.sort_order_edit.setText(str(row + 1))

        db_row = None
        name_item = self.category_table.item(row, 1)
        if name_item is not None:
            db_row = self.db.get_category_by_name(name_item.text())
        self.output_path_edit.setText(str(db_row["output_path"] or "") if db_row is not None else "")

        self.reload_groups()

    def clear_details(self) -> None:
        self.name_edit.clear()
        self.folder_edit.clear()
        self.output_path_edit.clear()
        self.hotkey_edit.clear()
        self.sort_order_edit.clear()

    def apply_advanced_visibility(self) -> None:
        visible = self.show_advanced_check.isChecked()
        self.output_path_edit.setVisible(visible)
        self.sort_order_edit.setVisible(visible)
        for label_index in range(self.details_layout.rowCount()):
            label_item = self.details_layout.itemAt(label_index, QFormLayout.LabelRole)
            field_item = self.details_layout.itemAt(label_index, QFormLayout.FieldRole)
            if not label_item or not field_item:
                continue
            field_widget = field_item.widget()
            label_widget = label_item.widget()
            if field_widget in {self.output_path_edit, self.sort_order_edit} and label_widget:
                label_widget.setVisible(visible)

    def add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "Kategorie hinzufügen", "Name:")
        if not ok or not name.strip():
            return

        category_id = self.db.create_category(name.strip())
        self.current_category_id = category_id
        self.reload_categories()

    def save_selected_category(self) -> None:
        category_id = self.selected_category_id()
        if category_id is None:
            QMessageBox.information(self, "Kategorie speichern", "Bitte zuerst eine Kategorie auswählen.")
            return

        current_row = self.db.execute(
            "SELECT sort_order FROM categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        sort_order = int(current_row["sort_order"] or 0) if current_row is not None else 0

        self.db.update_category(
            category_id=category_id,
            name=self.name_edit.text(),
            folder_name=self.folder_edit.text(),
            output_path=self.output_path_edit.text() or None,
            hotkey=self.hotkey_edit.text() or None,
            sort_order=sort_order,
        )
        self.current_category_id = category_id
        self.reload_categories()

    def delete_selected_category(self) -> None:
        category_id = self.selected_category_id()
        if category_id is None:
            return

        result = QMessageBox.question(
            self,
            "Kategorie löschen",
            "Kategorie wirklich löschen? Zugehörige Regeln werden ebenfalls gelöscht.",
        )
        if result != QMessageBox.Yes:
            return

        self.db.delete_category(category_id)
        self.current_category_id = None
        self.reload_all()

    def move_selected_category(self, direction: int) -> None:
        category_id = self.selected_category_id()
        if category_id is None:
            return

        self.db.move_category_sort_order(category_id, direction)
        self.current_category_id = category_id
        self.reload_categories()

    def expressions_from_table(self, table: QTableWidget) -> list[str]:
        expressions: list[str] = []
        for row in range(table.rowCount()):
            item = table.item(row, 1)
            text = item.text().strip() if item is not None else ""
            includes, excludes = parse_group_expression(text)
            expression = expression_from_parts(includes, excludes)
            if expression:
                expressions.append(expression)
        return expressions

    def current_group_expressions(self) -> list[str]:
        return self.expressions_from_table(self.groups_table)

    def current_global_expressions(self) -> list[str]:
        return self.expressions_from_table(self.global_table)

    def save_rule_groups(self) -> None:
        category_id = self.selected_category_id()
        if category_id is None:
            QMessageBox.information(self, "Regeln speichern", "Bitte zuerst eine Kategorie auswählen.")
            return

        self.db.replace_category_rule_groups(
            category_id,
            self.current_group_expressions(),
            self.current_global_expressions(),
        )
        self.reload_groups()

    def on_group_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading_groups or item.column() != 1:
            return
        self.safe(self.save_rule_groups)

    def on_global_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading_groups or item.column() != 1:
            return
        self.safe(self.save_rule_groups)

    def add_expression_row(self, table: QTableWidget, label_prefix: str, expression: str = "") -> int:
        row = table.rowCount()
        self._loading_groups = True
        try:
            table.insertRow(row)
            name_item = QTableWidgetItem(f"{label_prefix} {row + 1}")
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            name_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 0, name_item)
            table.setItem(row, 1, QTableWidgetItem(expression))
        finally:
            self._loading_groups = False
        table.selectRow(row)
        return row

    def add_group_row(self) -> None:
        row = self.add_expression_row(self.groups_table, "Include-Regel")
        self.groups_table.editItem(self.groups_table.item(row, 1))

    def add_global_row(self) -> None:
        row = self.add_expression_row(self.global_table, "Globale Bedingung")
        self.global_table.editItem(self.global_table.item(row, 1))

    def add_expression_from_input(self, edit: QLineEdit, table: QTableWidget, label_prefix: str) -> None:
        text = edit.text().strip()
        if not text:
            return
        includes, excludes = parse_group_expression(text)
        expression = expression_from_parts(includes, excludes)
        if not expression:
            return
        self.add_expression_row(table, label_prefix, expression)
        edit.clear()
        self.save_rule_groups()

    def add_group_from_input(self) -> None:
        self.add_expression_from_input(self.new_group_edit, self.groups_table, "Include-Regel")

    def add_global_from_input(self) -> None:
        self.add_expression_from_input(self.new_global_edit, self.global_table, "Globale Bedingung")


    def move_selected_rule_rows(self, table: QTableWidget, direction: int) -> None:
        rows = self.selected_rows(table)
        if len(rows) != 1:
            QMessageBox.information(self, "Include-Regel verschieben", "Bitte genau eine Zeile auswählen.")
            return

        row = rows[0]
        target = row + direction
        if target < 0 or target >= table.rowCount():
            return

        current_text = table.item(row, 1).text() if table.item(row, 1) is not None else ""
        target_text = table.item(target, 1).text() if table.item(target, 1) is not None else ""

        self._loading_groups = True
        try:
            table.item(row, 1).setText(target_text)
            table.item(target, 1).setText(current_text)
        finally:
            self._loading_groups = False

        table.selectRow(target)
        self.save_rule_groups()

    def selected_rows(self, table: QTableWidget) -> list[int]:
        return sorted({item.row() for item in table.selectedItems()})

    def selected_group_rows(self) -> list[int]:
        return self.selected_rows(self.groups_table)

    def selected_global_rows(self) -> list[int]:
        return self.selected_rows(self.global_table)

    def delete_rows_from_table(self, table: QTableWidget) -> None:
        rows = self.selected_rows(table)
        if not rows:
            return
        for row in reversed(rows):
            table.removeRow(row)
        self.save_rule_groups()

    def delete_selected_group_rows(self) -> None:
        self.delete_rows_from_table(self.groups_table)

    def delete_selected_global_rows(self) -> None:
        self.delete_rows_from_table(self.global_table)
