from __future__ import annotations

import faulthandler
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from app.core.database import Database
from app.i18n.i18n import tr


TAG_SOURCE_LABELS = {
    "local": "Used locally",
    "both": "Local + Danbooru catalog",
    "catalog": "Danbooru catalog",
    "catalog_only": "Catalog only (unused locally)",
}


TAG_TYPE_LABELS = {
    "all": "All",
    "copyright": "Copyright",
    "character": "Character",
    "artist": "Artist",
    "general": "General",
    "meta": "Meta",
}


class SortableTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem with sane numeric sorting.

    Qt sorts table items lexicographically by default. That means 100 can
    happily come before 9, because apparently strings were invited to a number
    party. Store an explicit sort value and compare that when possible.
    """

    SORT_ROLE = Qt.UserRole + 10

    def __lt__(self, other: QTableWidgetItem) -> bool:
        left = self.data(self.SORT_ROLE)
        right = other.data(self.SORT_ROLE)

        if left is not None and right is not None:
            try:
                return float(left) < float(right)
            except (TypeError, ValueError):
                return str(left).casefold() < str(right).casefold()

        return self.text().casefold() < other.text().casefold()


class SimilarTagsBulkActionDialog(QDialog):
    """Bulk action dialog for tags found by a wildcard pattern.

    The old dialog only knew aliases. Naturally that was too narrow, because
    apparently tags now need a small administrative office. This dialog keeps
    the useful checkable result list, but lets the selected matches receive all
    configured bulk operations in one pass.
    """

    FILENAME_NO_CHANGE = "none"
    FILENAME_ADD = "add"
    FILENAME_REMOVE = "remove"
    CATEGORY_NO_CHANGE = ""
    FLAG_NO_CHANGE = "none"
    FLAG_IGNORE = "ignore"
    FLAG_USE = "use"

    def __init__(self, parent: QWidget, rows: list[Any], category_names: list[str], suggested_alias: str = "") -> None:
        super().__init__(parent)
        self.config = getattr(parent, "config", {})
        self.setWindowTitle(self.t("tags.similar.title", "Edit similar tags"))
        self.resize(820, 640)

        layout = QVBoxLayout(self)

        info = QLabel(
            self.t(
                "tags.similar.info",
                "Select the tags and enter only the actions that should actually be applied. "
                "Empty fields stay unchanged."
            )
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        for row in rows:
            tag = str(row["tag"] or "")
            alias = str(row["alias_tag"] or "")
            post_count = int(row["post_count"] or 0)
            tag_type = str(row["tag_type"] or "")
            filename_excluded = bool(int(row["filename_excluded"] or 0))
            ignore_category_influence = bool(int(row["ignore_category_influence"] or 0))
            ignore_recommendation_score = bool(int(row["ignore_recommendation_score"] or 0))
            ignore_llm_input = bool(int(row["ignore_llm_input"] or 0))

            suffix = f" | {tag_type} | {post_count} Posts"
            if alias:
                suffix += f" | Alias: {alias}"
            if filename_excluded:
                suffix += " | Filename-Exclude"
            flag_labels: list[str] = []
            if ignore_category_influence:
                flag_labels.append(self.t("tags.flags.category_ignored_short", "Category hint ignored"))
            if ignore_recommendation_score:
                flag_labels.append(self.t("tags.flags.preselection_ignored_short", "Preselection ignored"))
            if ignore_llm_input:
                flag_labels.append(self.t("tags.flags.llm_ignored_short", "LLM ignored"))
            if flag_labels:
                suffix += " | " + ", ".join(flag_labels)

            item = QListWidgetItem(f"{tag}{suffix}")
            item.setData(Qt.UserRole, tag)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget, stretch=1)

        select_buttons = QHBoxLayout()
        select_all = QPushButton(self.t("common.select_all", "Select all"))
        select_none = QPushButton(self.t("common.select_none", "Select none"))
        select_all.clicked.connect(lambda: self.set_all_checked(True))
        select_none.clicked.connect(lambda: self.set_all_checked(False))
        select_buttons.addWidget(select_all)
        select_buttons.addWidget(select_none)
        select_buttons.addStretch(1)
        layout.addLayout(select_buttons)

        layout.addWidget(QLabel(self.t("tags.bulk.actions_for_selected", "Actions for all selected tags:")))

        alias_row = QHBoxLayout()
        alias_row.addWidget(QLabel(self.t("tags.bulk.set_alias", "Set alias:")))
        self.alias_edit = QLineEdit("")
        self.alias_edit.setPlaceholderText(suggested_alias or self.t("tags.bulk.placeholder.no_change", "empty = no change"))
        alias_row.addWidget(self.alias_edit, stretch=1)
        layout.addLayout(alias_row)

        filename_row = QHBoxLayout()
        filename_row.addWidget(QLabel(self.t("tags.bulk.filename_exclude", "Filename exclude:")))
        self.filename_combo = QComboBox()
        self.filename_combo.addItem(self.t("common.no_change", "no change"), self.FILENAME_NO_CHANGE)
        self.filename_combo.addItem(self.t("tags.bulk.filename_add", "add to filename exclude"), self.FILENAME_ADD)
        self.filename_combo.addItem(self.t("tags.bulk.filename_remove", "remove from filename exclude"), self.FILENAME_REMOVE)
        filename_row.addWidget(self.filename_combo, stretch=1)
        layout.addLayout(filename_row)

        scoring_row = QHBoxLayout()
        scoring_row.addWidget(QLabel(self.t("tags.bulk.scoring_flags", "Scoring / usage flags:")))
        self.category_influence_combo = QComboBox()
        self.category_influence_combo.addItem(self.t("tags.flags.category_no_change", "category hint: no change"), self.FLAG_NO_CHANGE)
        self.category_influence_combo.addItem(self.t("tags.flags.category_ignore", "ignore category hint"), self.FLAG_IGNORE)
        self.category_influence_combo.addItem(self.t("tags.flags.category_use", "use category hint again"), self.FLAG_USE)
        self.recommendation_combo = QComboBox()
        self.recommendation_combo.addItem(self.t("tags.flags.preselection_no_change", "preselection: no change"), self.FLAG_NO_CHANGE)
        self.recommendation_combo.addItem(self.t("tags.flags.preselection_ignore", "ignore preselection"), self.FLAG_IGNORE)
        self.recommendation_combo.addItem(self.t("tags.flags.preselection_use", "use preselection again"), self.FLAG_USE)
        self.llm_input_combo = QComboBox()
        self.llm_input_combo.addItem(self.t("tags.flags.llm_no_change", "LLM input: no change"), self.FLAG_NO_CHANGE)
        self.llm_input_combo.addItem(self.t("tags.flags.llm_ignore", "ignore LLM input"), self.FLAG_IGNORE)
        self.llm_input_combo.addItem(self.t("tags.flags.llm_use", "use LLM input again"), self.FLAG_USE)
        scoring_row.addWidget(self.category_influence_combo, stretch=1)
        scoring_row.addWidget(self.recommendation_combo, stretch=1)
        scoring_row.addWidget(self.llm_input_combo, stretch=1)
        layout.addLayout(scoring_row)

        score_row = QHBoxLayout()
        self.score_checkbox = QCheckBox(self.t("tags.bulk.set_manual_score", "Set manual score"))
        self.score_spin = QDoubleSpinBox()
        self.score_spin.setRange(-10.0, 10.0)
        self.score_spin.setDecimals(3)
        self.score_spin.setSingleStep(0.25)
        self.score_spin.setEnabled(False)
        self.score_checkbox.toggled.connect(self.score_spin.setEnabled)
        score_row.addWidget(self.score_checkbox)
        score_row.addWidget(self.score_spin)
        score_row.addStretch(1)
        layout.addLayout(score_row)

        category_row = QHBoxLayout()
        category_row.addWidget(QLabel(self.t("tags.bulk.category_rule", "Category rule:")))
        self.category_combo = QComboBox()
        self.category_combo.addItem(self.t("common.no_change", "no change"), self.CATEGORY_NO_CHANGE)
        for category_name in category_names:
            self.category_combo.addItem(category_name, category_name)
        self.category_rule_combo = QComboBox()
        self.category_rule_combo.addItem("include", "include")
        self.category_rule_combo.addItem("exclude", "exclude")
        category_row.addWidget(self.category_combo, stretch=1)
        category_row.addWidget(self.category_rule_combo)
        layout.addLayout(category_row)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.button(QDialogButtonBox.Ok).setText(self.t("common.apply", "Apply"))
        button_box.button(QDialogButtonBox.Cancel).setText(self.t("common.cancel", "Cancel"))
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def t(self, key: str, default: str, **kwargs: Any) -> str:
        return tr(key, default, config=self.config, **kwargs)

    def set_all_checked(self, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        for index in range(self.list_widget.count()):
            self.list_widget.item(index).setCheckState(state)

    def yes_text(self) -> str:
        return self.t("common.yes", "yes")

    def selected_tags(self) -> list[str]:
        tags: list[str] = []
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.checkState() != Qt.Checked:
                continue
            tag = item.data(Qt.UserRole)
            if tag:
                tags.append(str(tag))
        return tags

    def alias_to_set(self) -> str | None:
        alias = self.alias_edit.text().strip()
        return alias if alias else None

    def filename_action(self) -> str:
        return str(self.filename_combo.currentData() or self.FILENAME_NO_CHANGE)

    def manual_score(self) -> float | None:
        if not self.score_checkbox.isChecked():
            return None
        return float(self.score_spin.value())

    def scoring_flag_actions(self) -> dict[str, bool | None]:
        def combo_to_value(combo: QComboBox) -> bool | None:
            value = str(combo.currentData() or self.FLAG_NO_CHANGE)
            if value == self.FLAG_IGNORE:
                return True
            if value == self.FLAG_USE:
                return False
            return None

        return {
            "ignore_category_influence": combo_to_value(self.category_influence_combo),
            "ignore_recommendation_score": combo_to_value(self.recommendation_combo),
            "ignore_llm_input": combo_to_value(self.llm_input_combo),
        }

    def category_action(self) -> tuple[str | None, str | None]:
        category_name = str(self.category_combo.currentData() or "")
        if not category_name:
            return None, None
        return category_name, str(self.category_rule_combo.currentData() or "include")

    def has_any_action(self) -> bool:
        category_name, _ = self.category_action()
        return any(
            [
                self.alias_to_set() is not None,
                self.filename_action() != self.FILENAME_NO_CHANGE,
                self.manual_score() is not None,
                any(value is not None for value in self.scoring_flag_actions().values()),
                category_name is not None,
            ]
        )


class TagTab(QWidget):
    """Tag overview/configuration tab.

    This version is deliberately conservative around context-menu actions:
    - QAction callbacks are delayed with QTimer.singleShot(0, ...).
    - Filename-exclude, alias and manual-score changes do not immediately run the expensive overview reload.
    - Long-running/hanging operations write watchdog stack dumps.
    """

    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.current_rows: list[Any] = []
        self._context_menu: QMenu | None = None
        self._reload_pending = False
        self._sort_column: int | None = None
        self._sort_order = Qt.DescendingOrder
        self._suppress_item_changed = False

        work_dir = Path(str(config.get("work_dir", ".")))
        self.log_dir = work_dir / "logs"
        self.log_path = self.log_dir / "gui_error.log"
        self.tag_log_path = self.log_dir / "tag_tab_error.log"
        self.hang_log_path = self.log_dir / "tag_tab_hang_dump.log"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.enable_fault_handler()

        self.main_layout = QVBoxLayout(self)

        self.toolbar_layout = QHBoxLayout()

        self.toolbar_layout.addWidget(QLabel(self.t("common.search.label", "Search: ")))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.t("tags.search.placeholder", "Search tags..."))
        self.search_edit.returnPressed.connect(lambda: self.safe(self.reload_tags, self.t("tags.action.reload", "Reload tags")))
        self.toolbar_layout.addWidget(self.search_edit, stretch=1)

        self.toolbar_layout.addWidget(QLabel(self.t("tags.source.label", "Source:")))
        self.source_filter = QComboBox()
        for source_key, label in TAG_SOURCE_LABELS.items():
            self.source_filter.addItem(self.t(f"tags.source.{source_key}", label), source_key)
        self.source_filter.setCurrentIndex(1)
        self.source_filter.currentIndexChanged.connect(lambda *_: self.safe(self.reload_tags, self.t("tags.action.reload", "Reload tags")))
        self.toolbar_layout.addWidget(self.source_filter)

        self.toolbar_layout.addWidget(QLabel(self.t("tags.type.label", "Type:")))
        self.type_filter = QComboBox()
        for tag_type, label in TAG_TYPE_LABELS.items():
            self.type_filter.addItem(label, tag_type)
        self.type_filter.currentIndexChanged.connect(lambda *_: self.safe(self.reload_tags, self.t("tags.action.reload", "Reload tags")))
        self.toolbar_layout.addWidget(self.type_filter)

        self.reload_button = QPushButton(self.t("common.reload", "Reload"))
        self.reload_button.clicked.connect(lambda *_: self.safe(self.reload_tags, self.t("tags.action.reload", "Reload tags")))
        self.toolbar_layout.addWidget(self.reload_button)

        self.main_layout.addLayout(self.toolbar_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(14)
        self.table.setHorizontalHeaderLabels(
            [
                self.t("tags.table.tag", "Tag"),
                self.t("tags.table.type", "Type"),
                self.t("tags.table.posts", "Posts"),
                self.t("tags.table.open", "Open"),
                self.t("tags.table.saved", "Saved"),
                self.t("tags.table.rejected", "Rejected"),
                self.t("tags.table.alias", "Alias"),
                self.t("tags.table.filename_exclude", "Filename exclude"),
                self.t("tags.table.category_scoring_ignored", "Category scoring ignored"),
                self.t("tags.table.preselection_ignored", "Preselection ignored"),
                self.t("tags.table.llm_ignored", "LLM ignored"),
                self.t("tags.table.manual_score", "Manual score"),
                self.t("tags.table.computed_score", "Computed score"),
                self.t("tags.table.average_stars", "Avg. stars"),
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(
            lambda pos: self.safe(lambda: self.open_context_menu(pos), self.t("tags.action.open_context_menu", "Open context menu"))
        )
        self.table.itemClicked.connect(
            lambda item: self.safe(lambda: self.handle_option_cell_click(item), self.t("tags.action.toggle_option", "Toggle tag option"))
        )
        self.table.itemChanged.connect(
            lambda item: self.safe(lambda: self.handle_editable_cell_changed(item), self.t("tags.action.edit_cell", "Edit tag cell"))
        )

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 14):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(lambda column: self.safe(lambda: self.sort_by_column(column), self.t("tags.action.sort", "Sort tags")))

        self.main_layout.addWidget(self.table)

        self.hint_label = QLabel(
            self.t("tags.hint", "Click filename/scoring columns to toggle options directly. Alias and manual score are editable in the table. Right-click for category, scoring/usage, bulk alias and search actions. Error log: {path}", path=self.tag_log_path)
        )
        self.hint_label.setWordWrap(True)
        self.main_layout.addWidget(self.hint_label)

        self.safe(self.reload_tags, self.t("tags.action.initial_load", "Initial tag load"))

    # ------------------------------------------------------------------
    # Logging / safety helpers
    # ------------------------------------------------------------------

    def enable_fault_handler(self) -> None:
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self._fault_log_handle = self.hang_log_path.open("a", encoding="utf-8")
            faulthandler.enable(file=self._fault_log_handle, all_threads=True)
        except Exception:
            # If even the logger fails, do not break the GUI startup.
            pass

    def log_message(self, message: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}\n"
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with self.tag_log_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
        except Exception:
            pass
        print(line.rstrip(), flush=True)

    def write_error_log(self, traceback_text: str) -> None:
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            for path in (self.log_path, self.tag_log_path):
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "=" * 100 + "\n")
                    handle.write(traceback_text)
                    handle.write("\n")
        except Exception:
            pass

    def t(self, key: str, default: str, **kwargs: Any) -> str:
        return tr(key, default, config=self.config, **kwargs)

    def safe(self, action: Callable[[], None], title: str = "Tag tab action") -> None:
        self.log_message(f"START: {title}")
        watchdog_done = self.start_watchdog(title)
        try:
            action()
            self.log_message(f"OK: {title}")
        except Exception as exc:
            traceback_text = traceback.format_exc()
            self.write_error_log(traceback_text)
            self.log_message(f"ERROR: {title}: {exc}")
            QMessageBox.critical(
                self,
                self.t("tags.error.title", "Tag tab error"),
                self.t("tags.error.failed", "{title} failed:\n\n{error}\n\nLog: {log}", title=title, error=exc, log=self.tag_log_path),
            )
        finally:
            watchdog_done.set()

    def schedule_safe(self, action: Callable[[], None], title: str = "Tag tab action") -> None:
        QTimer.singleShot(0, lambda: self.safe(action, title))

    def start_watchdog(self, title: str, timeout_seconds: float = 15.0) -> threading.Event:
        done = threading.Event()

        def watchdog() -> None:
            if done.wait(timeout_seconds):
                return

            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                with self.hang_log_path.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "=" * 100 + "\n")
                    handle.write(f"HANG WATCHDOG after {timeout_seconds:.1f}s: {title}\n")
                    faulthandler.dump_traceback(file=handle, all_threads=True)
                    handle.write("\n")
            except Exception:
                pass

            print(f"[TAG_TAB_HANG] Operation haengt wahrscheinlich: {title}", file=sys.stderr, flush=True)

        threading.Thread(target=watchdog, daemon=True).start()
        return done

    # ------------------------------------------------------------------
    # Data loading / table helpers
    # ------------------------------------------------------------------

    def selected_tag_source(self) -> str:
        if hasattr(self, "source_filter"):
            return str(self.source_filter.currentData() or "both")
        return "both"

    def selected_tag_type(self) -> str:
        return str(self.type_filter.currentData())

    def search_text(self) -> str | None:
        text = self.search_edit.text().strip()
        return text or None

    def reload_tags_later(self) -> None:
        if self._reload_pending:
            return
        self._reload_pending = True

        def do_reload() -> None:
            self._reload_pending = False
            self.safe(self.reload_tags, self.t("tags.action.delayed_reload", "Delayed tag reload"))

        QTimer.singleShot(50, do_reload)

    def sort_by_column(self, column: int) -> None:
        if self._sort_column == column:
            self._sort_order = (
                Qt.AscendingOrder
                if self._sort_order == Qt.DescendingOrder
                else Qt.DescendingOrder
            )
        else:
            self._sort_column = column
            self._sort_order = Qt.AscendingOrder if column in {0, 1, 6, 7, 8, 9, 10} else Qt.DescendingOrder

        self.apply_current_sort()

    def apply_current_sort(self) -> None:
        if self._sort_column is None:
            return

        header = self.table.horizontalHeader()
        header.setSortIndicator(self._sort_column, self._sort_order)
        self.table.sortItems(self._sort_column, self._sort_order)

    def format_number_cell(self, value: Any, decimals: int = 1, empty: str = "") -> str:
        if value is None or str(value) in {"", "None"}:
            return empty

        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)

        text = f"{number:.{decimals}f}"
        return text.rstrip("0").rstrip(".")

    def make_table_item(self, tag: str, value: Any, sort_value: Any | None = None, align_right: bool = False) -> QTableWidgetItem:
        item = SortableTableWidgetItem("" if value is None else str(value))
        item.setData(Qt.UserRole, tag)
        item.setData(SortableTableWidgetItem.SORT_ROLE, sort_value if sort_value is not None else value)
        if align_right:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

    def reload_tags(self) -> None:
        self.log_message("fetch_tag_overview: begin")
        rows = self.db.fetch_tag_overview(
            search_text=self.search_text(),
            tag_type=self.selected_tag_type(),
            limit=5000,
            source=self.selected_tag_source(),
        )
        self.log_message(f"fetch_tag_overview: end, rows={len(rows)}")

        self.current_rows = rows

        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.clearContents()
            self.table.setRowCount(len(self.current_rows))

            for row_index, row in enumerate(self.current_rows):
                tag = str(row["tag"] or "")
                manual_score = row["manual_score"]
                computed_score = row["computed_score"]
                average_rating = row["average_rating"]
                filename_excluded = bool(int(row["filename_excluded"] or 0))
                ignore_category_influence = bool(int(row["ignore_category_influence"] or 0))
                ignore_recommendation_score = bool(int(row["ignore_recommendation_score"] or 0))
                ignore_llm_input = bool(int(row["ignore_llm_input"] or 0))

                values: list[tuple[Any, Any, bool]] = [
                    (tag, tag, False),
                    (row["tag_type"], row["tag_type"], False),
                    (row["post_count"], row["post_count"], True),
                    (row["open_count"], row["open_count"], True),
                    (row["saved_count"], row["saved_count"], True),
                    (row["rejected_count"], row["rejected_count"], True),
                    (row["alias_tag"] or "", row["alias_tag"] or "", False),
                    (self.yes_text() if filename_excluded else "", 1 if filename_excluded else 0, False),
                    (self.yes_text() if ignore_category_influence else "", 1 if ignore_category_influence else 0, False),
                    (self.yes_text() if ignore_recommendation_score else "", 1 if ignore_recommendation_score else 0, False),
                    (self.yes_text() if ignore_llm_input else "", 1 if ignore_llm_input else 0, False),
                    (self.format_number_cell(manual_score, decimals=2), manual_score if manual_score not in {"", None} else -999999, True),
                    (self.format_number_cell(computed_score, decimals=2, empty="0"), computed_score, True),
                    (self.format_number_cell(average_rating, decimals=1), average_rating if average_rating is not None else -1, True),
                ]

                for column, (display_value, sort_value, align_right) in enumerate(values):
                    table_item = self.make_table_item(
                        tag,
                        display_value,
                        sort_value=sort_value,
                        align_right=align_right,
                    )
                    if column in {6, 11}:
                        table_item.setFlags(table_item.flags() | Qt.ItemIsEditable)
                    else:
                        table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)

                    self.table.setItem(row_index, column, table_item)

            self.apply_current_sort()
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

    def yes_text(self) -> str:
        return self.t("common.yes", "yes")

    def selected_tags(self) -> list[str]:
        tags: list[str] = []
        seen: set[str] = set()

        selected_ranges = self.table.selectedRanges()
        for selected_range in selected_ranges:
            for row in range(selected_range.topRow(), selected_range.bottomRow() + 1):
                item = self.table.item(row, 0)
                if item is None:
                    continue
                tag = item.data(Qt.UserRole)
                if tag and str(tag) not in seen:
                    tags.append(str(tag))
                    seen.add(str(tag))

        return tags

    def tags_for_context_position(self, position) -> list[str]:  # noqa: ANN001
        item = self.table.itemAt(position)
        clicked_tag = self.tag_from_item(item)

        selected = self.selected_tags()

        if clicked_tag and clicked_tag not in selected:
            row = item.row() if item is not None else -1
            if row >= 0:
                self.table.clearSelection()
                self.table.selectRow(row)
            return [clicked_tag]

        if selected:
            return selected

        if clicked_tag:
            return [clicked_tag]

        return []

    def tag_from_item(self, item: QTableWidgetItem | None) -> str | None:
        if item is None:
            return None
        tag = item.data(Qt.UserRole)
        return str(tag) if tag else None

    FLAG_OPTION_COLUMNS = {
        7: "filename_excluded",
        8: "ignore_category_influence",
        9: "ignore_recommendation_score",
        10: "ignore_llm_input",
    }

    def is_yes_cell(self, row_index: int, column: int) -> bool:
        item = self.table.item(row_index, column)
        if item is None:
            return False
        return item.text().strip().lower() in {"yes", "true", "1", "x"}

    def handle_option_cell_click(self, item: QTableWidgetItem) -> None:
        if item is None:
            return

        column = item.column()
        if column not in self.FLAG_OPTION_COLUMNS:
            return

        tag = self.tag_from_item(item)
        if not tag:
            return

        new_value = not self.is_yes_cell(item.row(), column)
        selected = self.selected_tags()
        tags = selected if tag in selected and len(selected) > 1 else [tag]

        if column == 7:
            if new_value:
                self.add_tags_to_filename_exclude(tags)
            else:
                self.remove_tags_from_filename_exclude(tags)
            return

        kwargs = {
            "ignore_category_influence": None,
            "ignore_recommendation_score": None,
            "ignore_llm_input": None,
        }
        key = self.FLAG_OPTION_COLUMNS[column]
        kwargs[key] = new_value
        self.set_scoring_flags_for_tags(tags, **kwargs)

    def current_manual_score_for_tag(self, tag: str) -> float | None:
        for row in self.current_rows:
            try:
                if str(row["tag"]) != tag:
                    continue
                value = row["manual_score"]
            except Exception:
                continue

            if value is None or str(value).strip() in {"", "None"}:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        return None

    def format_manual_score_for_cell(self, score: float | None) -> str:
        if score is None:
            return ""
        return f"{float(score):.3f}".rstrip("0").rstrip(".")

    def restore_manual_score_cell(self, item: QTableWidgetItem, tag: str) -> None:
        score = self.current_manual_score_for_tag(tag)
        self._suppress_item_changed = True
        self.table.blockSignals(True)
        try:
            item.setText(self.format_manual_score_for_cell(score))
            item.setData(SortableTableWidgetItem.SORT_ROLE, score if score is not None else -999999)
        finally:
            self.table.blockSignals(False)
            self._suppress_item_changed = False

    def handle_editable_cell_changed(self, item: QTableWidgetItem) -> None:
        if self._suppress_item_changed or item is None:
            return

        column = item.column()
        if column not in {6, 11}:
            return

        tag = self.tag_from_item(item)
        if not tag:
            return

        if column == 6:
            alias = item.text().strip()
            self.log_message(f"db.set_tag_alias: begin tag={tag!r}")
            self.db.set_tag_alias(tag, alias)
            self.log_message(f"db.set_tag_alias: end tag={tag!r}")

            self.update_current_row_value_for_tag(tag, "alias_tag", alias)
            self._suppress_item_changed = True
            self.table.blockSignals(True)
            try:
                item.setText(alias)
                item.setData(SortableTableWidgetItem.SORT_ROLE, alias)
            finally:
                self.table.blockSignals(False)
                self._suppress_item_changed = False
            self.log_message(f"Alias updated directly for tag={tag!r}. No automatic full reload.")
            return

        raw_text = item.text().strip().replace(",", ".")
        score: float | None
        if raw_text == "":
            score = None
        else:
            try:
                score = float(raw_text)
            except ValueError:
                QMessageBox.warning(
                    self,
                    self.t("tags.invalid_score.title", "Invalid score"),
                    self.t("tags.invalid_score.empty_or_range", "The manual score must be empty or a number between -10 and +10."),
                )
                self.restore_manual_score_cell(item, tag)
                return

            if score < -10.0 or score > 10.0:
                QMessageBox.warning(
                    self,
                    self.t("tags.invalid_score.title", "Invalid score"),
                    self.t("tags.invalid_score.range", "The manual score must be between -10 and +10."),
                )
                self.restore_manual_score_cell(item, tag)
                return

        self.log_message(f"db.set_tag_manual_score: begin tag={tag!r}")
        self.db.set_tag_manual_score(tag, score)
        self.log_message(f"db.set_tag_manual_score: end tag={tag!r}")

        self.update_current_row_value_for_tag(tag, "manual_score", score if score is not None else "")
        self._suppress_item_changed = True
        self.table.blockSignals(True)
        try:
            item.setText(self.format_manual_score_for_cell(score))
            item.setData(SortableTableWidgetItem.SORT_ROLE, score if score is not None else -999999)
        finally:
            self.table.blockSignals(False)
            self._suppress_item_changed = False
        self.log_message(f"Manual score updated locally for tag={tag!r}. No automatic full reload.")

    def update_filename_exclude_cells(self, tags: list[str], excluded: bool) -> None:
        tag_set = set(tags)
        value = self.yes_text() if excluded else ""

        self.table.setUpdatesEnabled(False)
        try:
            for row_index in range(self.table.rowCount()):
                tag_item = self.table.item(row_index, 0)
                tag = self.tag_from_item(tag_item)
                if tag not in tag_set:
                    continue

                item = self.table.item(row_index, 7)
                if item is None:
                    item = QTableWidgetItem()
                    item.setData(Qt.UserRole, tag)
                    self.table.setItem(row_index, 7, item)
                item.setData(Qt.UserRole, tag)
                item.setText(value)
                item.setData(SortableTableWidgetItem.SORT_ROLE, 1 if excluded else 0)
                self.update_current_row_value_for_tag(str(tag), "filename_excluded", 1 if excluded else 0)

            # sqlite3.Row is immutable. The visible table state is therefore the
            # authoritative state until the next manual reload. Yes, GUI state as
            # source of truth is not philosophy, it is damage control.
        finally:
            self.table.setUpdatesEnabled(True)

    def is_filename_excluded_visible(self, tag: str) -> bool:
        """Return the current visible filename-exclude state for a tag."""
        for row_index in range(self.table.rowCount()):
            tag_item = self.table.item(row_index, 0)
            if self.tag_from_item(tag_item) != tag:
                continue

            exclude_item = self.table.item(row_index, 7)
            if exclude_item is None:
                return False

            value = exclude_item.text().strip().lower()
            return value in {"yes", "true", "1", "x"}

        # Fallback for invisible/missing rows. This is mostly defensive.
        for row in self.current_rows:
            try:
                if str(row["tag"]) == tag:
                    return bool(int(row["filename_excluded"] or 0))
            except Exception:
                continue

        return False

    def filename_exclude_state_for_tags(self, tags: list[str]) -> tuple[bool, bool]:
        """Return (any_excluded, all_excluded) for selected tags."""
        states = [self.is_filename_excluded_visible(tag) for tag in tags]
        if not states:
            return False, False
        return any(states), all(states)

    def update_current_row_value(self, row_index: int, key: str, value: Any) -> None:
        """Update current_rows even when sqlite3.Row-style rows are immutable."""
        if row_index < 0 or row_index >= len(self.current_rows):
            return

        try:
            self.current_rows[row_index][key] = value
        except TypeError:
            mutable_row = dict(self.current_rows[row_index])
            mutable_row[key] = value
            self.current_rows[row_index] = mutable_row
        except Exception:
            # Defensive fallback: losing this cache update must not break the GUI.
            pass

    def update_current_row_value_for_tag(self, tag: str, key: str, value: Any) -> None:
        """Update current_rows by tag, independent from visible sort order."""
        for row_index, row in enumerate(self.current_rows):
            try:
                if str(row["tag"]) != tag:
                    continue
            except Exception:
                continue

            self.update_current_row_value(row_index, key, value)
            return

    def set_table_cell_text(
        self,
        row_index: int,
        column: int,
        tag: str,
        text: str,
        align_right: bool = False,
        sort_value: Any | None = None,
    ) -> None:
        item = self.table.item(row_index, column)
        if item is None:
            item = SortableTableWidgetItem()
            self.table.setItem(row_index, column, item)

        item.setData(Qt.UserRole, tag)
        item.setText(text)
        item.setData(SortableTableWidgetItem.SORT_ROLE, text if sort_value is None else sort_value)
        if column in {6, 11}:
            item.setFlags(item.flags() | Qt.ItemIsEditable)
        else:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        if align_right:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def update_alias_in_visible_rows(self, tag: str, alias: str) -> None:
        """Update alias column locally without rebuilding the 5000-row table."""
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self._suppress_item_changed = True
        try:
            for row_index in range(self.table.rowCount()):
                tag_item = self.table.item(row_index, 0)
                if self.tag_from_item(tag_item) != tag:
                    continue

                self.update_current_row_value_for_tag(tag, "alias_tag", alias)
                self.set_table_cell_text(row_index, 6, tag, alias)
                return
        finally:
            self._suppress_item_changed = False
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

    def update_manual_score_in_visible_rows(self, tag: str, score: float | None) -> None:
        """Update manual-score column locally without rebuilding the 5000-row table."""
        score_text = self.format_manual_score_for_cell(score)
        sort_value = score if score is not None else -999999

        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self._suppress_item_changed = True
        try:
            for row_index in range(self.table.rowCount()):
                tag_item = self.table.item(row_index, 0)
                if self.tag_from_item(tag_item) != tag:
                    continue

                self.update_current_row_value_for_tag(tag, "manual_score", score if score is not None else "")
                self.set_table_cell_text(row_index, 11, tag, score_text, align_right=True, sort_value=sort_value)
                return
        finally:
            self._suppress_item_changed = False
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

    def update_scoring_flag_cells(
        self,
        tags: list[str],
        *,
        ignore_category_influence: bool | None = None,
        ignore_recommendation_score: bool | None = None,
        ignore_llm_input: bool | None = None,
    ) -> None:
        tag_set = set(tags)
        flag_columns = {
            "ignore_category_influence": (8, ignore_category_influence),
            "ignore_recommendation_score": (9, ignore_recommendation_score),
            "ignore_llm_input": (10, ignore_llm_input),
        }

        self.table.setUpdatesEnabled(False)
        try:
            for row_index in range(self.table.rowCount()):
                tag_item = self.table.item(row_index, 0)
                tag = self.tag_from_item(tag_item)
                if tag not in tag_set:
                    continue

                for key, (column, value) in flag_columns.items():
                    if value is None:
                        continue
                    self.update_current_row_value_for_tag(str(tag), key, 1 if value else 0)
                    self.set_table_cell_text(row_index, column, str(tag), self.yes_text() if value else "")
                    item = self.table.item(row_index, column)
                    if item is not None:
                        item.setData(SortableTableWidgetItem.SORT_ROLE, 1 if value else 0)
        finally:
            self.table.setUpdatesEnabled(True)

    def set_scoring_flags_for_tags(
        self,
        tags: list[str],
        *,
        ignore_category_influence: bool | None = None,
        ignore_recommendation_score: bool | None = None,
        ignore_llm_input: bool | None = None,
    ) -> None:
        clean_tags = [tag for tag in dict.fromkeys(tags) if str(tag).strip()]
        if not clean_tags:
            return
        if all(value is None for value in (ignore_category_influence, ignore_recommendation_score, ignore_llm_input)):
            return

        for tag in clean_tags:
            self.log_message(f"db.set_tag_scoring_flags: begin tag={tag!r}")
            self.db.set_tag_scoring_flags(
                tag,
                ignore_category_influence=ignore_category_influence,
                ignore_recommendation_score=ignore_recommendation_score,
                ignore_llm_input=ignore_llm_input,
            )
            self.log_message(f"db.set_tag_scoring_flags: end tag={tag!r}")

        self.update_scoring_flag_cells(
            clean_tags,
            ignore_category_influence=ignore_category_influence,
            ignore_recommendation_score=ignore_recommendation_score,
            ignore_llm_input=ignore_llm_input,
        )
        self.log_message(f"Scoring flags updated locally for {len(clean_tags)} Tag(s). No automatic full reload.")

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def open_context_menu(self, position) -> None:  # noqa: ANN001
        tags = self.tags_for_context_position(position)
        if not tags:
            return

        frozen_tags = list(tags)

        menu = QMenu(self)
        self._context_menu = menu

        category_menu = QMenu(self.t("tags.menu.add_to_category", "Add to category"), menu)
        category_names = self.db.list_category_names()

        if not category_names:
            disabled = QAction(self.t("tags.menu.no_categories", "No categories available"), menu)
            disabled.setEnabled(False)
            category_menu.addAction(disabled)

        for category_name in category_names:
            include_action = QAction(f"{category_name} / include", menu)
            include_action.triggered.connect(
                lambda checked=False, c=category_name, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.add_tags_to_category(t, c, "include"),
                    self.t("tags.action.add_to_category", "Add tags to category"),
                )
            )
            category_menu.addAction(include_action)

            exclude_action = QAction(f"{category_name} / exclude", menu)
            exclude_action.triggered.connect(
                lambda checked=False, c=category_name, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.add_tags_to_category(t, c, "exclude"),
                    self.t("tags.action.add_category_exclude", "Add tags as category exclude"),
                )
            )
            category_menu.addAction(exclude_action)

            category_menu.addSeparator()

        menu.addMenu(category_menu)
        menu.addSeparator()

        any_excluded, all_excluded = self.filename_exclude_state_for_tags(frozen_tags)

        if all_excluded:
            remove_exclude_action = QAction(self.t("tags.menu.remove_filename_exclude", "Remove filename exclude"), menu)
            remove_exclude_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.remove_tags_from_filename_exclude(t),
                    self.t("tags.action.remove_filename_exclude", "Remove tags from filename exclude"),
                )
            )
            menu.addAction(remove_exclude_action)
        elif any_excluded:
            add_exclude_action = QAction(self.t("tags.menu.exclude_not_excluded", "Exclude non-excluded tags"), menu)
            add_exclude_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.add_tags_to_filename_exclude([tag for tag in t if not self.is_filename_excluded_visible(tag)]),
                    self.t("tags.action.exclude_not_excluded", "Add non-excluded tags to filename exclude"),
                )
            )
            menu.addAction(add_exclude_action)

            remove_exclude_action = QAction(self.t("tags.menu.remove_excluded_subset", "Remove excluded tags from exclude list"), menu)
            remove_exclude_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.remove_tags_from_filename_exclude([tag for tag in t if self.is_filename_excluded_visible(tag)]),
                    self.t("tags.action.remove_excluded_subset", "Remove excluded tags from filename exclude"),
                )
            )
            menu.addAction(remove_exclude_action)
        else:
            add_exclude_action = QAction(self.t("tags.menu.exclude_from_filename", "Exclude from filename"), menu)
            add_exclude_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.add_tags_to_filename_exclude(t),
                    self.t("tags.action.add_filename_exclude", "Add tags to filename exclude"),
                )
            )
            menu.addAction(add_exclude_action)

        menu.addSeparator()

        scoring_menu = QMenu(self.t("tags.menu.scoring_usage", "Scoring / usage"), menu)

        category_ignore_action = QAction(self.t("tags.menu.ignore_category_hint", "Ignore category hint"), menu)
        category_ignore_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                lambda: self.set_scoring_flags_for_tags(t, ignore_category_influence=True),
                self.t("tags.action.ignore_category_hint", "Ignore category hint for tags"),
            )
        )
        scoring_menu.addAction(category_ignore_action)

        category_use_action = QAction(self.t("tags.menu.use_category_hint", "Use category hint again"), menu)
        category_use_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                lambda: self.set_scoring_flags_for_tags(t, ignore_category_influence=False),
                self.t("tags.action.use_category_hint", "Use category hint for tags again"),
            )
        )
        scoring_menu.addAction(category_use_action)

        scoring_menu.addSeparator()

        recommendation_ignore_action = QAction(self.t("tags.menu.ignore_preselection", "Ignore preselection"), menu)
        recommendation_ignore_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                lambda: self.set_scoring_flags_for_tags(t, ignore_recommendation_score=True),
                self.t("tags.action.ignore_preselection", "Ignore preselection for tags"),
            )
        )
        scoring_menu.addAction(recommendation_ignore_action)

        recommendation_use_action = QAction(self.t("tags.menu.use_preselection", "Use preselection again"), menu)
        recommendation_use_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                lambda: self.set_scoring_flags_for_tags(t, ignore_recommendation_score=False),
                self.t("tags.action.use_preselection", "Use preselection for tags again"),
            )
        )
        scoring_menu.addAction(recommendation_use_action)

        scoring_menu.addSeparator()

        llm_ignore_action = QAction(self.t("tags.menu.ignore_llm_input", "Ignore LLM input"), menu)
        llm_ignore_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                lambda: self.set_scoring_flags_for_tags(t, ignore_llm_input=True),
                self.t("tags.action.ignore_llm_input", "Ignore LLM input for tags"),
            )
        )
        scoring_menu.addAction(llm_ignore_action)

        llm_use_action = QAction(self.t("tags.menu.use_llm_input", "Use LLM input again"), menu)
        llm_use_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                lambda: self.set_scoring_flags_for_tags(t, ignore_llm_input=False),
                self.t("tags.action.use_llm_input", "Use LLM input for tags again"),
            )
        )
        scoring_menu.addAction(llm_use_action)

        scoring_menu.addSeparator()

        all_ignore_action = QAction(self.t("tags.menu.ignore_all_auto_scores", "Ignore all automatic scores"), menu)
        all_ignore_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                lambda: self.set_scoring_flags_for_tags(
                    t,
                    ignore_category_influence=True,
                    ignore_recommendation_score=True,
                    ignore_llm_input=True,
                ),
                self.t("tags.action.ignore_all_auto_scores", "Ignore all automatic scores for tags"),
            )
        )
        scoring_menu.addAction(all_ignore_action)

        all_use_action = QAction(self.t("tags.menu.use_all_auto_scores", "Use all automatic scores again"), menu)
        all_use_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                lambda: self.set_scoring_flags_for_tags(
                    t,
                    ignore_category_influence=False,
                    ignore_recommendation_score=False,
                    ignore_llm_input=False,
                ),
                self.t("tags.action.use_all_auto_scores", "Use all automatic scores for tags again"),
            )
        )
        scoring_menu.addAction(all_use_action)

        menu.addMenu(scoring_menu)
        menu.addSeparator()

        if len(frozen_tags) > 1:
            alias_action = QAction(self.t("tags.menu.set_alias_selection", "Set alias for selection… ({count})", count=len(frozen_tags)), menu)
            alias_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.bulk_set_alias(t),
                    self.t("tags.action.set_alias_selection", "Set alias for selection"),
                )
            )
            menu.addAction(alias_action)

            remove_alias_action = QAction(self.t("tags.menu.remove_alias_selection", "Remove alias for selection… ({count})", count=len(frozen_tags)), menu)
            remove_alias_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.bulk_remove_alias(t),
                    self.t("tags.action.remove_alias_selection", "Remove alias for selection"),
                )
            )
            menu.addAction(remove_alias_action)

        similar_action = QAction(self.t("tags.menu.find_similar", "Find/edit similar tags…"), menu)
        similar_action.triggered.connect(
            lambda checked=False, tag=frozen_tags[0]: self.schedule_safe(
                lambda: self.find_similar_tags_for_bulk_actions(tag),
                self.t("tags.action.find_similar", "Find/edit similar tags"),
            )
        )
        menu.addAction(similar_action)

        # Alias and manual score are edited directly in the table.
        # Scoring/usage flags remain directly toggleable by cell click,
        # but are also available as bulk actions in the context menu.

        menu.addSeparator()

        copy_action = QAction(self.t("tags.menu.copy_tag", "Copy tag"), menu)
        copy_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                lambda: self.copy_tags_to_clipboard(t),
                self.t("tags.action.copy_tags", "Copy tags"),
            )
        )
        menu.addAction(copy_action)

        query_action = QAction(self.t("tags.menu.use_as_search", "Use as search text"), menu)
        query_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                lambda: self.set_search_text(t),
                self.t("tags.action.use_as_search", "Use tags as search text"),
            )
        )
        menu.addAction(query_action)

        menu.aboutToHide.connect(lambda: QTimer.singleShot(250, self.release_context_menu))
        menu.popup(self.table.viewport().mapToGlobal(position))

    def release_context_menu(self) -> None:
        self._context_menu = None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def add_tags_to_category(self, tags: list[str], category_name: str, rule_type: str) -> None:
        if not tags:
            return

        for tag in tags:
            self.log_message(f"db.add_tag_to_category_rule: begin tag={tag!r}, category={category_name!r}, type={rule_type!r}")
            self.db.add_tag_to_category_rule(category_name, tag, rule_type)
            self.log_message(f"db.add_tag_to_category_rule: end tag={tag!r}")

        # Do not show a QMessageBox here. Modal boxes inside context-menu follow-up actions
        # are a wonderful way to summon Qt ghosts.
        self.log_message(f"Category updated: {len(tags)} tag(s) -> {category_name}/{rule_type}")

    def add_tags_to_filename_exclude(self, tags: list[str]) -> None:
        if not tags:
            return

        for tag in tags:
            self.log_message(f"db.add_filename_excluded_tag: begin tag={tag!r}")
            self.db.add_filename_excluded_tag(tag, "manual")
            self.log_message(f"db.add_filename_excluded_tag: end tag={tag!r}")

        self.update_filename_exclude_cells(tags, excluded=True)
        self.log_message(f"Filename exclude set for {len(tags)} Tag(s). No automatic full reload.")

    def remove_tags_from_filename_exclude(self, tags: list[str]) -> None:
        if not tags:
            return

        for tag in tags:
            self.log_message(f"db.remove_filename_excluded_tag: begin tag={tag!r}")
            self.db.remove_filename_excluded_tag(tag)
            self.log_message(f"db.remove_filename_excluded_tag: end tag={tag!r}")

        self.update_filename_exclude_cells(tags, excluded=False)
        self.log_message(f"Filename exclude removed for {len(tags)} Tag(s). No automatic full reload.")

    def add_selected_tags_to_filename_exclude(self) -> None:
        self.safe(lambda: self.add_tags_to_filename_exclude(self.selected_tags()), self.t("tags.action.exclude_selected", "Exclude selected tags"))

    def remove_selected_tags_from_filename_exclude(self) -> None:
        self.safe(lambda: self.remove_tags_from_filename_exclude(self.selected_tags()), self.t("tags.action.remove_selected_exclude", "Remove selected tags from exclude list"))

    def edit_alias_for_item(self, item: QTableWidgetItem) -> None:
        if item is None or item.column() != 6:
            return
        tag = self.tag_from_item(item)
        if tag:
            self.edit_alias(tag)

    def edit_alias(self, tag: str) -> None:
        current_alias = ""
        for row in self.current_rows:
            if str(row["tag"]) == tag:
                current_alias = str(row["alias_tag"] or "")
                break

        text, ok = QInputDialog.getText(
            self,
            self.t("tags.alias.edit_title", "Edit alias"),
            self.t("tags.alias.edit_prompt", "LLM alias for tag '{tag}'\nLeave empty to remove:", tag=tag),
            QLineEdit.Normal,
            current_alias,
        )

        if not ok:
            return

        alias = text.strip()

        self.log_message(f"db.set_tag_alias: begin tag={tag!r}")
        self.db.set_tag_alias(tag, alias)
        self.log_message(f"db.set_tag_alias: end tag={tag!r}")

        self.update_alias_in_visible_rows(tag, alias)
        self.log_message(f"Alias updated locally for tag={tag!r}. No automatic full reload.")

    def current_alias_for_tag(self, tag: str) -> str:
        for row in self.current_rows:
            try:
                if str(row["tag"]) == tag:
                    return str(row["alias_tag"] or "")
            except Exception:
                continue
        return ""

    def format_tag_list_preview(self, tags: list[str], max_items: int = 30) -> str:
        visible = tags[:max_items]
        lines = [f"- {tag}" for tag in visible]
        remaining = len(tags) - len(visible)
        if remaining > 0:
            lines.append(self.t("tags.preview.more", "… and {count} more", count=remaining))
        return "\n".join(lines)

    def confirm_bulk_alias_change(self, title: str, message: str, tags: list[str]) -> bool:
        preview = self.format_tag_list_preview(tags)
        result = QMessageBox.question(
            self,
            title,
            self.t("tags.confirm.affected_tags", "{message}\n\nAffected tags ({count}):\n{preview}", message=message, count=len(tags), preview=preview),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return result == QMessageBox.Yes

    def update_aliases_in_visible_rows(self, tags: list[str], alias: str) -> None:
        tag_set = set(tags)
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self._suppress_item_changed = True
        try:
            for row_index in range(self.table.rowCount()):
                tag_item = self.table.item(row_index, 0)
                tag = self.tag_from_item(tag_item)
                if tag not in tag_set:
                    continue

                self.update_current_row_value_for_tag(str(tag), "alias_tag", alias)
                self.set_table_cell_text(row_index, 6, str(tag), alias)
        finally:
            self._suppress_item_changed = False
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

    def apply_alias_to_tags(self, tags: list[str], alias: str) -> None:
        clean_tags = [tag for tag in dict.fromkeys(tags) if str(tag).strip()]
        if not clean_tags:
            return

        for tag in clean_tags:
            self.log_message(f"db.set_tag_alias: begin tag={tag!r}")
            self.db.set_tag_alias(tag, alias)
            self.log_message(f"db.set_tag_alias: end tag={tag!r}")

        self.update_aliases_in_visible_rows(clean_tags, alias.strip())
        self.log_message(
            f"Alias updated locally for {len(clean_tags)} tag(s). No automatic full reload."
        )

    def bulk_set_alias(self, tags: list[str]) -> None:
        clean_tags = [tag for tag in dict.fromkeys(tags) if str(tag).strip()]
        if not clean_tags:
            return

        current_aliases = sorted({self.current_alias_for_tag(tag) for tag in clean_tags if self.current_alias_for_tag(tag)})
        default_alias = current_aliases[0] if len(current_aliases) == 1 else ""

        text, ok = QInputDialog.getText(
            self,
            self.t("tags.action.set_alias_selection", "Set alias for selection"),
            self.t("tags.alias.selection_prompt", "Alias for {count} selected tags:\nLeave empty to remove the alias.", count=len(clean_tags)),
            QLineEdit.Normal,
            default_alias,
        )
        if not ok:
            return

        alias = text.strip()
        action_text = self.t("tags.alias.action_removed", "removed") if not alias else self.t("tags.alias.action_set_to", "set to '{alias}'", alias=alias)
        if not self.confirm_bulk_alias_change(
            self.t("tags.action.set_alias_selection", "Set alias for selection"),
            f"Der Alias wird {action_text}.",
            clean_tags,
        ):
            return

        self.apply_alias_to_tags(clean_tags, alias)

    def bulk_remove_alias(self, tags: list[str]) -> None:
        clean_tags = [tag for tag in dict.fromkeys(tags) if str(tag).strip()]
        if not clean_tags:
            return

        if not self.confirm_bulk_alias_change(
            self.t("tags.alias.remove_title", "Remove alias"),
            self.t("tags.alias.confirm_remove", "The alias will be removed for these tags."),
            clean_tags,
        ):
            return

        self.apply_alias_to_tags(clean_tags, "")

    def suggest_alias_from_tag(self, tag: str) -> str:
        parts = [part for part in tag.split("_") if part]
        if len(parts) >= 2:
            return parts[-1]
        return tag

    def suggest_pattern_from_tag(self, tag: str) -> str:
        parts = [part for part in tag.split("_") if part]
        if len(parts) >= 2:
            return f"*_{parts[-1]}"
        return f"*{tag}*"

    def describe_bulk_tag_actions(
        self,
        alias: str | None,
        filename_action: str,
        manual_score: float | None,
        scoring_flag_actions: dict[str, bool | None] | None,
        category_name: str | None,
        category_rule_type: str | None,
    ) -> list[str]:
        lines: list[str] = []
        if alias is not None:
            lines.append(self.t("tags.bulk.describe.alias", "Set alias to: {alias}", alias=alias))
        if filename_action == SimilarTagsBulkActionDialog.FILENAME_ADD:
            lines.append(self.t("tags.bulk.describe.filename_add", "Filename exclude: add"))
        elif filename_action == SimilarTagsBulkActionDialog.FILENAME_REMOVE:
            lines.append(self.t("tags.bulk.describe.filename_remove", "Filename exclude: remove"))
        if manual_score is not None:
            lines.append(self.t("tags.bulk.describe.manual_score", "Set manual score to: {score}", score=f"{manual_score:.3f}".rstrip("0").rstrip(".")))
        flag_labels = {
            "ignore_category_influence": self.t("tags.flags.category_hint", "Category hint"),
            "ignore_recommendation_score": self.t("tags.flags.preselection", "Preselection"),
            "ignore_llm_input": self.t("tags.flags.llm_input", "LLM input"),
        }
        for key, value in (scoring_flag_actions or {}).items():
            if value is None:
                continue
            label = flag_labels.get(key, key)
            lines.append(self.t("tags.bulk.describe.flag", "{label}: {action}", label=label, action=self.t("tags.action.ignore", "ignore") if value else self.t("tags.action.use_again", "use again")))
        if category_name and category_rule_type:
            lines.append(self.t("tags.bulk.describe.category_rule", "Add category rule: {category} / {rule}", category=category_name, rule=category_rule_type))
        return lines

    def confirm_bulk_tag_actions(self, title: str, action_lines: list[str], tags: list[str]) -> bool:
        preview = self.format_tag_list_preview(tags)
        action_text = "\n".join(f"- {line}" for line in action_lines)
        result = QMessageBox.question(
            self,
            title,
            self.t("tags.bulk.confirm_actions", "These actions will be applied:\n{actions}\n\nAffected tags ({count}):\n{preview}", actions=action_text, count=len(tags), preview=preview),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return result == QMessageBox.Yes

    def apply_bulk_tag_actions(
        self,
        tags: list[str],
        alias: str | None = None,
        filename_action: str = SimilarTagsBulkActionDialog.FILENAME_NO_CHANGE,
        manual_score: float | None = None,
        scoring_flag_actions: dict[str, bool | None] | None = None,
        category_name: str | None = None,
        category_rule_type: str | None = None,
    ) -> None:
        clean_tags = [tag for tag in dict.fromkeys(tags) if str(tag).strip()]
        if not clean_tags:
            return

        if alias is not None:
            self.apply_alias_to_tags(clean_tags, alias)

        if filename_action == SimilarTagsBulkActionDialog.FILENAME_ADD:
            self.add_tags_to_filename_exclude(clean_tags)
        elif filename_action == SimilarTagsBulkActionDialog.FILENAME_REMOVE:
            self.remove_tags_from_filename_exclude(clean_tags)

        if manual_score is not None:
            for tag in clean_tags:
                self.log_message(f"db.set_tag_manual_score: begin tag={tag!r}")
                self.db.set_tag_manual_score(tag, manual_score)
                self.log_message(f"db.set_tag_manual_score: end tag={tag!r}")
                self.update_manual_score_in_visible_rows(tag, manual_score)
            self.log_message(f"Manual score updated locally for {len(clean_tags)} tag(s). No automatic full reload.")

        if scoring_flag_actions:
            self.set_scoring_flags_for_tags(
                clean_tags,
                ignore_category_influence=scoring_flag_actions.get("ignore_category_influence"),
                ignore_recommendation_score=scoring_flag_actions.get("ignore_recommendation_score"),
                ignore_llm_input=scoring_flag_actions.get("ignore_llm_input"),
            )

        if category_name and category_rule_type:
            self.add_tags_to_category(clean_tags, category_name, category_rule_type)

    def find_similar_tags_for_bulk_actions(self, base_tag: str) -> None:
        default_pattern = self.suggest_pattern_from_tag(base_tag)
        pattern, ok = QInputDialog.getText(
            self,
            self.t("tags.similar.search_title", "Find similar tags"),
            self.t("tags.similar.pattern_prompt", "Search pattern (* and ? allowed):"),
            QLineEdit.Normal,
            default_pattern,
        )
        if not ok:
            return

        pattern = pattern.strip()
        if not pattern:
            return

        self.log_message(f"db.search_tags_by_pattern: begin pattern={pattern!r}")
        rows = self.db.search_tags_by_pattern(
            pattern,
            tag_type=self.selected_tag_type(),
            limit=1000,
        )
        self.log_message(f"db.search_tags_by_pattern: end rows={len(rows)}")

        if not rows:
            QMessageBox.information(self, self.t("tags.similar.search_title", "Find similar tags"), self.t("tags.similar.none_found", "No matching tags found."))
            return

        suggested_alias = self.current_alias_for_tag(base_tag) or self.suggest_alias_from_tag(base_tag)
        dialog = SimilarTagsBulkActionDialog(
            self,
            rows,
            category_names=self.db.list_category_names(),
            suggested_alias=suggested_alias,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        selected = dialog.selected_tags()
        if not selected:
            QMessageBox.information(self, self.t("tags.similar.title", "Edit similar tags"), self.t("tags.similar.none_selected", "No tags selected."))
            return

        if not dialog.has_any_action():
            QMessageBox.information(self, self.t("tags.similar.title", "Edit similar tags"), self.t("tags.similar.no_action", "No action entered."))
            return

        category_name, category_rule_type = dialog.category_action()
        alias = dialog.alias_to_set()
        filename_action = dialog.filename_action()
        manual_score = dialog.manual_score()
        scoring_flag_actions = dialog.scoring_flag_actions()
        action_lines = self.describe_bulk_tag_actions(
            alias,
            filename_action,
            manual_score,
            scoring_flag_actions,
            category_name,
            category_rule_type,
        )

        if not self.confirm_bulk_tag_actions(self.t("tags.similar.title", "Edit similar tags"), action_lines, selected):
            return

        self.apply_bulk_tag_actions(
            selected,
            alias=alias,
            filename_action=filename_action,
            manual_score=manual_score,
            scoring_flag_actions=scoring_flag_actions,
            category_name=category_name,
            category_rule_type=category_rule_type,
        )

    def find_similar_tags_for_alias(self, base_tag: str) -> None:
        # Backwards-compatible wrapper for older signal connections or muscle memory.
        self.find_similar_tags_for_bulk_actions(base_tag)

    def edit_manual_score(self, tag: str) -> None:
        current_value = 0.0
        for row in self.current_rows:
            if str(row["tag"]) == tag and str(row["manual_score"]) not in {"", "None"}:
                try:
                    current_value = float(row["manual_score"])
                except ValueError:
                    current_value = 0.0
                break

        value, ok = QInputDialog.getDouble(
            self,
            self.t("tags.manual_score.title", "Manual score"),
            self.t("tags.manual_score.prompt", "Manual score for '{tag}' (-10 to +10):", tag=tag),
            current_value,
            -10.0,
            10.0,
            3,
        )

        if not ok:
            return

        self.log_message(f"db.set_tag_manual_score: begin tag={tag!r}")
        self.db.set_tag_manual_score(tag, value)
        self.log_message(f"db.set_tag_manual_score: end tag={tag!r}")

        self.update_manual_score_in_visible_rows(tag, value)
        self.log_message(f"Manual score updated locally for tag={tag!r}. No automatic full reload.")

    def copy_tags_to_clipboard(self, tags: list[str]) -> None:
        QGuiApplication.clipboard().setText(" ".join(tags))

    def set_search_text(self, tags: list[str]) -> None:
        self.search_edit.setText(" ".join(tags))
