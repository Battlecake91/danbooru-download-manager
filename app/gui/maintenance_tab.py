from __future__ import annotations

import json
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
from app.services.download_service import DownloadService


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
    """Temporäre Werkbank für einmalige Reparaturen.

    Das Ding ist absichtlich nicht hübsch. Es soll falsche lokale Dateien finden,
    nicht im Museum für GUI-Design ausgestellt werden.
    """

    HEADERS = [
        "Status",
        "Post-ID",
        "Lokal",
        "Danbooru",
        "Dateigröße",
        "Hinweis",
        "Pfad",
    ]

    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()
        self.config = config
        self.db = db
        self.api = DanbooruApi(config)
        self.download_service = DownloadService(config, db)
        self.current_rows: list[QualityAuditRow] = []

        layout = QVBoxLayout(self)

        self.db_info_label = QLabel(
            "Datenbank-Wartung: analysiert Tabellen/Indizes, app_settings, WAL-Dateien "
            "und kann LLM-Debug-Payloads löschen. VACUUM kann je nach DB-Größe kurz dauern, "
            "weil SQLite dann einmal tief durchatmet und die Möbel neu stellt."
        )
        self.db_info_label.setWordWrap(True)
        layout.addWidget(self.db_info_label)

        db_controls = QHBoxLayout()
        self.analyze_db_button = QPushButton("Datenbankgröße analysieren")
        self.analyze_db_button.clicked.connect(self.analyze_database_size)
        db_controls.addWidget(self.analyze_db_button)

        self.clear_llm_payloads_button = QPushButton("LLM-Debug-Payloads löschen")
        self.clear_llm_payloads_button.clicked.connect(self.clear_llm_debug_payloads)
        db_controls.addWidget(self.clear_llm_payloads_button)

        self.checkpoint_wal_button = QPushButton("WAL komprimieren")
        self.checkpoint_wal_button.clicked.connect(self.checkpoint_wal)
        db_controls.addWidget(self.checkpoint_wal_button)

        self.vacuum_button = QPushButton("VACUUM ausführen")
        self.vacuum_button.clicked.connect(self.vacuum_database)
        db_controls.addWidget(self.vacuum_button)
        db_controls.addStretch(1)
        layout.addLayout(db_controls)

        self.db_result_text = QPlainTextEdit()
        self.db_result_text.setReadOnly(True)
        self.db_result_text.setMinimumHeight(180)
        self.db_result_text.setPlainText("Noch keine Datenbankanalyse ausgeführt.")
        layout.addWidget(self.db_result_text)

        self.info_label = QLabel(
            "Temporäre Prüfung: findet lokal gespeicherte Dateien, die kleiner als die "
            "Danbooru-Originalauflösung sind. Fehlende Originalmaße können direkt von "
            "Danbooru nachgeladen werden. Später darf dieser Tab wieder rausfliegen, "
            "wie ein hässliches Gerüst nach der Renovierung."
        )
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        controls = QHBoxLayout()

        self.fetch_missing_metadata_checkbox = QCheckBox("Fehlende Originalmaße von Danbooru nachladen")
        self.fetch_missing_metadata_checkbox.setChecked(True)
        controls.addWidget(self.fetch_missing_metadata_checkbox)

        self.scan_button = QPushButton("Gespeicherte Dateien prüfen")
        self.scan_button.clicked.connect(self.scan_saved_files)
        controls.addWidget(self.scan_button)

        self.repair_selected_button = QPushButton("Ausgewählte Verdächtige neu laden/ersetzen")
        self.repair_selected_button.clicked.connect(self.repair_selected_rows)
        controls.addWidget(self.repair_selected_button)

        self.repair_all_button = QPushButton("Alle Verdächtigen/Fehlenden neu laden/ersetzen")
        self.repair_all_button.clicked.connect(self.repair_all_suspects)
        controls.addWidget(self.repair_all_button)

        controls.addStretch(1)
        layout.addLayout(controls)

        self.result_label = QLabel("Noch nicht geprüft.")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.open_selected_file)
        layout.addWidget(self.table, stretch=1)

    def analyze_database_size(self) -> None:
        self.analyze_db_button.setEnabled(False)
        self.db_result_text.setPlainText("Analysiere Datenbankgröße ...")
        try:
            report = self.db.analyze_database_size()
            self.db_result_text.setPlainText(format_database_size_report(report))
        except Exception as exc:
            QMessageBox.critical(self, "Datenbankanalyse fehlgeschlagen", str(exc))
            self.db_result_text.setPlainText(f"Datenbankanalyse fehlgeschlagen: {exc}")
        finally:
            self.analyze_db_button.setEnabled(True)

    def clear_llm_debug_payloads(self) -> None:
        answer = QMessageBox.question(
            self,
            "LLM-Debug-Payloads löschen?",
            "Die gespeicherten LLM-Debug-Payloads und deren Summary werden aus app_settings gelöscht. "
            "LLM-Ergebnisse an Posts bleiben erhalten. Fortfahren?",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            deleted = self.db.clear_llm_debug_payload_settings()
            QMessageBox.information(self, "LLM-Debug-Payloads gelöscht", f"Gelöschte Einträge: {deleted}")
            self.analyze_database_size()
        except Exception as exc:
            QMessageBox.critical(self, "Löschen fehlgeschlagen", str(exc))

    def checkpoint_wal(self) -> None:
        try:
            before = self.db.database_file_sizes()
            result = self.db.checkpoint_wal_truncate()
            after = self.db.database_file_sizes()
            QMessageBox.information(
                self,
                "WAL komprimiert",
                "WAL-Checkpoint/TRUNCATE ausgeführt.\n"
                f"Vorher WAL: {format_bytes(before.get('wal', 0))}\n"
                f"Nachher WAL: {format_bytes(after.get('wal', 0))}\n"
                f"SQLite-Ergebnis: {result}",
            )
            self.analyze_database_size()
        except Exception as exc:
            QMessageBox.critical(self, "WAL-Komprimierung fehlgeschlagen", str(exc))

    def vacuum_database(self) -> None:
        answer = QMessageBox.warning(
            self,
            "VACUUM ausführen?",
            "VACUUM kompaktiert die SQLite-Datei und kann bei großen Datenbanken eine Weile dauern. "
            "Währenddessen sollte kein Fetch/Import laufen. Fortfahren?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.vacuum_button.setEnabled(False)
        self.db_result_text.setPlainText("VACUUM läuft ... bitte nicht nervös auf Knöpfe hämmern.")
        try:
            before = self.db.database_file_sizes()
            self.db.vacuum_database()
            after = self.db.database_file_sizes()
            QMessageBox.information(
                self,
                "VACUUM abgeschlossen",
                f"Vorher: {format_bytes(before.get('database', 0))}\n"
                f"Nachher: {format_bytes(after.get('database', 0))}",
            )
            self.analyze_database_size()
        except Exception as exc:
            QMessageBox.critical(self, "VACUUM fehlgeschlagen", str(exc))
            self.db_result_text.setPlainText(f"VACUUM fehlgeschlagen: {exc}")
        finally:
            self.vacuum_button.setEnabled(True)

    def scan_saved_files(self) -> None:
        self.scan_button.setEnabled(False)
        self.result_label.setText("Prüfe gespeicherte Dateien ...")
        self.table.setRowCount(0)
        self.current_rows = []

        try:
            rows = self.db.fetch_saved_posts_for_quality_audit()
            audit_rows = [self.audit_post(row) for row in rows]
            self.current_rows = audit_rows
            self.populate_table(audit_rows)

            suspects = sum(1 for row in audit_rows if row.status == "Verdächtig")
            unclear = sum(1 for row in audit_rows if row.status == "Unklar")
            errors = sum(1 for row in audit_rows if row.status == "Fehler")
            ok = sum(1 for row in audit_rows if row.status == "OK")
            self.result_label.setText(
                f"Geprüft: {len(audit_rows)} | OK: {ok} | Verdächtig: {suspects} | "
                f"Unklar: {unclear} | Fehlend/Fehler: {errors}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Prüfung fehlgeschlagen", str(exc))
            self.result_label.setText(f"Prüfung fehlgeschlagen: {exc}")
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
                    status="Unklar",
                    note=f"Remote-Metadaten konnten nicht geladen werden: {exc}",
                )

        if final_path is None or not final_path.exists():
            # Fehlende lokale Dateien sind reparierbar, wenn ein lokaler Dateipfad in der DB steht.
            # Früher wurde hier nur gemeckert und beim Reparieren trotzdem abgebrochen.
            # Sehr hilfreich, wenn man gerne Türen ohne Griff einbaut.
            return QualityAuditRow(
                post_id=post_id,
                final_path=final_path,
                local_size=None,
                local_width=None,
                local_height=None,
                remote_size=remote_size,
                remote_width=remote_width,
                remote_height=remote_height,
                status="Fehler",
                note="Lokaler Dateipfad fehlt oder Datei existiert nicht",
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
                status="Unklar",
                note="Danbooru-Originalmaße fehlen",
            )

        dimension_suspect = (
            local_width is not None
            and local_height is not None
            and (local_width < remote_width or local_height < remote_height)
        )
        size_suspect = remote_size is not None and local_size < int(remote_size * 0.98)

        if dimension_suspect:
            status = "Verdächtig"
            note = "Lokale Auflösung ist kleiner als Danbooru-Original"
        elif size_suspect:
            status = "Verdächtig"
            note = "Lokale Datei ist deutlich kleiner als Danbooru-file_size"
        elif local_width is None or local_height is None:
            status = "Unklar"
            note = "Lokale Bildmaße nicht lesbar, eventuell Video/defekte Datei"
        else:
            status = "OK"
            note = "Lokale Datei passt zu den bekannten Originaldaten"

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
            return {"Verdächtig": 0, "Fehler": 1, "Unklar": 2, "OK": 3}.get(row.status, 9)

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
                if row.status == "Verdächtig":
                    item.setBackground(QColor("#5a4a00"))
                elif row.status == "Fehler":
                    item.setBackground(QColor("#5a1d1d"))
                elif row.status == "OK":
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
        return [row.post_id for row in self.current_rows if row.status in {"Verdächtig", "Fehler"}]

    def repair_selected_rows(self) -> None:
        self.repair_posts(self.selected_post_ids())

    def repair_all_suspects(self) -> None:
        self.repair_posts(self.suspect_post_ids())

    def repair_posts(self, post_ids: list[int]) -> None:
        if not post_ids:
            QMessageBox.information(self, "Nichts zu tun", "Keine verdächtigen Posts ausgewählt.")
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

        message = f"Ersetzt: {repaired}"
        if failed:
            message += "\nFehler:\n" + "\n".join(failed[:20])
            if len(failed) > 20:
                message += f"\n... und {len(failed) - 20} weitere"

        QMessageBox.information(self, "Reparatur abgeschlossen", message)
        self.scan_saved_files()

    def replace_final_file_with_original(self, post_id: int) -> None:
        row = self.db.get_post_detail(post_id)
        if row is None:
            raise RuntimeError("Post nicht in Datenbank")

        final_value = row["final_file_path"]
        if not final_value:
            raise RuntimeError("final_file_path fehlt")

        final_path = Path(str(final_value))
        final_path.parent.mkdir(parents=True, exist_ok=True)

        original_path_value = self.download_service.ensure_full_original_cached(post_id, force=True)
        if not original_path_value:
            raise RuntimeError("Originaldatei konnte nicht geladen werden")

        original_path = Path(original_path_value)
        if not original_path.exists():
            raise RuntimeError(f"Original-Cache fehlt: {original_path}")

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


def format_database_size_report(report: dict[str, Any]) -> str:
    file_sizes = report.get("file_sizes", {}) or {}
    sqlite_info = report.get("sqlite", {}) or {}
    counts = report.get("counts", {}) or {}
    object_sizes = report.get("object_sizes", []) or []
    largest_app_settings = report.get("largest_app_settings", []) or []

    lines: list[str] = []
    lines.append("Datenbankgröße")
    lines.append("===============")
    lines.append(f"Pfad: {report.get('path', '-')}")
    lines.append(f"DB-Datei: {format_bytes(file_sizes.get('database', 0))}")
    lines.append(f"WAL:      {format_bytes(file_sizes.get('wal', 0))}")
    lines.append(f"SHM:      {format_bytes(file_sizes.get('shm', 0))}")
    lines.append(f"Gesamt:   {format_bytes(file_sizes.get('total', 0))}")
    lines.append("")
    lines.append("SQLite")
    lines.append("------")
    lines.append(f"Journal-Modus: {sqlite_info.get('journal_mode', '-')}")
    lines.append(f"Page size: {sqlite_info.get('page_size', '-')}")
    lines.append(f"Pages: {sqlite_info.get('page_count', '-')}")
    lines.append(f"Freelist pages: {sqlite_info.get('freelist_count', '-')}")
    lines.append(f"Geschätzter freier Platz: {format_bytes(sqlite_info.get('free_bytes_estimate', 0))}")
    lines.append("")
    lines.append("Zeilen")
    lines.append("------")
    for key in ("posts", "post_tags", "tag_scores", "categories", "app_settings"):
        lines.append(f"{key}: {counts.get(key, '-')}")

    lines.append("")
    if report.get("dbstat_available"):
        lines.append("Größte Tabellen/Indizes laut dbstat")
        lines.append("-----------------------------------")
        for item in object_sizes[:30]:
            lines.append(f"{format_bytes(int(item.get('bytes', 0))):>12}  {item.get('name', '-')}")
    else:
        lines.append("dbstat ist in dieser SQLite-Version nicht verfügbar. Natürlich fehlt genau das Werkzeug, wenn man es mal braucht.")

    lines.append("")
    lines.append("Größte app_settings")
    lines.append("-------------------")
    for item in largest_app_settings[:20]:
        lines.append(
            f"{format_bytes(int(item.get('bytes', 0))):>12}  {item.get('key', '-')}  {item.get('updated_at', '')}"
        )

    lines.append("")
    lines.append("Hinweis")
    lines.append("-------")
    lines.append("Wenn llm.last_fetch_payloads groß ist: 'LLM-Debug-Payloads löschen' drücken.")
    lines.append("Wenn WAL groß ist: 'WAL komprimieren' drücken.")
    lines.append("Wenn Freelist groß ist: 'VACUUM ausführen' kann die DB-Datei verkleinern.")
    return "\n".join(lines)
