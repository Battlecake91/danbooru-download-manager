from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImageReader
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.database import Database
from app.danbooru.api import DanbooruApi
from app.i18n.i18n import tr
from app.services.download_service import DownloadService


STATUS_OK = "OK"
STATUS_SUSPECT = "Suspect"
STATUS_UNCLEAR = "Unclear"
STATUS_ERROR = "Error"


@dataclass
class QualityAuditRow:
    post_id: int
    final_path: Path | None
    local_size: int | None
    local_width: int | None
    local_height: int | None
    remote_size: int | None
    remote_width: int | None
    remote_height: int | None
    status: str
    note: str


class MaintenanceTab(QWidget):
    """Temporary workbench for database maintenance and local file audits."""

    HEADER_KEYS = [
        "maintenance.header.status",
        "maintenance.header.post_id",
        "maintenance.header.local",
        "maintenance.header.danbooru",
        "maintenance.header.file_size",
        "maintenance.header.note",
        "maintenance.header.path",
    ]

    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()
        self.config = config
        self.db = db
        self.api = DanbooruApi(config)
        self.download_service = DownloadService(config, db)
        self.current_rows: list[QualityAuditRow] = []

        layout = QVBoxLayout(self)

        self.db_info_label = QLabel(tr("maintenance.db_info", config=self.config))
        self.db_info_label.setWordWrap(True)
        layout.addWidget(self.db_info_label)

        db_controls = QHBoxLayout()
        self.analyze_db_button = QPushButton(tr("maintenance.analyze_db", config=self.config))
        self.analyze_db_button.clicked.connect(self.analyze_database_size)
        db_controls.addWidget(self.analyze_db_button)

        self.clear_llm_payloads_button = QPushButton(tr("maintenance.clear_llm_payloads", config=self.config))
        self.clear_llm_payloads_button.clicked.connect(self.clear_llm_debug_payloads)
        db_controls.addWidget(self.clear_llm_payloads_button)

        self.checkpoint_wal_button = QPushButton(tr("maintenance.checkpoint_wal", config=self.config))
        self.checkpoint_wal_button.clicked.connect(self.checkpoint_wal)
        db_controls.addWidget(self.checkpoint_wal_button)

        self.vacuum_button = QPushButton(tr("maintenance.vacuum", config=self.config))
        self.vacuum_button.clicked.connect(self.vacuum_database)
        db_controls.addWidget(self.vacuum_button)
        db_controls.addStretch(1)
        layout.addLayout(db_controls)

        self.db_result_text = QPlainTextEdit()
        self.db_result_text.setReadOnly(True)
        self.db_result_text.setMinimumHeight(180)
        self.db_result_text.setPlainText(tr("maintenance.db_no_analysis", config=self.config))
        layout.addWidget(self.db_result_text)

        self.info_label = QLabel(tr("maintenance.quality_info", config=self.config))
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        controls = QHBoxLayout()

        self.fetch_missing_metadata_checkbox = QCheckBox(tr("maintenance.fetch_missing_metadata", config=self.config))
        self.fetch_missing_metadata_checkbox.setChecked(True)
        controls.addWidget(self.fetch_missing_metadata_checkbox)

        self.scan_button = QPushButton(tr("maintenance.scan_saved_files", config=self.config))
        self.scan_button.clicked.connect(self.scan_saved_files)
        controls.addWidget(self.scan_button)

        self.repair_selected_button = QPushButton(tr("maintenance.repair_selected", config=self.config))
        self.repair_selected_button.clicked.connect(self.repair_selected_rows)
        controls.addWidget(self.repair_selected_button)

        self.repair_all_button = QPushButton(tr("maintenance.repair_all", config=self.config))
        self.repair_all_button.clicked.connect(self.repair_all_suspects)
        controls.addWidget(self.repair_all_button)

        controls.addStretch(1)
        layout.addLayout(controls)

        self.result_label = QLabel(tr("maintenance.not_checked", config=self.config))
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        self.table = QTableWidget(0, len(self.HEADER_KEYS))
        self.table.setHorizontalHeaderLabels([tr(key, config=self.config) for key in self.HEADER_KEYS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.open_selected_file)
        layout.addWidget(self.table, stretch=1)

    def analyze_database_size(self) -> None:
        self.analyze_db_button.setEnabled(False)
        self.db_result_text.setPlainText(tr("maintenance.analyzing_db", config=self.config))
        try:
            report = self.db.analyze_database_size()
            self.db_result_text.setPlainText(format_database_size_report(report, self.config))
        except Exception as exc:
            QMessageBox.critical(self, tr("maintenance.db_analysis_failed_title", config=self.config), str(exc))
            self.db_result_text.setPlainText(tr("maintenance.db_analysis_failed", config=self.config, error=exc))
        finally:
            self.analyze_db_button.setEnabled(True)

    def clear_llm_debug_payloads(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("maintenance.clear_llm_payloads_title", config=self.config),
            tr("maintenance.clear_llm_payloads_question", config=self.config),
        )
        if answer != QMessageBox.Yes:
            return
        try:
            deleted = self.db.clear_llm_debug_payload_settings()
            QMessageBox.information(
                self,
                tr("maintenance.clear_llm_payloads_done_title", config=self.config),
                tr("maintenance.deleted_entries", config=self.config, count=deleted),
            )
            self.analyze_database_size()
        except Exception as exc:
            QMessageBox.critical(self, tr("maintenance.delete_failed_title", config=self.config), str(exc))

    def checkpoint_wal(self) -> None:
        try:
            before = self.db.database_file_sizes()
            result = self.db.checkpoint_wal_truncate()
            after = self.db.database_file_sizes()
            QMessageBox.information(
                self,
                tr("maintenance.wal_checkpoint_done_title", config=self.config),
                tr(
                    "maintenance.wal_checkpoint_done_message",
                    config=self.config,
                    before=format_bytes(before.get("wal", 0)),
                    after=format_bytes(after.get("wal", 0)),
                    result=result,
                ),
            )
            self.analyze_database_size()
        except Exception as exc:
            QMessageBox.critical(self, tr("maintenance.wal_checkpoint_failed_title", config=self.config), str(exc))

    def vacuum_database(self) -> None:
        answer = QMessageBox.warning(
            self,
            tr("maintenance.vacuum_question_title", config=self.config),
            tr("maintenance.vacuum_question", config=self.config),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.vacuum_button.setEnabled(False)
        self.db_result_text.setPlainText(tr("maintenance.vacuum_running", config=self.config))
        try:
            before = self.db.database_file_sizes()
            self.db.vacuum_database()
            after = self.db.database_file_sizes()
            QMessageBox.information(
                self,
                tr("maintenance.vacuum_done_title", config=self.config),
                tr(
                    "maintenance.vacuum_done_message",
                    config=self.config,
                    before=format_bytes(before.get("database", 0)),
                    after=format_bytes(after.get("database", 0)),
                ),
            )
            self.analyze_database_size()
        except Exception as exc:
            QMessageBox.critical(self, tr("maintenance.vacuum_failed_title", config=self.config), str(exc))
            self.db_result_text.setPlainText(tr("maintenance.vacuum_failed", config=self.config, error=exc))
        finally:
            self.vacuum_button.setEnabled(True)

    def scan_saved_files(self) -> None:
        self.scan_button.setEnabled(False)
        self.result_label.setText(tr("maintenance.scanning_saved_files", config=self.config))
        self.table.setRowCount(0)
        self.current_rows = []

        try:
            rows = self.db.fetch_saved_posts_for_quality_audit()
            audit_rows = [self.audit_post(row) for row in rows]
            self.current_rows = audit_rows
            self.populate_table(audit_rows)

            suspects = sum(1 for row in audit_rows if row.status == STATUS_SUSPECT)
            unclear = sum(1 for row in audit_rows if row.status == STATUS_UNCLEAR)
            errors = sum(1 for row in audit_rows if row.status == STATUS_ERROR)
            ok = sum(1 for row in audit_rows if row.status == STATUS_OK)
            self.result_label.setText(
                tr(
                    "maintenance.scan_summary",
                    config=self.config,
                    total=len(audit_rows),
                    ok=ok,
                    suspects=suspects,
                    unclear=unclear,
                    errors=errors,
                )
            )
        except Exception as exc:
            QMessageBox.critical(self, tr("maintenance.scan_failed_title", config=self.config), str(exc))
            self.result_label.setText(tr("maintenance.scan_failed", config=self.config, error=exc))
        finally:
            self.scan_button.setEnabled(True)

    def audit_post(self, row: Any) -> QualityAuditRow:
        post_id = int(row["id"])
        final_value = row["final_file_path"]
        final_path = Path(str(final_value)) if final_value else None

        remote_width = int(row["image_width"]) if row["image_width"] is not None else None
        remote_height = int(row["image_height"]) if row["image_height"] is not None else None
        remote_size = int(row["file_size"]) if row["file_size"] is not None else None

        if self.fetch_missing_metadata_checkbox.isChecked() and (remote_width is None or remote_height is None):
            try:
                post = self.api.get_post(post_id)
                self.db.update_post_remote_metadata(post_id, post)
                remote_width = int(post["image_width"]) if post.get("image_width") is not None else remote_width
                remote_height = int(post["image_height"]) if post.get("image_height") is not None else remote_height
                remote_size = int(post["file_size"]) if post.get("file_size") is not None else remote_size
            except Exception as exc:
                return QualityAuditRow(
                    post_id=post_id,
                    final_path=final_path,
                    local_size=None,
                    local_width=None,
                    local_height=None,
                    remote_size=remote_size,
                    remote_width=remote_width,
                    remote_height=remote_height,
                    status=STATUS_UNCLEAR,
                    note=tr("maintenance.note.remote_metadata_failed", config=self.config, error=exc),
                )

        if final_path is None or not final_path.exists():
            return QualityAuditRow(
                post_id=post_id,
                final_path=final_path,
                local_size=None,
                local_width=None,
                local_height=None,
                remote_size=remote_size,
                remote_width=remote_width,
                remote_height=remote_height,
                status=STATUS_ERROR,
                note=tr("maintenance.note.local_file_missing", config=self.config),
            )

        local_size = final_path.stat().st_size
        local_width, local_height = read_image_dimensions(final_path)

        if remote_width is None or remote_height is None:
            return QualityAuditRow(
                post_id=post_id,
                final_path=final_path,
                local_size=local_size,
                local_width=local_width,
                local_height=local_height,
                remote_size=remote_size,
                remote_width=remote_width,
                remote_height=remote_height,
                status=STATUS_UNCLEAR,
                note=tr("maintenance.note.remote_dimensions_missing", config=self.config),
            )

        dimension_suspect = (
            local_width is not None
            and local_height is not None
            and (local_width < remote_width or local_height < remote_height)
        )
        size_suspect = remote_size is not None and local_size < int(remote_size * 0.98)

        if dimension_suspect:
            status = STATUS_SUSPECT
            note = tr("maintenance.note.local_resolution_smaller", config=self.config)
        elif size_suspect:
            status = STATUS_SUSPECT
            note = tr("maintenance.note.local_file_smaller", config=self.config)
        elif local_width is None or local_height is None:
            status = STATUS_UNCLEAR
            note = tr("maintenance.note.local_dimensions_unreadable", config=self.config)
        else:
            status = STATUS_OK
            note = tr("maintenance.note.local_file_ok", config=self.config)

        return QualityAuditRow(
            post_id=post_id,
            final_path=final_path,
            local_size=local_size,
            local_width=local_width,
            local_height=local_height,
            remote_size=remote_size,
            remote_width=remote_width,
            remote_height=remote_height,
            status=status,
            note=note,
        )

    def populate_table(self, rows: list[QualityAuditRow]) -> None:
        def priority(row: QualityAuditRow) -> int:
            return {STATUS_SUSPECT: 0, STATUS_ERROR: 1, STATUS_UNCLEAR: 2, STATUS_OK: 3}.get(row.status, 9)

        sorted_rows = sorted(rows, key=lambda row: (priority(row), -row.post_id))
        self.current_rows = sorted_rows
        self.table.setRowCount(len(sorted_rows))

        for index, row in enumerate(sorted_rows):
            values = [
                row.status,
                str(row.post_id),
                format_dimensions(row.local_width, row.local_height),
                format_dimensions(row.remote_width, row.remote_height),
                format_size_pair(row.local_size, row.remote_size),
                row.note,
                str(row.final_path or ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, row.post_id)
                item.setData(Qt.UserRole + 1, str(row.final_path or ""))
                if row.status == STATUS_SUSPECT:
                    item.setBackground(QColor("#5a4a00"))
                elif row.status == STATUS_ERROR:
                    item.setBackground(QColor("#5a1d1d"))
                elif row.status == STATUS_OK:
                    item.setBackground(QColor("#1f4a1f"))
                self.table.setItem(index, column, item)

        self.table.resizeColumnsToContents()

    def selected_post_ids(self) -> list[int]:
        post_ids: list[int] = []
        seen: set[int] = set()
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 1)
            if item is None:
                continue
            post_id = int(item.text())
            if post_id not in seen:
                post_ids.append(post_id)
                seen.add(post_id)
        return post_ids

    def suspect_post_ids(self) -> list[int]:
        return [row.post_id for row in self.current_rows if row.status in {STATUS_SUSPECT, STATUS_ERROR}]

    def repair_selected_rows(self) -> None:
        self.repair_posts(self.selected_post_ids())

    def repair_all_suspects(self) -> None:
        self.repair_posts(self.suspect_post_ids())

    def repair_posts(self, post_ids: list[int]) -> None:
        if not post_ids:
            QMessageBox.information(
                self,
                tr("maintenance.nothing_to_do_title", config=self.config),
                tr("maintenance.nothing_to_do_message", config=self.config),
            )
            return

        self.repair_selected_button.setEnabled(False)
        self.repair_all_button.setEnabled(False)

        repaired = 0
        failed: list[str] = []

        try:
            for post_id in post_ids:
                try:
                    self.replace_final_file_with_original(post_id)
                    repaired += 1
                except Exception as exc:
                    failed.append(f"{post_id}: {exc}")
        finally:
            self.repair_selected_button.setEnabled(True)
            self.repair_all_button.setEnabled(True)

        message = tr("maintenance.repair_summary", config=self.config, repaired=repaired)
        if failed:
            message += "\n" + tr("maintenance.errors_heading", config=self.config) + "\n" + "\n".join(failed[:20])
            if len(failed) > 20:
                message += "\n" + tr("maintenance.more_errors", config=self.config, count=len(failed) - 20)

        QMessageBox.information(self, tr("maintenance.repair_done_title", config=self.config), message)
        self.scan_saved_files()

    def replace_final_file_with_original(self, post_id: int) -> None:
        row = self.db.get_post_detail(post_id)
        if row is None:
            raise RuntimeError(tr("maintenance.error.post_not_in_db", config=self.config))

        final_value = row["final_file_path"]
        if not final_value:
            raise RuntimeError(tr("maintenance.error.final_file_path_missing", config=self.config))

        final_path = Path(str(final_value))
        final_path.parent.mkdir(parents=True, exist_ok=True)

        original_path_value = self.download_service.ensure_full_original_cached(post_id, force=True)
        if not original_path_value:
            raise RuntimeError(tr("maintenance.error.original_download_failed", config=self.config))

        original_path = Path(original_path_value)
        if not original_path.exists():
            raise RuntimeError(tr("maintenance.error.original_cache_missing", config=self.config, path=original_path))

        tmp_path = final_path.with_name(final_path.name + ".replace_tmp")
        shutil.copy2(original_path, tmp_path)
        tmp_path.replace(final_path)

    def open_selected_file(self, *args) -> None:  # noqa: ANN002
        post_ids = self.selected_post_ids()
        if not post_ids:
            return
        row = self.db.get_post_detail(post_ids[0])
        if row is None or not row["final_file_path"]:
            return
        path = Path(str(row["final_file_path"]))
        if path.exists():
            os.startfile(path)


def read_image_dimensions(path: Path) -> tuple[int | None, int | None]:
    reader = QImageReader(str(path))
    size = reader.size()
    if not size.isValid():
        return None, None
    return int(size.width()), int(size.height())


def format_dimensions(width: int | None, height: int | None) -> str:
    if width is None or height is None:
        return "-"
    return f"{width}x{height}"


def format_size_pair(local_size: int | None, remote_size: int | None) -> str:
    return f"{format_bytes(local_size)} / {format_bytes(remote_size)}"


def format_bytes(value: int | None) -> str:
    if value is None:
        return "-"
    number = float(value)
    for unit in ["B", "KiB", "MiB", "GiB"]:
        if number < 1024.0 or unit == "GiB":
            return f"{number:.1f} {unit}" if unit != "B" else f"{int(number)} B"
        number /= 1024.0
    return f"{value} B"


def format_database_size_report(report: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    file_sizes = report.get("file_sizes", {}) or {}
    sqlite_info = report.get("sqlite", {}) or {}
    counts = report.get("counts", {}) or {}
    object_sizes = report.get("object_sizes", []) or []
    largest_app_settings = report.get("largest_app_settings", []) or []

    lines: list[str] = []
    lines.append(tr("maintenance.report.database_size", config=config))
    lines.append("===============")
    lines.append(tr("maintenance.report.path", config=config, path=report.get("path", "-")))
    lines.append(tr("maintenance.report.db_file", config=config, value=format_bytes(file_sizes.get("database", 0))))
    lines.append(tr("maintenance.report.wal", config=config, value=format_bytes(file_sizes.get("wal", 0))))
    lines.append(tr("maintenance.report.shm", config=config, value=format_bytes(file_sizes.get("shm", 0))))
    lines.append(tr("maintenance.report.total", config=config, value=format_bytes(file_sizes.get("total", 0))))
    lines.append("")
    lines.append("SQLite")
    lines.append("------")
    lines.append(tr("maintenance.report.journal_mode", config=config, value=sqlite_info.get("journal_mode", "-")))
    lines.append(tr("maintenance.report.page_size", config=config, value=sqlite_info.get("page_size", "-")))
    lines.append(tr("maintenance.report.pages", config=config, value=sqlite_info.get("page_count", "-")))
    lines.append(tr("maintenance.report.freelist_pages", config=config, value=sqlite_info.get("freelist_count", "-")))
    lines.append(
        tr(
            "maintenance.report.estimated_free_space",
            config=config,
            value=format_bytes(sqlite_info.get("free_bytes_estimate", 0)),
        )
    )
    lines.append("")
    lines.append(tr("maintenance.report.rows", config=config))
    lines.append("------")
    for key in ("posts", "post_tags", "tag_scores", "categories", "app_settings"):
        lines.append(f"{key}: {counts.get(key, '-')}")

    lines.append("")
    if report.get("dbstat_available"):
        lines.append(tr("maintenance.report.largest_objects", config=config))
        lines.append("-----------------------------------")
        for item in object_sizes[:30]:
            lines.append(f"{format_bytes(int(item.get('bytes', 0))):>12}  {item.get('name', '-')}")
    else:
        lines.append(tr("maintenance.report.dbstat_missing", config=config))

    lines.append("")
    lines.append(tr("maintenance.report.largest_app_settings", config=config))
    lines.append("-------------------")
    for item in largest_app_settings[:20]:
        lines.append(
            f"{format_bytes(int(item.get('bytes', 0))):>12}  {item.get('key', '-')}  {item.get('updated_at', '')}"
        )

    lines.append("")
    lines.append(tr("maintenance.report.note", config=config))
    lines.append("-------")
    lines.append(tr("maintenance.report.note_llm", config=config))
    lines.append(tr("maintenance.report.note_wal", config=config))
    lines.append(tr("maintenance.report.note_vacuum", config=config))
    return "\n".join(lines)
