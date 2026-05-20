from __future__ import annotations

import copy
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
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


@dataclass(frozen=True)
class FetchPreset:
    name: str
    mode: str
    query: str
    saved_search_labels: list[str]
    saved_search_queries: list[str]
    extra_tags: str
    limit: int | None
    max_posts_per_query: int | None
    max_total_posts: int | None


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
    fetch_finished = Signal()
    open_preview_requested = Signal()

    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.thread: QThread | None = None
        self.worker: FetchWorker | None = None

        self.presets = self.load_presets()

        self.main_layout = QVBoxLayout(self)

        self.info_label = QLabel(
            "Fetch lädt neue Posts nach SQLite. Danach kannst du sie im Preview/Review-Tab prüfen."
        )
        self.info_label.setWordWrap(True)
        self.main_layout.addWidget(self.info_label)

        self.preset_group = QGroupBox("Vordefinierte Suche")
        self.preset_layout = QFormLayout(self.preset_group)

        self.preset_combo = QComboBox()
        for preset in self.presets:
            self.preset_combo.addItem(preset.name, preset.name)
        self.preset_combo.currentIndexChanged.connect(self.on_preset_changed)
        self.preset_layout.addRow("Preset:", self.preset_combo)

        self.preset_description = QLabel("")
        self.preset_description.setWordWrap(True)
        self.preset_layout.addRow("Details:", self.preset_description)

        self.main_layout.addWidget(self.preset_group)

        self.manual_group = QGroupBox("Manuelle Suche")
        self.manual_layout = QFormLayout(self.manual_group)

        self.manual_query_edit = QLineEdit()
        self.manual_query_edit.setPlaceholderText("z. B. 1girl rating:q order:id_desc")
        self.manual_layout.addRow("Tags / Query:", self.manual_query_edit)

        self.manual_extra_tags_edit = QLineEdit()
        self.manual_extra_tags_edit.setPlaceholderText("optional, z. B. ( rating:q or rating:e )")
        self.manual_layout.addRow("Zusatz-Tags:", self.manual_extra_tags_edit)

        self.use_manual_checkbox = QCheckBox("Manuelle Query verwenden statt Preset")
        self.use_manual_checkbox.setChecked(False)
        self.manual_layout.addRow("", self.use_manual_checkbox)

        self.main_layout.addWidget(self.manual_group)

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

        self.fetch_saved_searches_checkbox = QCheckBox("Saved Searches verwenden")
        self.fetch_saved_searches_checkbox.setChecked(bool(config.get("use_saved_searches", False)))
        self.options_layout.addRow("", self.fetch_saved_searches_checkbox)

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

        self.on_preset_changed()

    def load_presets(self) -> list[FetchPreset]:
        raw_presets = self.config.get("fetch_presets", []) or []
        presets: list[FetchPreset] = []

        for item in raw_presets:
            if not isinstance(item, dict):
                continue

            presets.append(
                FetchPreset(
                    name=str(item.get("name", "Unnamed")),
                    mode=str(item.get("mode", "tags")),
                    query=str(item.get("query", "")),
                    saved_search_labels=[str(v) for v in item.get("saved_search_labels", []) or []],
                    saved_search_queries=[str(v) for v in item.get("saved_search_queries", []) or []],
                    extra_tags=str(item.get("extra_tags", item.get("saved_search_extra_tags", "")) or ""),
                    limit=int(item["limit"]) if item.get("limit") is not None else None,
                    max_posts_per_query=int(item["max_posts_per_query"]) if item.get("max_posts_per_query") is not None else None,
                    max_total_posts=int(item["max_total_posts"]) if item.get("max_total_posts") is not None else None,
                )
            )

        if not presets:
            presets.append(
                FetchPreset(
                    name="Config: Standard-Suche",
                    mode="saved_searches" if bool(self.config.get("use_saved_searches", False)) else "tags",
                    query=str(self.config.get("search_tags", "")),
                    saved_search_labels=[str(v) for v in self.config.get("saved_search_labels", []) or []],
                    saved_search_queries=[str(v) for v in self.config.get("saved_search_queries", []) or []],
                    extra_tags=str(self.config.get("saved_search_extra_tags", "") or ""),
                    limit=int(self.config.get("limit", 100)),
                    max_posts_per_query=int(self.config.get("max_posts_per_query", 200)),
                    max_total_posts=int(self.config.get("max_total_posts", 500)),
                )
            )

        return presets

    def selected_preset(self) -> FetchPreset:
        index = max(0, self.preset_combo.currentIndex())
        return self.presets[index]

    def on_preset_changed(self) -> None:
        preset = self.selected_preset()
        self.preset_description.setText(
            f"Modus: {preset.mode}\n"
            f"Query: {preset.query or '-'}\n"
            f"Labels: {', '.join(preset.saved_search_labels) or '-'}\n"
            f"Saved-Search-Queries: {', '.join(preset.saved_search_queries) or '-'}\n"
            f"Extra Tags: {preset.extra_tags or '-'}"
        )

        if preset.limit is not None:
            self.limit_spin.setValue(preset.limit)
        if preset.max_posts_per_query is not None:
            self.max_posts_per_query_spin.setValue(preset.max_posts_per_query)
        if preset.max_total_posts is not None:
            self.max_total_posts_spin.setValue(preset.max_total_posts)

        self.fetch_saved_searches_checkbox.setChecked(preset.mode == "saved_searches")

    def build_fetch_config(self) -> dict[str, Any]:
        fetch_config = copy.deepcopy(self.config)

        fetch_config["limit"] = int(self.limit_spin.value())
        fetch_config["max_posts_per_query"] = int(self.max_posts_per_query_spin.value())
        fetch_config["max_total_posts"] = int(self.max_total_posts_spin.value())

        if self.use_manual_checkbox.isChecked():
            query = self.manual_query_edit.text().strip()
            extra = self.manual_extra_tags_edit.text().strip()

            if not query:
                raise ValueError("Manuelle Query ist leer. So findet selbst ein Computer nichts, und die sind darin eigentlich gut.")

            if extra:
                query = f"{query} {extra}"

            fetch_config["use_saved_searches"] = False
            fetch_config["search_tags"] = query
            fetch_config["saved_search_labels"] = []
            fetch_config["saved_search_queries"] = []
            fetch_config["saved_search_extra_tags"] = ""

            return fetch_config

        preset = self.selected_preset()

        if preset.mode == "saved_searches" or self.fetch_saved_searches_checkbox.isChecked():
            fetch_config["use_saved_searches"] = True
            fetch_config["search_tags"] = preset.query or fetch_config.get("search_tags", "")
            fetch_config["saved_search_labels"] = preset.saved_search_labels
            fetch_config["saved_search_queries"] = preset.saved_search_queries
            fetch_config["saved_search_extra_tags"] = preset.extra_tags
        else:
            query = preset.query.strip()
            if preset.extra_tags:
                query = f"{query} {preset.extra_tags}".strip()

            fetch_config["use_saved_searches"] = False
            fetch_config["search_tags"] = query
            fetch_config["saved_search_labels"] = []
            fetch_config["saved_search_queries"] = []
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
        QMessageBox.critical(self, "Fetch fehlgeschlagen", traceback_text)

    def cleanup_thread(self) -> None:
        self.thread = None
        self.worker = None
