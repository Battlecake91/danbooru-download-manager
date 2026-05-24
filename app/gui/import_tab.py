from __future__ import annotations

import copy
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot
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
    QVBoxLayout,
    QWidget,
)

from app.core.database import Database
from app.i18n.i18n import tr
from app.services.existing_file_import_service import (
    ExistingFileImportProgress,
    ExistingFileImportService,
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

    @Slot()
    def run(self) -> None:
        worker_db: Database | None = None
        try:
            database_file = Path(str(self.config["database_file"]))
            worker_db = Database(database_file)
            worker_db.connect()
            worker_db.initialize_schema()

            service = ExistingFileImportService(self.config, worker_db, progress_callback=self.progress.emit)
            if self.mode == "import":
                self.log.emit(tr("import.log.import_started", "Existing file import started.", config=self.config))
                result = service.import_folder(
                    self.folder,
                    self.category_id,
                    recursive=self.recursive,
                    rename_after_import=self.rename_after_import,
                    update_existing=self.update_existing,
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
                result = service.rename_saved_files_for_category(self.category_id)
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
        self.import_button = QPushButton(tr("import.button.import_folder", config=self.config))
        self.import_button.clicked.connect(self.start_import)
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

        self.progress_label = QLabel(tr("common.ready", "Ready.", config=self.config))
        self.progress_label.setWordWrap(True)
        self.main_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.main_layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(260)
        self.main_layout.addWidget(self.log_text, stretch=1)

        self.load_categories()

    def choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, tr("import.dialog.choose_folder.title", config=self.config), self.folder_edit.text().strip() or str(Path.home()))
        if selected:
            self.folder_edit.setText(selected)

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
        self.old_category_combo.setEnabled(enabled)
        self.repair_button.setEnabled(enabled)
        self.import_button.setEnabled(enabled)
        self.rename_category_button.setEnabled(enabled)
        self.refresh_categories_button.setEnabled(enabled)

    def start_import(self) -> None:
        folder = self.folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, tr("import.title", config=self.config), tr("import.warning.select_import_folder", config=self.config))
            return
        if not Path(folder).expanduser().is_dir():
            QMessageBox.warning(self, tr("import.title", config=self.config), tr("import.warning.folder_not_found", config=self.config, folder=folder))
            return

        category_id = self.current_category_id()
        if category_id is None:
            QMessageBox.warning(self, tr("import.title", config=self.config), tr("import.warning.select_category", config=self.config))
            return

        self.start_worker(
            mode="import",
            folder=folder,
            category_id=category_id,
            recursive=self.recursive_checkbox.isChecked(),
            rename_after_import=self.rename_after_import_checkbox.isChecked(),
            update_existing=self.update_existing_checkbox.isChecked(),
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
        if QMessageBox.question(
            self,
            tr("import.confirm_rename.title", config=self.config),
            tr("import.confirm_rename.message", config=self.config, category_name=category_name),
        ) != QMessageBox.Yes:
            return

        self.start_worker(
            mode="rename",
            folder="",
            category_id=category_id,
            recursive=False,
            rename_after_import=False,
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
                not_found=progress.not_found,
                errors=progress.errors,
            )
        )
        if progress.message:
            self.log_text.append(progress.message)

    def on_finished(self, result: object) -> None:
        self.set_controls_enabled(True)
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
        )
        self.log_text.append(summary)
        self.progress_label.setText(summary.replace("\n", " | "))
        self.import_finished.emit()

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
