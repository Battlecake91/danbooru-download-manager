from __future__ import annotations

import re
import traceback
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


RULE_LABELS = {
    "include": "Muss enthalten",
    "exclude": "Darf nicht enthalten",
}


def rule_label(rule_type: str) -> str:
    if rule_type.startswith("include_group_"):
        number = rule_type.rsplit("_", 1)[-1]
        try:
            return f"Include-Gruppe {int(number) + 1}"
        except ValueError:
            return "Include-Gruppe"
    return RULE_LABELS.get(rule_type, rule_type)


def split_tag_input(text: str) -> list[str]:
    """Accept copied tag blocks, comma lists or normal space separated Danbooru tags."""
    tags = [part.strip() for part in re.split(r"[\s,;]+", text.strip()) if part.strip()]
    return list(dict.fromkeys(tags))


class CategoryTab(QWidget):
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.current_category_id: int | None = None
        self._known_tags_model = QStringListModel(self)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(8)

        self.top_buttons = QHBoxLayout()

        self.reload_button = QPushButton("Neu laden")
        self.reload_button.clicked.connect(self.reload_all)
        self.top_buttons.addWidget(self.reload_button)

        self.add_category_button = QPushButton("Kategorie hinzufügen")
        self.add_category_button.clicked.connect(lambda: self.safe(self.add_category))
        self.top_buttons.addWidget(self.add_category_button)

        self.save_category_button = QPushButton("Kategorie speichern")
        self.save_category_button.clicked.connect(lambda: self.safe(self.save_selected_category))
        self.top_buttons.addWidget(self.save_category_button)

        self.delete_category_button = QPushButton("Kategorie löschen")
        self.delete_category_button.clicked.connect(lambda: self.safe(self.delete_selected_category))
        self.top_buttons.addWidget(self.delete_category_button)

        self.top_buttons.addStretch(1)
        self.main_layout.addLayout(self.top_buttons)

        self.splitter = QSplitter(Qt.Horizontal)

        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setContentsMargins(0, 0, 6, 0)
        self.left_layout.setSpacing(6)
        self.left_title = QLabel("Kategorien")
        self.left_title.setStyleSheet("font-weight: 600;")
        self.left_layout.addWidget(self.left_title)

        self.category_table = QTableWidget()
        self.category_table.setColumnCount(5)
        self.category_table.setHorizontalHeaderLabels(["ID", "Name", "Ordner", "Hotkey", "Sort"])
        self.category_table.setColumnHidden(0, True)
        self.category_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.category_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.category_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.category_table.setSortingEnabled(True)
        self.category_table.itemSelectionChanged.connect(self.on_category_selection_changed)
        self.category_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.category_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.category_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.category_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.left_layout.addWidget(self.category_table, stretch=1)
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
        self.sort_order_edit.setPlaceholderText("0")
        self.details_layout.addRow("Sortierung", self.sort_order_edit)

        self.right_layout.addWidget(self.details_box)

        self.rule_editor_box = QGroupBox("Regeln schnell bearbeiten")
        self.rule_editor_layout = QVBoxLayout(self.rule_editor_box)
        self.rule_editor_layout.setSpacing(6)

        self.rule_hint = QLabel(
            "Mehrere Tags koennen mit Leerzeichen, Komma oder Semikolon getrennt werden. "
            "Include = Kategorie passt, wenn mindestens eines dieser Tags vorhanden ist. "
            "Exclude = Kategorie wird blockiert, wenn eines dieser Tags vorhanden ist."
        )
        self.rule_hint.setWordWrap(True)
        self.rule_hint.setStyleSheet("color: #9aa0a6;")
        self.rule_editor_layout.addWidget(self.rule_hint)

        self.rule_input_row = QHBoxLayout()
        self.rule_tag_edit = QLineEdit()
        self.rule_tag_edit.setPlaceholderText("Tag eingeben, z. B. brown_eyes - mehrere Tags sind erlaubt")
        self.rule_input_row.addWidget(self.rule_tag_edit, stretch=1)

        self.add_include_button = QPushButton("+ Muss enthalten")
        self.add_include_button.clicked.connect(lambda: self.safe(lambda: self.add_rules_from_input("include")))
        self.rule_input_row.addWidget(self.add_include_button)

        self.add_exclude_button = QPushButton("+ Ausschließen")
        self.add_exclude_button.clicked.connect(lambda: self.safe(lambda: self.add_rules_from_input("exclude")))
        self.rule_input_row.addWidget(self.add_exclude_button)

        self.rule_editor_layout.addLayout(self.rule_input_row)

        self.right_layout.addWidget(self.rule_editor_box)

        self.rules_box = QGroupBox("Regeln dieser Kategorie")
        self.rules_layout = QVBoxLayout(self.rules_box)
        self.rules_layout.setSpacing(6)

        self.rule_buttons = QHBoxLayout()

        self.delete_rule_button = QPushButton("Ausgewählte Regel löschen")
        self.delete_rule_button.clicked.connect(lambda: self.safe(self.delete_selected_rule))
        self.rule_buttons.addWidget(self.delete_rule_button)

        self.delete_all_rules_button = QPushButton("Alle Regeln dieser Kategorie löschen")
        self.delete_all_rules_button.clicked.connect(lambda: self.safe(self.delete_all_rules_for_category))
        self.rule_buttons.addWidget(self.delete_all_rules_button)

        self.rule_buttons.addStretch(1)
        self.rules_layout.addLayout(self.rule_buttons)

        self.rules_table = QTableWidget()
        self.rules_table.setColumnCount(4)
        self.rules_table.setHorizontalHeaderLabels(["ID", "Typ", "Tag", "Kategorie"])
        self.rules_table.setColumnHidden(0, True)
        self.rules_table.setColumnHidden(3, True)
        self.rules_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rules_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.rules_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rules_table.setSortingEnabled(True)
        self.rules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.rules_layout.addWidget(self.rules_table, stretch=1)

        self.right_layout.addWidget(self.rules_box, stretch=1)

        self.show_advanced_check = QCheckBox("Erweiterte Felder anzeigen")
        self.show_advanced_check.setChecked(True)
        self.show_advanced_check.stateChanged.connect(self.apply_advanced_visibility)
        self.right_layout.addWidget(self.show_advanced_check)

        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)

        self.main_layout.addWidget(self.splitter, stretch=1)

        self.hint_label = QLabel(
            "Kategorie-Regeln werden in SQLite gespeichert. Der normale Fall ist simpel: "
            "Kategorie links wählen, Tags eingeben, als Muss/Ausschluss hinzufügen."
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
        completer = QCompleter(self._known_tags_model, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.popup().setMinimumWidth(420)
        self.rule_tag_edit.setCompleter(completer)

    def reload_all(self) -> None:
        self.reload_categories()
        self.reload_rules()
        self.setup_tag_completer()

    def reload_categories(self) -> None:
        selected_id = self.current_category_id
        self.category_table.setSortingEnabled(False)
        categories = self.db.list_categories_full()
        self.category_table.setRowCount(len(categories))

        selected_row: int | None = None
        for row_index, row in enumerate(categories):
            values = [
                row["id"],
                row["name"],
                row["folder_name"],
                row["hotkey"] or "",
                row["sort_order"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, int(row["id"]))
                if column in {0, 4}:
                    item.setData(Qt.EditRole, int(value))
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.category_table.setItem(row_index, column, item)
            if selected_id is not None and int(row["id"]) == selected_id:
                selected_row = row_index

        self.category_table.setSortingEnabled(True)
        if selected_row is not None:
            self.category_table.selectRow(selected_row)

    def reload_rules(self) -> None:
        self.rules_table.setSortingEnabled(False)
        rules = self.db.list_category_rules(self.current_category_id)
        self.rules_table.setRowCount(len(rules))

        for row_index, row in enumerate(rules):
            values = [
                row["id"],
                rule_label(str(row["rule_type"])),
                row["tag"],
                row["category_name"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, int(row["id"]))
                if column == 0:
                    item.setData(Qt.EditRole, int(value))
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setToolTip(str(value))
                self.rules_table.setItem(row_index, column, item)

        self.rules_table.setSortingEnabled(True)

    def selected_category_id(self) -> int | None:
        selected = self.category_table.selectedItems()
        if not selected:
            return None
        return int(selected[0].data(Qt.UserRole))

    def selected_rule_ids(self) -> list[int]:
        rows = sorted({item.row() for item in self.rules_table.selectedItems()})
        rule_ids: list[int] = []
        for row in rows:
            item = self.rules_table.item(row, 0)
            if item is not None:
                rule_ids.append(int(item.data(Qt.UserRole)))
        return rule_ids

    def selected_rule_id(self) -> int | None:
        rule_ids = self.selected_rule_ids()
        return rule_ids[0] if rule_ids else None

    def on_category_selection_changed(self) -> None:
        category_id = self.selected_category_id()
        self.current_category_id = category_id

        if category_id is None:
            self.clear_details()
            self.reload_rules()
            return

        row_items = self.category_table.selectedItems()
        if not row_items:
            self.clear_details()
            self.reload_rules()
            return

        row = row_items[0].row()
        self.name_edit.setText(self.category_table.item(row, 1).text())
        self.folder_edit.setText(self.category_table.item(row, 2).text())
        self.hotkey_edit.setText(self.category_table.item(row, 3).text())
        self.sort_order_edit.setText(self.category_table.item(row, 4).text())

        db_row = None
        name_item = self.category_table.item(row, 1)
        if name_item is not None:
            db_row = self.db.get_category_by_name(name_item.text())
        self.output_path_edit.setText(str(db_row["output_path"] or "") if db_row is not None else "")

        self.reload_rules()

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

        sort_order_text = self.sort_order_edit.text().strip()
        sort_order = int(sort_order_text) if sort_order_text else 0

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

    def add_rules_from_input(self, rule_type: str) -> None:
        category_id = self.selected_category_id()
        if category_id is None:
            QMessageBox.information(self, "Regel hinzufügen", "Bitte zuerst eine Kategorie auswählen.")
            return

        tags = split_tag_input(self.rule_tag_edit.text())
        if not tags:
            return

        for tag in tags:
            self.db.add_category_rule(category_id, rule_type, tag)
        self.rule_tag_edit.clear()
        self.reload_rules()

    def add_rule(self, rule_type: str) -> None:
        category_id = self.selected_category_id()
        if category_id is None:
            return

        tag, ok = QInputDialog.getText(self, "Regel hinzufügen", f"Tag für {rule_type}:")
        if not ok or not tag.strip():
            return

        self.db.add_category_rule(category_id, rule_type, tag.strip())
        self.reload_rules()

    def delete_selected_rule(self) -> None:
        rule_ids = self.selected_rule_ids()
        if not rule_ids:
            return

        for rule_id in rule_ids:
            self.db.delete_category_rule(rule_id)
        self.reload_rules()

    def delete_all_rules_for_category(self) -> None:
        category_id = self.selected_category_id()
        if category_id is None:
            return

        result = QMessageBox.question(
            self,
            "Alle Regeln löschen",
            "Alle Regeln dieser Kategorie wirklich löschen?",
        )
        if result != QMessageBox.Yes:
            return

        for row in self.db.list_category_rules(category_id):
            self.db.delete_category_rule(int(row["id"]))
        self.reload_rules()
