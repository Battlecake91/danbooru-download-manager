from __future__ import annotations

import copy
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)

from app.core.database import Database
from app.i18n.i18n import tr
from app.services.existing_file_import_service import (
    ExistingFileImportCandidate,
    ExistingFileImportProgress,
    ExistingFileImportService,
    ExistingFileScanResult,
)


class ExistingFileImportWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(object)
    log = Signal(str)

    def __init__(
        self,
        config: dict[str, Any],
        mode: str,
        folder: str,
        category_id: int,
        recursive: bool,
        rename_after_import: bool,
        old_category_id: int | None = None,
        update_existing: bool = True,
        fetch_thumbnails: bool = False,
        post_ids: list[int] | None = None,
        candidate_paths: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.mode = mode
        self.folder = folder
        self.category_id = int(category_id)
        self.recursive = bool(recursive)
        self.rename_after_import = bool(rename_after_import)
        self.old_category_id = int(old_category_id) if old_category_id is not None else None
        self.update_existing = bool(update_existing)
        self.fetch_thumbnails = bool(fetch_thumbnails)
        self.post_ids = list(post_ids or [])
        self.candidate_paths = list(candidate_paths or [])

    @Slot()
    def run(self) -> None:
        worker_db: Database | None = None
        try:
            database_file = Path(str(self.config["database_file"]))
            worker_db = Database(database_file)
            worker_db.connect()
            worker_db.initialize_schema()

            service = ExistingFileImportService(self.config, worker_db, progress_callback=self.progress.emit)
            if self.mode == "scan":
                result = service.scan_folder(self.folder, recursive=self.recursive)
            elif self.mode == "import":
                self.log.emit(tr("import.log.import_started", "Existing file import started.", config=self.config))
                result = service.import_folder(
                    self.folder,
                    self.category_id,
                    recursive=self.recursive,
                    rename_after_import=self.rename_after_import,
                    update_existing=self.update_existing,
                    fetch_thumbnails=self.fetch_thumbnails,
                    candidate_paths=self.candidate_paths or None,
                )
            elif self.mode == "repair":
                if self.old_category_id is None:
                    raise RuntimeError(tr("import.error.no_old_category_for_repair", "No old category set for repair.", config=self.config))
                self.log.emit(tr("import.log.repair_started", "Import category repair started.", config=self.config))
                result = service.repair_imported_category(
                    self.folder,
                    self.old_category_id,
                    self.category_id,
                    recursive=self.recursive,
                    rename_after_repair=self.rename_after_import,
                )
            elif self.mode == "rename":
                self.log.emit(tr("import.log.rename_started", "Renaming saved files using the current filename schema started.", config=self.config))
                result = service.rename_saved_files_for_category(self.category_id, self.post_ids or None)
            else:
                raise RuntimeError(tr("import.error.unknown_mode", "Unknown import mode: {mode}", config=self.config, mode=self.mode))

            self.finished.emit(result)
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            if worker_db is not None:
                try:
                    worker_db.close()
                except Exception:
                    pass


class ImportTab(QWidget):
    import_finished = Signal()

    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()
        self.config = config
        self.db = db
        self.thread: QThread | None = None
        self.worker: ExistingFileImportWorker | None = None
        self.last_imported_post_ids: list[int] = []
        self.scan_candidates: list[ExistingFileImportCandidate] = []

        self.main_layout = QVBoxLayout(self)

        self.info_label = QLabel(tr("import.info", config=self.config))
        self.info_label.setWordWrap(True)
        self.main_layout.addWidget(self.info_label)

        self.warning_label = QLabel(tr("import.warning_filename_id_md5", config=self.config))
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet(
            "QLabel { background: #fff4c2; color: #4f3600; border: 1px solid #d6a800; "
            "border-radius: 6px; padding: 8px; font-weight: bold; }"
        )
        self.main_layout.addWidget(self.warning_label)

        self.import_group = QGroupBox(tr("import.group.source", config=self.config))
        self.import_layout = QFormLayout(self.import_group)

        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText(tr("import.folder.placeholder", config=self.config))
        folder_row.addWidget(self.folder_edit, stretch=1)
        self.browse_button = QPushButton(tr("import.button.choose_folder", config=self.config))
        self.browse_button.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.browse_button)
        self.import_layout.addRow(tr("import.label.folder", config=self.config), folder_row)

        self.category_combo = QComboBox()
        self.category_combo.setMinimumWidth(260)
        self.import_layout.addRow(tr("import.label.category", config=self.config), self.category_combo)

        self.recursive_checkbox = QCheckBox(tr("import.checkbox.recursive", config=self.config))
        self.recursive_checkbox.setChecked(True)
        self.import_layout.addRow(tr("import.label.scan", config=self.config), self.recursive_checkbox)

        self.rename_after_import_checkbox = QCheckBox(tr("import.checkbox.rename_after_import", config=self.config))
        self.rename_after_import_checkbox.setChecked(False)
        self.import_layout.addRow(tr("import.label.rename", config=self.config), self.rename_after_import_checkbox)

        self.update_existing_checkbox = QCheckBox(tr("import.checkbox.update_existing", config=self.config))
        self.update_existing_checkbox.setChecked(True)
        self.import_layout.addRow(tr("import.label.existing_posts", config=self.config), self.update_existing_checkbox)

        self.fetch_thumbnails_checkbox = QCheckBox(tr("import.checkbox.fetch_thumbnails", config=self.config))
        self.fetch_thumbnails_checkbox.setChecked(False)
        self.import_layout.addRow(tr("import.label.thumbnails", config=self.config), self.fetch_thumbnails_checkbox)

        self.rename_last_import_checkbox = QCheckBox(tr("import.checkbox.rename_last_import_only", config=self.config))
        self.rename_last_import_checkbox.setChecked(True)
        self.import_layout.addRow(tr("import.label.rename_scope", config=self.config), self.rename_last_import_checkbox)

        self.repair_group = QGroupBox(tr("import.group.repair", config=self.config))
        self.repair_layout = QFormLayout(self.repair_group)

        self.old_category_combo = QComboBox()
        self.old_category_combo.setMinimumWidth(260)
        self.repair_layout.addRow(tr("import.label.wrongly_imported_as", config=self.config), self.old_category_combo)

        self.repair_hint_label = QLabel(tr("import.repair_hint", config=self.config))
        self.repair_hint_label.setWordWrap(True)
        self.repair_layout.addRow(tr("import.label.note", config=self.config), self.repair_hint_label)

        self.main_layout.addWidget(self.import_group)
        self.main_layout.addWidget(self.repair_group)

        button_row = QHBoxLayout()
        self.scan_button = QPushButton(tr("import.button.scan_folder", "Scan folder", config=self.config))
        self.scan_button.clicked.connect(self.start_scan)
        button_row.addWidget(self.scan_button)

        self.import_button = QPushButton(tr("import.button.import_selected", "Import selected", config=self.config))
        self.import_button.clicked.connect(self.start_import)
        self.import_button.setEnabled(False)
        button_row.addWidget(self.import_button)

        self.repair_button = QPushButton(tr("import.button.repair_category", config=self.config))
        self.repair_button.clicked.connect(self.start_repair_category)
        button_row.addWidget(self.repair_button)

        self.rename_category_button = QPushButton(tr("import.button.rename_category", config=self.config))
        self.rename_category_button.clicked.connect(self.start_rename_category)
        button_row.addWidget(self.rename_category_button)

        self.refresh_categories_button = QPushButton(tr("import.button.reload_categories", config=self.config))
        self.refresh_categories_button.clicked.connect(self.load_categories)
        button_row.addWidget(self.refresh_categories_button)
        button_row.addStretch(1)
        self.main_layout.addLayout(button_row)

        review_row = QHBoxLayout()
        review_row.addWidget(QLabel(tr("import.label.confidence_filter", "Show", config=self.config)))
        self.confidence_high_checkbox = QCheckBox(
            tr("import.filter.high", "High confidence", config=self.config)
        )
        self.confidence_questionable_checkbox = QCheckBox(
            tr("import.filter.questionable", "Questionable", config=self.config)
        )
        self.confidence_mismatch_checkbox = QCheckBox(
            tr("import.filter.mismatch", "Wrong ID / mismatch", config=self.config)
        )
        for checkbox in (
            self.confidence_high_checkbox,
            self.confidence_questionable_checkbox,
            self.confidence_mismatch_checkbox,
        ):
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self.apply_candidate_filter)
            review_row.addWidget(checkbox)
        review_row.addStretch(1)
        self.open_local_button = QPushButton(tr("import.button.open_local", "Open local file", config=self.config))
        self.open_local_button.clicked.connect(self.open_selected_local_file)
        self.open_local_button.setEnabled(False)
        review_row.addWidget(self.open_local_button)
        self.open_remote_button = QPushButton(tr("import.button.open_remote", "Open remote image", config=self.config))
        self.open_remote_button.clicked.connect(self.open_selected_remote_image)
        self.open_remote_button.setEnabled(False)
        review_row.addWidget(self.open_remote_button)
        self.main_layout.addLayout(review_row)

        self.candidate_table = QTableWidget(0, 8)
        self.candidate_table.setHorizontalHeaderLabels([
            tr("import.table.import", "Import", config=self.config),
            tr("import.table.confidence", "Confidence", config=self.config),
            tr("import.table.post_id", "Post ID", config=self.config),
            tr("import.table.filename", "Local file", config=self.config),
            tr("import.table.tags", "Filename tags", config=self.config),
            tr("import.table.resolution", "Resolution", config=self.config),
            tr("import.table.reason", "Reason", config=self.config),
            tr("import.table.path", "Path", config=self.config),
        ])
        self.candidate_table.setAlternatingRowColors(True)
        self.candidate_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.candidate_table.setSortingEnabled(True)
        self.candidate_table.itemSelectionChanged.connect(self.update_candidate_open_buttons)
        self.candidate_table.itemDoubleClicked.connect(self.open_candidate_from_item)
        header = self.candidate_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        self.candidate_table.setMinimumHeight(260)
        self.main_layout.addWidget(self.candidate_table, stretch=1)

        self.progress_label = QLabel(tr("common.ready", "Ready.", config=self.config))
        self.progress_label.setWordWrap(True)
        self.main_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.main_layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(120)
        self.main_layout.addWidget(self.log_text)

        self.load_categories()

    def choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, tr("import.dialog.choose_folder.title", config=self.config), self.folder_edit.text().strip() or str(Path.home()))
        if selected:
            self.folder_edit.setText(selected)
            self.clear_scan_results()

    def load_categories(self) -> None:
        current_id = self.current_category_id()
        old_current_id = self.old_category_id() if hasattr(self, "old_category_combo") else None
        self.category_combo.blockSignals(True)
        if hasattr(self, "old_category_combo"):
            self.old_category_combo.blockSignals(True)
        try:
            self.category_combo.clear()
            if hasattr(self, "old_category_combo"):
                self.old_category_combo.clear()
            for row in self.db.list_categories_full():
                name = str(row["name"])
                category_id = int(row["id"])
                self.category_combo.addItem(name, category_id)
                if hasattr(self, "old_category_combo"):
                    self.old_category_combo.addItem(name, category_id)
            if current_id is not None:
                index = self.category_combo.findData(current_id)
                if index >= 0:
                    self.category_combo.setCurrentIndex(index)
            if old_current_id is not None and hasattr(self, "old_category_combo"):
                index = self.old_category_combo.findData(old_current_id)
                if index >= 0:
                    self.old_category_combo.setCurrentIndex(index)
        finally:
            self.category_combo.blockSignals(False)
            if hasattr(self, "old_category_combo"):
                self.old_category_combo.blockSignals(False)

    def current_category_id(self) -> int | None:
        value = self.category_combo.currentData()
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def old_category_id(self) -> int | None:
        if not hasattr(self, "old_category_combo"):
            return None
        value = self.old_category_combo.currentData()
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def set_controls_enabled(self, enabled: bool) -> None:
        self.folder_edit.setEnabled(enabled)
        self.browse_button.setEnabled(enabled)
        self.category_combo.setEnabled(enabled)
        self.recursive_checkbox.setEnabled(enabled)
        self.rename_after_import_checkbox.setEnabled(enabled)
        self.update_existing_checkbox.setEnabled(enabled)
        self.fetch_thumbnails_checkbox.setEnabled(enabled)
        self.rename_last_import_checkbox.setEnabled(enabled)
        self.old_category_combo.setEnabled(enabled)
        self.repair_button.setEnabled(enabled)
        self.scan_button.setEnabled(enabled)
        self.import_button.setEnabled(enabled and bool(self.scan_candidates))
        self.confidence_high_checkbox.setEnabled(enabled)
        self.confidence_questionable_checkbox.setEnabled(enabled)
        self.confidence_mismatch_checkbox.setEnabled(enabled)
        self.candidate_table.setEnabled(enabled)
        self.update_candidate_open_buttons()
        self.rename_category_button.setEnabled(enabled)
        self.refresh_categories_button.setEnabled(enabled)

    def start_scan(self) -> None:
        folder = self.folder_edit.text().strip()
        if not folder or not Path(folder).expanduser().is_dir():
            QMessageBox.warning(self, tr("import.title", config=self.config), tr("import.warning.folder_not_found", config=self.config, folder=folder))
            return
        category_id = self.current_category_id() or 0
        self.clear_scan_results()
        self.start_worker(
            mode="scan", folder=folder, category_id=category_id,
            recursive=self.recursive_checkbox.isChecked(), rename_after_import=False,
        )

    def selected_candidate_paths(self) -> list[str]:
        paths: list[str] = []
        for row in range(self.candidate_table.rowCount()):
            check_item = self.candidate_table.item(row, 0)
            path_item = self.candidate_table.item(row, 7)
            if check_item and path_item and check_item.checkState() == Qt.Checked:
                paths.append(path_item.data(Qt.UserRole) or path_item.text())
        return paths

    def start_import(self) -> None:
        folder = self.folder_edit.text().strip()
        if not folder or not Path(folder).expanduser().is_dir():
            QMessageBox.warning(self, tr("import.title", config=self.config), tr("import.warning.folder_not_found", config=self.config, folder=folder))
            return
        candidate_paths = self.selected_candidate_paths()
        if not candidate_paths:
            QMessageBox.information(self, tr("import.title", config=self.config), tr("import.info.no_candidates_selected", "No import candidates selected.", config=self.config))
            return
        category_id = self.current_category_id()
        if category_id is None:
            QMessageBox.warning(self, tr("import.title", config=self.config), tr("import.warning.select_category", config=self.config))
            return
        self.start_worker(
            mode="import", folder=folder, category_id=category_id,
            recursive=self.recursive_checkbox.isChecked(),
            rename_after_import=self.rename_after_import_checkbox.isChecked(),
            update_existing=self.update_existing_checkbox.isChecked(),
            fetch_thumbnails=self.fetch_thumbnails_checkbox.isChecked(),
            candidate_paths=candidate_paths,
        )

    def start_repair_category(self) -> None:
        folder = self.folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, tr("import.repair_title", config=self.config), tr("import.warning.select_affected_folder", config=self.config))
            return
        if not Path(folder).expanduser().is_dir():
            QMessageBox.warning(self, tr("import.repair_title", config=self.config), tr("import.warning.folder_not_found", config=self.config, folder=folder))
            return

        old_category_id = self.old_category_id()
        new_category_id = self.current_category_id()
        if old_category_id is None or new_category_id is None:
            QMessageBox.warning(self, tr("import.repair_title", config=self.config), tr("import.warning.select_old_new_category", config=self.config))
            return
        if old_category_id == new_category_id:
            QMessageBox.warning(self, tr("import.repair_title", config=self.config), tr("import.warning.old_new_category_same", config=self.config))
            return

        old_name = self.old_category_combo.currentText()
        new_name = self.category_combo.currentText()
        if QMessageBox.question(
            self,
            tr("import.confirm_repair.title", config=self.config),
            tr("import.confirm_repair.message", config=self.config, folder=folder, old_name=old_name, new_name=new_name),
        ) != QMessageBox.Yes:
            return

        self.start_worker(
            mode="repair",
            folder=folder,
            category_id=new_category_id,
            recursive=self.recursive_checkbox.isChecked(),
            rename_after_import=self.rename_after_import_checkbox.isChecked(),
            old_category_id=old_category_id,
            update_existing=True,
        )

    def start_rename_category(self) -> None:
        category_id = self.current_category_id()
        if category_id is None:
            QMessageBox.warning(self, tr("import.rename_title", config=self.config), tr("import.warning.select_category", config=self.config))
            return

        category_name = self.category_combo.currentText()
        rename_last_only = self.rename_last_import_checkbox.isChecked()
        post_ids = self.last_imported_post_ids if rename_last_only else []
        if rename_last_only and not post_ids:
            QMessageBox.information(self, tr("import.rename_title", config=self.config), tr("import.info.no_last_import", config=self.config))
            return
        message_key = "import.confirm_rename.last_import_message" if rename_last_only else "import.confirm_rename.message"
        if QMessageBox.question(
            self,
            tr("import.confirm_rename.title", config=self.config),
            tr(message_key, config=self.config, category_name=category_name, count=len(post_ids)),
        ) != QMessageBox.Yes:
            return

        self.start_worker(
            mode="rename",
            folder="",
            category_id=category_id,
            recursive=False,
            rename_after_import=False,
            post_ids=post_ids,
        )

    def start_worker(
        self,
        *,
        mode: str,
        folder: str,
        category_id: int,
        recursive: bool,
        rename_after_import: bool,
        old_category_id: int | None = None,
        update_existing: bool = True,
        fetch_thumbnails: bool = False,
        post_ids: list[int] | None = None,
        candidate_paths: list[str] | None = None,
    ) -> None:
        if self.thread is not None:
            QMessageBox.information(self, tr("import.importer_title", config=self.config), tr("import.info.already_running", config=self.config))
            return

        self.set_controls_enabled(False)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.progress_label.setText(tr("common.starting", "Starting…", config=self.config))
        self.log_text.append(tr("import.log.action_starting", config=self.config))

        worker_config = copy.deepcopy(self.config)
        self.thread = QThread(self)
        self.worker = ExistingFileImportWorker(
            worker_config,
            mode=mode,
            folder=folder,
            category_id=category_id,
            recursive=recursive,
            rename_after_import=rename_after_import,
            old_category_id=old_category_id,
            update_existing=update_existing,
            fetch_thumbnails=fetch_thumbnails,
            post_ids=post_ids,
            candidate_paths=candidate_paths,
        )
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.log.connect(self.log_text.append)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.cleanup_thread)
        self.thread.start()

    def on_progress(self, progress: object) -> None:
        if not isinstance(progress, ExistingFileImportProgress):
            return

        total = max(0, int(progress.total or 0))
        current = max(0, int(progress.current or 0))
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(min(current, total))
            self.progress_bar.setFormat(f"{current}/{total}")
        else:
            self.progress_bar.setRange(0, 0)

        self.progress_label.setText(
            tr(
                "import.progress.status",
                config=self.config,
                current=current,
                total=total,
                imported=progress.imported,
                updated=progress.updated,
                repaired=progress.repaired,
                renamed=progress.renamed,
                skipped_existing=progress.skipped_existing,
                skipped_no_md5=progress.skipped_no_md5,
                skipped_tag_mismatch=progress.skipped_tag_mismatch,
                cached_thumbnails=progress.cached_thumbnails,
                not_found=progress.not_found,
                errors=progress.errors,
            )
        )
        if progress.message:
            self.log_text.append(progress.message)

    def on_finished(self, result: object) -> None:
        self.set_controls_enabled(True)
        if isinstance(result, ExistingFileScanResult):
            self.scan_candidates = list(result.candidates)
            self.populate_candidate_table()
            self.progress_label.setText(tr("import.scan.summary", "Scan complete: {count} files", config=self.config, count=len(self.scan_candidates)))
            self.import_button.setEnabled(bool(self.scan_candidates))
            return
        imported_ids = list(getattr(result, "imported_post_ids", []) or [])
        if imported_ids:
            self.last_imported_post_ids = imported_ids
        self.progress_bar.setVisible(True)
        summary = tr(
            "import.summary",
            config=self.config,
            category=getattr(result, "category_name", ""),
            old_category=getattr(result, "old_category_name", ""),
            scanned=getattr(result, "scanned_files", 0),
            imported=getattr(result, "imported_posts", 0),
            updated=getattr(result, "updated_posts", 0),
            repaired=getattr(result, "repaired_posts", 0),
            renamed=getattr(result, "renamed_files", 0),
            skipped_rename=getattr(result, "skipped_rename", 0),
            skipped_existing=getattr(result, "skipped_existing", 0),
            skipped_no_md5=getattr(result, "skipped_no_md5", 0),
            not_found=getattr(result, "not_found", 0),
            errors=getattr(result, "errors", 0),
            skipped_tag_mismatch=getattr(result, "skipped_tag_mismatch", 0),
            cached_thumbnails=getattr(result, "cached_thumbnails", 0),
        )
        self.log_text.append(summary)
        self.progress_label.setText(summary.replace("\n", " | "))
        self.import_finished.emit()

    def clear_scan_results(self) -> None:
        self.scan_candidates = []
        if hasattr(self, "candidate_table"):
            self.candidate_table.setRowCount(0)
        if hasattr(self, "import_button"):
            self.import_button.setEnabled(False)

    def populate_candidate_table(self) -> None:
        self.candidate_table.setSortingEnabled(False)
        self.candidate_table.setRowCount(0)
        colors = {
            "high": QColor(211, 245, 218),
            "questionable": QColor(255, 243, 180),
            "mismatch": QColor(255, 205, 205),
        }
        labels = {
            "high": tr("import.confidence.high", "High", config=self.config),
            "questionable": tr("import.confidence.questionable", "Questionable", config=self.config),
            "mismatch": tr("import.confidence.mismatch", "Mismatch", config=self.config),
        }
        for candidate in self.scan_candidates:
            row = self.candidate_table.rowCount()
            self.candidate_table.insertRow(row)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            check.setCheckState(Qt.Checked if candidate.importable else Qt.Unchecked)
            confidence = QTableWidgetItem(labels.get(candidate.confidence, candidate.confidence))
            confidence.setData(Qt.UserRole, candidate.confidence)
            post_id = QTableWidgetItem(str(candidate.post_id or ""))
            filename = QTableWidgetItem(candidate.filename)
            tags_text = ", ".join(candidate.matched_tags)
            if candidate.missing_tags:
                tags_text += " | missing: " + ", ".join(candidate.missing_tags)
            tags = QTableWidgetItem(tags_text)
            if candidate.resolution_status == "match":
                symbol = "✓"
            elif candidate.resolution_status == "mismatch":
                symbol = "✗"
            else:
                symbol = "?"
            local = f"{candidate.local_width}×{candidate.local_height}" if candidate.local_width else "?"
            remote = f"{candidate.remote_width}×{candidate.remote_height}" if candidate.remote_width else "?"
            resolution = QTableWidgetItem(f"{symbol} {local} / {remote}")
            reason = QTableWidgetItem(candidate.reason)
            path = QTableWidgetItem(candidate.path)
            path.setData(Qt.UserRole, candidate.path)
            path.setData(Qt.UserRole + 1, candidate.remote_image_url)
            path.setData(Qt.UserRole + 2, candidate.remote_post_url)
            row_background = colors.get(candidate.confidence)
            for column, item in enumerate((check, confidence, post_id, filename, tags, resolution, reason, path)):
                if column != 0:
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if row_background is not None:
                    item.setBackground(row_background)
                    item.setForeground(QColor(0, 0, 0))
                if not candidate.importable and column == 0:
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.candidate_table.setItem(row, column, item)
        self.candidate_table.setSortingEnabled(True)
        self.apply_candidate_filter()

    def selected_candidate_path_item(self) -> QTableWidgetItem | None:
        row = self.candidate_table.currentRow()
        if row < 0:
            return None
        return self.candidate_table.item(row, 7)

    def update_candidate_open_buttons(self) -> None:
        if not hasattr(self, "open_local_button"):
            return
        item = self.selected_candidate_path_item()
        enabled = self.thread is None and item is not None
        local_path = str(item.data(Qt.UserRole) or item.text()) if item else ""
        remote_url = str(item.data(Qt.UserRole + 1) or item.data(Qt.UserRole + 2) or "") if item else ""
        self.open_local_button.setEnabled(enabled and Path(local_path).is_file())
        self.open_remote_button.setEnabled(enabled and bool(remote_url))

    def open_selected_local_file(self) -> None:
        item = self.selected_candidate_path_item()
        if item is None:
            return
        path = Path(str(item.data(Qt.UserRole) or item.text()))
        if not path.is_file():
            QMessageBox.warning(self, tr("import.title", config=self.config), tr("import.warning.local_file_missing", "Local file no longer exists.", config=self.config))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def open_selected_remote_image(self) -> None:
        item = self.selected_candidate_path_item()
        if item is None:
            return
        remote_url = str(item.data(Qt.UserRole + 1) or item.data(Qt.UserRole + 2) or "").strip()
        if remote_url:
            QDesktopServices.openUrl(QUrl(remote_url))

    def open_candidate_from_item(self, item: QTableWidgetItem) -> None:
        if item.column() in (3, 7):
            self.open_selected_local_file()
        else:
            self.open_selected_remote_image()

    def apply_candidate_filter(self) -> None:
        visible_confidences: set[str] = set()
        if self.confidence_high_checkbox.isChecked():
            visible_confidences.add("high")
        if self.confidence_questionable_checkbox.isChecked():
            visible_confidences.add("questionable")
        if self.confidence_mismatch_checkbox.isChecked():
            visible_confidences.add("mismatch")

        for row in range(self.candidate_table.rowCount()):
            item = self.candidate_table.item(row, 1)
            confidence = str(item.data(Qt.UserRole) or "") if item else ""
            self.candidate_table.setRowHidden(row, confidence not in visible_confidences)

    def on_failed(self, traceback_text: str) -> None:
        self.set_controls_enabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setText(tr("import.failed", config=self.config))
        self.log_text.append(traceback_text)
        QMessageBox.critical(self, tr("import.failed", config=self.config), traceback_text)

    def cleanup_thread(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
        if self.thread is not None:
            self.thread.deleteLater()
            self.thread = None
        self.set_controls_enabled(True)
