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
    QComboBox,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
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


TAG_TYPE_LABELS = {
    "all": "Alle",
    "copyright": "Copyright",
    "character": "Character",
    "artist": "Artist",
    "general": "General",
    "meta": "Meta",
}


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

        work_dir = Path(str(config.get("work_dir", ".")))
        self.log_dir = work_dir / "logs"
        self.log_path = self.log_dir / "gui_error.log"
        self.tag_log_path = self.log_dir / "tag_tab_error.log"
        self.hang_log_path = self.log_dir / "tag_tab_hang_dump.log"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.enable_fault_handler()

        self.main_layout = QVBoxLayout(self)

        self.toolbar_layout = QHBoxLayout()

        self.toolbar_layout.addWidget(QLabel("Suche:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Tag suchen...")
        self.search_edit.returnPressed.connect(lambda: self.safe(self.reload_tags, "Tags neu laden"))
        self.toolbar_layout.addWidget(self.search_edit, stretch=1)

        self.toolbar_layout.addWidget(QLabel("Typ:"))
        self.type_filter = QComboBox()
        for tag_type, label in TAG_TYPE_LABELS.items():
            self.type_filter.addItem(label, tag_type)
        self.type_filter.currentIndexChanged.connect(lambda *_: self.safe(self.reload_tags, "Tags neu laden"))
        self.toolbar_layout.addWidget(self.type_filter)

        self.reload_button = QPushButton("Neu laden")
        self.reload_button.clicked.connect(lambda *_: self.safe(self.reload_tags, "Tags neu laden"))
        self.toolbar_layout.addWidget(self.reload_button)

        self.main_layout.addLayout(self.toolbar_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels(
            [
                "Tag",
                "Typ",
                "Posts",
                "Offen",
                "Gespeichert",
                "Abgelehnt",
                "Alias",
                "Filename-Exclude",
                "Manueller Score",
                "Berechneter Score",
                "Ø Sterne",
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(
            lambda pos: self.safe(lambda: self.open_context_menu(pos), "Kontextmenü öffnen")
        )
        self.table.itemDoubleClicked.connect(
            lambda item: self.safe(lambda: self.edit_alias_for_item(item), "Alias per Doppelklick bearbeiten")
        )

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 11):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        self.main_layout.addWidget(self.table)

        self.hint_label = QLabel(
            f"Rechtsklick auf Tags: zu Kategorie hinzufügen, Filename-Exclude setzen, Alias/Score bearbeiten. "
            f"Doppelklick: Alias bearbeiten. Fehlerlog: {self.tag_log_path}"
        )
        self.hint_label.setWordWrap(True)
        self.main_layout.addWidget(self.hint_label)

        self.safe(self.reload_tags, "Initiales Laden der Tags")

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

    def safe(self, action: Callable[[], None], title: str = "Tag-Tab-Aktion") -> None:
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
                "Fehler im Tag-Tab",
                f"{title} ist fehlgeschlagen:\n\n{exc}\n\nLog: {self.tag_log_path}",
            )
        finally:
            watchdog_done.set()

    def schedule_safe(self, action: Callable[[], None], title: str = "Tag-Tab-Aktion") -> None:
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
            self.safe(self.reload_tags, "Tags verzögert neu laden")

        QTimer.singleShot(50, do_reload)

    def reload_tags(self) -> None:
        self.log_message("fetch_tag_overview: begin")
        rows = self.db.fetch_tag_overview(
            search_text=self.search_text(),
            tag_type=self.selected_tag_type(),
            limit=5000,
        )
        self.log_message(f"fetch_tag_overview: end, rows={len(rows)}")

        self.current_rows = rows

        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.clearContents()
            self.table.setRowCount(len(self.current_rows))

            for row_index, row in enumerate(self.current_rows):
                values = [
                    row["tag"],
                    row["tag_type"],
                    row["post_count"],
                    row["open_count"],
                    row["saved_count"],
                    row["rejected_count"],
                    row["alias_tag"] or "",
                    "ja" if int(row["filename_excluded"] or 0) else "",
                    row["manual_score"],
                    row["computed_score"],
                    row["average_rating"],
                ]

                for column, value in enumerate(values):
                    item = QTableWidgetItem("" if value is None else str(value))
                    item.setData(Qt.UserRole, row["tag"])
                    if column in {2, 3, 4, 5, 8, 9, 10}:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.table.setItem(row_index, column, item)
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

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

    def update_filename_exclude_cells(self, tags: list[str], excluded: bool) -> None:
        tag_set = set(tags)
        value = "ja" if excluded else ""

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
            return value in {"ja", "yes", "true", "1", "x"}

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

    def set_table_cell_text(self, row_index: int, column: int, tag: str, text: str, align_right: bool = False) -> None:
        item = self.table.item(row_index, column)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row_index, column, item)

        item.setData(Qt.UserRole, tag)
        item.setText(text)
        if align_right:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def update_alias_in_visible_rows(self, tag: str, alias: str) -> None:
        """Update alias column locally without rebuilding the 5000-row table."""
        self.table.setUpdatesEnabled(False)
        try:
            for row_index in range(self.table.rowCount()):
                tag_item = self.table.item(row_index, 0)
                if self.tag_from_item(tag_item) != tag:
                    continue

                self.update_current_row_value(row_index, "alias_tag", alias)
                self.set_table_cell_text(row_index, 6, tag, alias)
                return
        finally:
            self.table.setUpdatesEnabled(True)

    def update_manual_score_in_visible_rows(self, tag: str, score: float) -> None:
        """Update manual-score column locally without rebuilding the 5000-row table."""
        score_text = f"{score:.3f}".rstrip("0").rstrip(".")

        self.table.setUpdatesEnabled(False)
        try:
            for row_index in range(self.table.rowCount()):
                tag_item = self.table.item(row_index, 0)
                if self.tag_from_item(tag_item) != tag:
                    continue

                self.update_current_row_value(row_index, "manual_score", score)
                self.set_table_cell_text(row_index, 8, tag, score_text, align_right=True)
                return
        finally:
            self.table.setUpdatesEnabled(True)

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

        category_menu = QMenu("Zu Kategorie hinzufügen", menu)
        category_names = self.db.list_category_names()

        if not category_names:
            disabled = QAction("Keine Kategorien vorhanden", menu)
            disabled.setEnabled(False)
            category_menu.addAction(disabled)

        for category_name in category_names:
            include_action = QAction(f"{category_name} / include", menu)
            include_action.triggered.connect(
                lambda checked=False, c=category_name, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.add_tags_to_category(t, c, "include"),
                    "Tags zu Kategorie hinzufügen",
                )
            )
            category_menu.addAction(include_action)

            exclude_action = QAction(f"{category_name} / exclude", menu)
            exclude_action.triggered.connect(
                lambda checked=False, c=category_name, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.add_tags_to_category(t, c, "exclude"),
                    "Tags als Kategorie-Ausschluss hinzufügen",
                )
            )
            category_menu.addAction(exclude_action)

            category_menu.addSeparator()

        menu.addMenu(category_menu)
        menu.addSeparator()

        any_excluded, all_excluded = self.filename_exclude_state_for_tags(frozen_tags)

        if all_excluded:
            remove_exclude_action = QAction("Filename-Ausschluss entfernen", menu)
            remove_exclude_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.remove_tags_from_filename_exclude(t),
                    "Tags vom Filename-Ausschluss entfernen",
                )
            )
            menu.addAction(remove_exclude_action)
        elif any_excluded:
            add_exclude_action = QAction("Nicht ausgeschlossene Tags ausschließen", menu)
            add_exclude_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.add_tags_to_filename_exclude([tag for tag in t if not self.is_filename_excluded_visible(tag)]),
                    "Nicht ausgeschlossene Tags zum Filename-Ausschluss hinzufügen",
                )
            )
            menu.addAction(add_exclude_action)

            remove_exclude_action = QAction("Ausgeschlossene Tags aus Ausschluss entfernen", menu)
            remove_exclude_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.remove_tags_from_filename_exclude([tag for tag in t if self.is_filename_excluded_visible(tag)]),
                    "Ausgeschlossene Tags vom Filename-Ausschluss entfernen",
                )
            )
            menu.addAction(remove_exclude_action)
        else:
            add_exclude_action = QAction("Vom Dateinamen ausschließen", menu)
            add_exclude_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                    lambda: self.add_tags_to_filename_exclude(t),
                    "Tags zum Filename-Ausschluss hinzufügen",
                )
            )
            menu.addAction(add_exclude_action)

        menu.addSeparator()

        alias_action = QAction("Alias bearbeiten", menu)
        alias_action.triggered.connect(
            lambda checked=False, tag=frozen_tags[0]: self.schedule_safe(
                lambda: self.edit_alias(tag),
                "Alias bearbeiten",
            )
        )
        menu.addAction(alias_action)

        score_action = QAction("Manuellen Score bearbeiten", menu)
        score_action.triggered.connect(
            lambda checked=False, tag=frozen_tags[0]: self.schedule_safe(
                lambda: self.edit_manual_score(tag),
                "Manuellen Score bearbeiten",
            )
        )
        menu.addAction(score_action)

        menu.addSeparator()

        copy_action = QAction("Tag kopieren", menu)
        copy_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                lambda: self.copy_tags_to_clipboard(t),
                "Tags kopieren",
            )
        )
        menu.addAction(copy_action)

        query_action = QAction("Als Suchtext übernehmen", menu)
        query_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): self.schedule_safe(
                lambda: self.set_search_text(t),
                "Tags als Suchtext übernehmen",
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
        self.log_message(f"Kategorie aktualisiert: {len(tags)} Tag(s) -> {category_name}/{rule_type}")

    def add_tags_to_filename_exclude(self, tags: list[str]) -> None:
        if not tags:
            return

        for tag in tags:
            self.log_message(f"db.add_filename_excluded_tag: begin tag={tag!r}")
            self.db.add_filename_excluded_tag(tag, "manual")
            self.log_message(f"db.add_filename_excluded_tag: end tag={tag!r}")

        self.update_filename_exclude_cells(tags, excluded=True)
        self.log_message(f"Filename-Exclude gesetzt fuer {len(tags)} Tag(s). Kein automatischer Voll-Reload.")

    def remove_tags_from_filename_exclude(self, tags: list[str]) -> None:
        if not tags:
            return

        for tag in tags:
            self.log_message(f"db.remove_filename_excluded_tag: begin tag={tag!r}")
            self.db.remove_filename_excluded_tag(tag)
            self.log_message(f"db.remove_filename_excluded_tag: end tag={tag!r}")

        self.update_filename_exclude_cells(tags, excluded=False)
        self.log_message(f"Filename-Exclude entfernt fuer {len(tags)} Tag(s). Kein automatischer Voll-Reload.")

    def add_selected_tags_to_filename_exclude(self) -> None:
        self.safe(lambda: self.add_tags_to_filename_exclude(self.selected_tags()), "Ausgewählte Tags ausschließen")

    def remove_selected_tags_from_filename_exclude(self) -> None:
        self.safe(lambda: self.remove_tags_from_filename_exclude(self.selected_tags()), "Ausgewählte Tags aus Ausschluss entfernen")

    def edit_alias_for_item(self, item: QTableWidgetItem) -> None:
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
            "Alias bearbeiten",
            f"LLM-Alias für Tag '{tag}'\nLeer lassen zum Entfernen:",
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
        self.log_message(f"Alias lokal aktualisiert fuer tag={tag!r}. Kein automatischer Voll-Reload.")

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
            "Manueller Score",
            f"Manueller Score für '{tag}' (-10 bis +10):",
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
        self.log_message(f"Manueller Score lokal aktualisiert fuer tag={tag!r}. Kein automatischer Voll-Reload.")

    def copy_tags_to_clipboard(self, tags: list[str]) -> None:
        QGuiApplication.clipboard().setText(" ".join(tags))

    def set_search_text(self, tags: list[str]) -> None:
        self.search_edit.setText(" ".join(tags))
