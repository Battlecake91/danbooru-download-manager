from __future__ import annotations

import copy
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.database import Database
from app.services.post_import_service import PostImportService


class FetchWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    log = Signal(str)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        self.config = config

    @Slot()
    def run(self) -> None:
        worker_db: Database | None = None

        try:
            self.log.emit("Fetch gestartet.")
            self.log.emit("Öffne eigene SQLite-Verbindung im Worker-Thread.")

            database_file = Path(str(self.config["database_file"]))
            worker_db = Database(database_file)
            worker_db.connect()
            worker_db.initialize_schema()

            service = PostImportService(self.config, worker_db)
            result = service.fetch_and_store()

            self.log.emit("Fetch abgeschlossen.")
            self.finished.emit(result)

        except Exception:
            self.failed.emit(traceback.format_exc())

        finally:
            if worker_db is not None:
                try:
                    worker_db.close()
                    self.log.emit("Worker-DB-Verbindung geschlossen.")
                except Exception:
                    pass


class FetchTab(QWidget):
    fetch_started = Signal()
    fetch_finished = Signal()
    fetch_failed_signal = Signal()
    open_preview_requested = Signal()

    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.thread: QThread | None = None
        self.worker: FetchWorker | None = None

        self.main_layout = QVBoxLayout(self)

        self.info_label = QLabel(
            "Fetch lädt neue Posts nach SQLite. Wähle klar zwischen manueller Tag-Suche und Saved Searches. "
            "Ja, so simpel hätte es natürlich von Anfang an sein können."
        )
        self.info_label.setWordWrap(True)
        self.main_layout.addWidget(self.info_label)

        self.source_group = QGroupBox("Suchquelle")
        self.source_layout = QFormLayout(self.source_group)

        self.source_mode_combo = QComboBox()
        self.source_mode_combo.addItem("Manuelle Tags / Query", "tags")
        self.source_mode_combo.addItem("Saved Searches", "saved_searches")
        self.source_mode_combo.currentIndexChanged.connect(self.on_source_mode_changed)
        self.source_layout.addRow("Quelle:", self.source_mode_combo)

        self.main_layout.addWidget(self.source_group)

        self.manual_group = QGroupBox("Manuelle Tags")
        self.manual_layout = QFormLayout(self.manual_group)

        self.manual_query_edit = QLineEdit()
        self.manual_query_edit.setPlaceholderText("z. B. 1girl cute smile ( rating:s or rating:q )")
        self.manual_layout.addRow("Tags / Query:", self.manual_query_edit)

        self.main_layout.addWidget(self.manual_group)

        self.saved_search_group = QGroupBox("Saved Searches")
        self.saved_search_layout = QFormLayout(self.saved_search_group)

        self.saved_search_label_edit = QLineEdit()
        self.saved_search_label_edit.setPlaceholderText("z. B. default")
        self.saved_search_layout.addRow("Label:", self.saved_search_label_edit)

        self.saved_search_query_edit = QLineEdit()
        self.saved_search_query_edit.setPlaceholderText("optional: exakter Saved-Search-Querystring")
        self.saved_search_layout.addRow("Query-Filter:", self.saved_search_query_edit)

        self.saved_search_hint = QLabel(
            "Label filtert nach Saved-Search-Labels. Query-Filter ist optional und muss exakt zur Saved Search passen. "
            "Mehrere Labels oder Queries kannst du mit Komma trennen."
        )
        self.saved_search_hint.setWordWrap(True)
        self.saved_search_layout.addRow("Hinweis:", self.saved_search_hint)

        self.main_layout.addWidget(self.saved_search_group)

        self.options_group = QGroupBox("Fetch-Optionen")
        self.options_layout = QFormLayout(self.options_group)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 200)
        self.limit_spin.setValue(int(config.get("limit", 100)))
        self.limit_spin.setKeyboardTracking(False)
        self.options_layout.addRow("API Limit pro Seite:", self.limit_spin)

        self.max_posts_per_query_spin = QSpinBox()
        self.max_posts_per_query_spin.setRange(1, 100000)
        self.max_posts_per_query_spin.setValue(int(config.get("max_posts_per_query", 200)))
        self.max_posts_per_query_spin.setKeyboardTracking(False)
        self.options_layout.addRow("Max Posts pro Query:", self.max_posts_per_query_spin)

        self.max_total_posts_spin = QSpinBox()
        self.max_total_posts_spin.setRange(1, 100000)
        self.max_total_posts_spin.setValue(int(config.get("max_total_posts", 500)))
        self.max_total_posts_spin.setKeyboardTracking(False)
        self.options_layout.addRow("Max Posts gesamt:", self.max_total_posts_spin)

        self.main_layout.addWidget(self.options_group)

        self.button_row = QHBoxLayout()

        self.fetch_button = QPushButton("Fetch starten")
        self.fetch_button.clicked.connect(self.start_fetch)
        self.button_row.addWidget(self.fetch_button)

        self.preview_button = QPushButton("Preview öffnen")
        self.preview_button.clicked.connect(self.open_preview_requested.emit)
        self.button_row.addWidget(self.preview_button)

        self.button_row.addStretch(1)
        self.main_layout.addLayout(self.button_row)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(180)
        self.main_layout.addWidget(self.log_text, stretch=1)

        self.load_initial_values_from_config()
        self.on_source_mode_changed()

    def load_initial_values_from_config(self) -> None:
        self.manual_query_edit.setText(str(self.config.get("search_tags", "") or ""))
        self.saved_search_label_edit.setText(", ".join(str(v) for v in self.config.get("saved_search_labels", []) or []))
        self.saved_search_query_edit.setText(", ".join(str(v) for v in self.config.get("saved_search_queries", []) or []))

        mode = "saved_searches" if bool(self.config.get("use_saved_searches", False)) else "tags"
        index = self.source_mode_combo.findData(mode)
        if index >= 0:
            self.source_mode_combo.setCurrentIndex(index)

    def on_source_mode_changed(self, *_args) -> None:
        mode = self.selected_source_mode()
        self.manual_group.setVisible(mode == "tags")
        self.saved_search_group.setVisible(mode == "saved_searches")

    def selected_source_mode(self) -> str:
        value = self.source_mode_combo.currentData()
        return str(value or "tags")

    @staticmethod
    def split_csv_text(text: str) -> list[str]:
        normalized = text.replace(";", ",")
        return [part.strip() for part in normalized.split(",") if part.strip()]

    def build_fetch_config(self) -> dict[str, Any]:
        fetch_config = copy.deepcopy(self.config)

        fetch_config["limit"] = int(self.limit_spin.value())
        fetch_config["max_posts_per_query"] = int(self.max_posts_per_query_spin.value())
        fetch_config["max_total_posts"] = int(self.max_total_posts_spin.value())

        mode = self.selected_source_mode()

        if mode == "tags":
            query = self.manual_query_edit.text().strip()
            if not query:
                raise ValueError("Manuelle Tags/Query ist leer. Suchmaschinen funktionieren leider selten mit Telepathie.")

            fetch_config["use_saved_searches"] = False
            fetch_config["search_tags"] = query
            fetch_config["saved_search_labels"] = []
            fetch_config["saved_search_queries"] = []
            fetch_config["saved_search_extra_tags"] = ""
            return fetch_config

        labels = self.split_csv_text(self.saved_search_label_edit.text())
        queries = self.split_csv_text(self.saved_search_query_edit.text())

        if not labels:
            raise ValueError("Saved-Search-Label fehlt. Irgendein Anker in diesem Meer aus Tags wäre schon nett.")

        fetch_config["use_saved_searches"] = True
        fetch_config["search_tags"] = ""
        fetch_config["saved_search_labels"] = labels
        fetch_config["saved_search_queries"] = queries
        fetch_config["saved_search_extra_tags"] = ""

        return fetch_config

    def start_fetch(self) -> None:
        if self.thread is not None:
            QMessageBox.information(self, "Fetch läuft", "Es läuft bereits ein Fetch.")
            return

        try:
            fetch_config = self.build_fetch_config()
        except Exception as exc:
            QMessageBox.warning(self, "Ungültige Fetch-Konfiguration", str(exc))
            return

        self.fetch_button.setEnabled(False)
        self.log_text.append("Starte Fetch...")
        self.fetch_started.emit()

        self.thread = QThread(self)
        self.worker = FetchWorker(fetch_config)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.log_text.append)
        self.worker.finished.connect(self.on_fetch_finished)
        self.worker.failed.connect(self.on_fetch_failed)

        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.cleanup_thread)

        self.thread.start()

    def on_fetch_finished(self, result: object) -> None:
        self.log_text.append(f"Fetch fertig: {result}")
        self.fetch_button.setEnabled(True)
        self.fetch_finished.emit()
        self.open_preview_requested.emit()

    def on_fetch_failed(self, traceback_text: str) -> None:
        self.log_text.append("Fetch fehlgeschlagen:")
        self.log_text.append(traceback_text)
        self.fetch_button.setEnabled(True)
        self.fetch_failed_signal.emit()
        QMessageBox.critical(self, "Fetch fehlgeschlagen", traceback_text)

    def cleanup_thread(self) -> None:
        self.thread = None
        self.worker = None
