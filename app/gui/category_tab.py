from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
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


class CategoryTab(QWidget):
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.current_category_id: int | None = None

        self.main_layout = QVBoxLayout(self)

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

        self.category_table = QTableWidget()
        self.category_table.setColumnCount(6)
        self.category_table.setHorizontalHeaderLabels(
            ["ID", "Name", "Folder", "Output Path", "Hotkey", "Sort"]
        )
        self.category_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.category_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.category_table.itemSelectionChanged.connect(self.on_category_selection_changed)
        self.category_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.splitter.addWidget(self.category_table)

        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)

        self.detail_label = QLabel("Kategorie-Details")
        self.right_layout.addWidget(self.detail_label)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name")
        self.right_layout.addWidget(self.name_edit)

        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Folder Name")
        self.right_layout.addWidget(self.folder_edit)

        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Output Path")
        self.right_layout.addWidget(self.output_path_edit)

        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setPlaceholderText("Hotkey")
        self.right_layout.addWidget(self.hotkey_edit)

        self.sort_order_edit = QLineEdit()
        self.sort_order_edit.setPlaceholderText("Sort Order")
        self.right_layout.addWidget(self.sort_order_edit)

        self.rule_buttons = QHBoxLayout()

        self.add_include_button = QPushButton("Include-Regel hinzufügen")
        self.add_include_button.clicked.connect(lambda: self.safe(lambda: self.add_rule("include")))
        self.rule_buttons.addWidget(self.add_include_button)

        self.add_exclude_button = QPushButton("Exclude-Regel hinzufügen")
        self.add_exclude_button.clicked.connect(lambda: self.safe(lambda: self.add_rule("exclude")))
        self.rule_buttons.addWidget(self.add_exclude_button)

        self.delete_rule_button = QPushButton("Regel löschen")
        self.delete_rule_button.clicked.connect(lambda: self.safe(self.delete_selected_rule))
        self.rule_buttons.addWidget(self.delete_rule_button)

        self.right_layout.addLayout(self.rule_buttons)

        self.rules_table = QTableWidget()
        self.rules_table.setColumnCount(4)
        self.rules_table.setHorizontalHeaderLabels(["ID", "Rule Type", "Tag", "Kategorie"])
        self.rules_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rules_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.rules_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.right_layout.addWidget(self.rules_table, stretch=1)

        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)

        self.main_layout.addWidget(self.splitter)

        self.hint_label = QLabel(
            "SQL ist führend. config.yaml wird nur noch nicht-destruktiv importiert. "
            "Kategorie-Regeln aus der GUI bleiben erhalten."
        )
        self.hint_label.setWordWrap(True)
        self.main_layout.addWidget(self.hint_label)

        self.reload_all()

    def safe(self, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Fehler im Kategorie-Tab",
                f"{exc}\n\nDetails:\n{traceback.format_exc()}",
            )

    def reload_all(self) -> None:
        self.reload_categories()
        self.reload_rules()

    def reload_categories(self) -> None:
        categories = self.db.list_categories_full()
        self.category_table.setRowCount(len(categories))

        for row_index, row in enumerate(categories):
            values = [
                row["id"],
                row["name"],
                row["folder_name"],
                row["output_path"] or "",
                row["hotkey"] or "",
                row["sort_order"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, int(row["id"]))
                if column in {0, 5}:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.category_table.setItem(row_index, column, item)

    def reload_rules(self) -> None:
        rules = self.db.list_category_rules(self.current_category_id)
        self.rules_table.setRowCount(len(rules))

        for row_index, row in enumerate(rules):
            values = [
                row["id"],
                row["rule_type"],
                row["tag"],
                row["category_name"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, int(row["id"]))
                if column == 0:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.rules_table.setItem(row_index, column, item)

    def selected_category_id(self) -> int | None:
        selected = self.category_table.selectedItems()
        if not selected:
            return None
        return int(selected[0].data(Qt.UserRole))

    def selected_rule_id(self) -> int | None:
        selected = self.rules_table.selectedItems()
        if not selected:
            return None
        return int(selected[0].data(Qt.UserRole))

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
        self.output_path_edit.setText(self.category_table.item(row, 3).text())
        self.hotkey_edit.setText(self.category_table.item(row, 4).text())
        self.sort_order_edit.setText(self.category_table.item(row, 5).text())

        self.reload_rules()

    def clear_details(self) -> None:
        self.name_edit.clear()
        self.folder_edit.clear()
        self.output_path_edit.clear()
        self.hotkey_edit.clear()
        self.sort_order_edit.clear()

    def add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "Kategorie hinzufügen", "Name:")
        if not ok or not name.strip():
            return

        self.db.create_category(name.strip())
        self.reload_categories()

    def save_selected_category(self) -> None:
        category_id = self.selected_category_id()
        if category_id is None:
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
        rule_id = self.selected_rule_id()
        if rule_id is None:
            return

        self.db.delete_category_rule(rule_id)
        self.reload_rules()
