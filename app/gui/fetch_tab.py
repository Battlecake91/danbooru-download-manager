from __future__ import annotations

import copy
import json
import re
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot, QStringListModel, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.database import Database
from app.i18n.i18n import tr
from app.services.llm_batch_service import LLMBatchPreselectionService
from app.services.post_import_service import FetchProgress, PostImportService


RATING_FILTERS: list[tuple[str, str]] = [
    ("g", "General"),
    ("s", "Safe"),
    ("q", "Questionable"),
    ("e", "Explicit"),
]

RATING_STATE_IGNORE = "ignore"
RATING_STATE_INCLUDE = "include"
RATING_STATE_EXCLUDE = "exclude"


class FetchWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    log = Signal(str)
    progress = Signal(object)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        self.config = config

    @Slot()
    def run(self) -> None:
        worker_db: Database | None = None

        try:
            self.log.emit(tr("fetch.log.started", config=self.config))
            self.log.emit(tr("fetch.log.worker_db_open", config=self.config))

            database_file = Path(str(self.config["database_file"]))
            worker_db = Database(database_file)
            worker_db.connect()
            worker_db.initialize_schema()

            service = PostImportService(self.config, worker_db, progress_callback=self.progress.emit)
            result = service.fetch_and_store()

            llm_ids = list(getattr(result, "inserted_post_ids", []) or [])
            if not llm_ids:
                llm_ids = list(getattr(result, "fetched_post_ids", []) or [])
            llm_service = LLMBatchPreselectionService(self.config, worker_db, log_callback=self.log.emit)
            llm_result = llm_service.run_for_post_ids(llm_ids)
            result.llm_input_posts = llm_result.input_posts
            result.llm_candidate_posts = llm_result.candidate_posts
            result.llm_skipped_posts = llm_result.skipped_posts
            result.llm_batches_total = llm_result.batches_total
            result.llm_payloads_prepared = llm_result.payloads_prepared
            result.llm_batch_summaries = llm_result.batch_summaries
            result.llm_requests_sent = llm_result.requests_sent
            result.llm_decisions_received = llm_result.decisions_received
            result.llm_decisions_saved = llm_result.decisions_saved
            result.llm_skipped_reason = llm_result.skipped_reason
            result.llm_errors = llm_result.errors

            self.log.emit(tr("fetch.log.finished", config=self.config))
            self.finished.emit(result)

        except Exception:
            self.failed.emit(traceback.format_exc())

        finally:
            if worker_db is not None:
                try:
                    worker_db.close()
                    self.log.emit(tr("fetch.log.worker_db_closed", config=self.config))
                except Exception:
                    pass


class TagSuggestionWorker(QObject):
    finished = Signal(str, list)
    failed = Signal(str, str)

    def __init__(self, database_file: Path, prefix: str, limit: int = 120) -> None:
        super().__init__()
        self.database_file = database_file
        self.prefix = prefix
        self.limit = limit

    @Slot()
    def run(self) -> None:
        worker_db: Database | None = None
        try:
            worker_db = Database(self.database_file)
            worker_db.connect()
            tags = worker_db.suggest_tags(prefix=self.prefix, limit=self.limit)
            self.finished.emit(self.prefix, tags)
        except Exception:
            self.failed.emit(self.prefix, traceback.format_exc())
        finally:
            if worker_db is not None:
                try:
                    worker_db.close()
                except Exception:
                    pass


class TagQueryLineEdit(QLineEdit):
    suggestions_requested = Signal(str)

    """Line edit with asynchronous Danbooru-tag completion for the current token.

    Tags are separated by whitespace. A leading '-' belongs to the current
    token and is preserved when a completion is inserted. Completion data is
    requested for the current token only, instead of loading a giant tag list
    when the field gains focus. Because apparently a text box should not freeze
    the whole application just because someone clicked into it.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_requested_token = ""
        self._last_result_token = ""
        self._model = QStringListModel(self)
        self._request_timer = QTimer(self)
        self._request_timer.setSingleShot(True)
        self._request_timer.setInterval(220)
        self._request_timer.timeout.connect(self.request_current_token_suggestions)

        self._completer = QCompleter(self._model, self)
        self._completer.setWidget(self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.activated.connect(self.insert_completion)
        self._completer.popup().setMinimumWidth(420)
        self.textEdited.connect(self.schedule_completion_update)

    def set_tag_suggestions(self, token: str, tags: list[str]) -> None:
        current = self.current_token().lower()
        result_token = str(token or "").lower()
        if result_token != current:
            return
        self._last_result_token = result_token
        self._model.setStringList(sorted({tag for tag in tags if tag}, key=str.lower))
        self.update_completion_popup()

    def focusInEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        super().focusInEvent(event)
        self.schedule_completion_update()

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        super().keyPressEvent(event)
        QTimer.singleShot(0, self.schedule_completion_update)

    def focusOutEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        self._request_timer.stop()
        self._completer.popup().hide()
        super().focusOutEvent(event)

    def schedule_completion_update(self, *_args: Any) -> None:
        token = self.current_token()
        if len(token) < 2 or not self.hasFocus():
            self._request_timer.stop()
            self._completer.popup().hide()
            return
        self._request_timer.start()

    def request_current_token_suggestions(self) -> None:
        token = self.current_token().strip()
        if len(token) < 2 or not self.hasFocus():
            self._completer.popup().hide()
            return
        token_lower = token.lower()
        if token_lower == self._last_requested_token and token_lower == self._last_result_token:
            self.update_completion_popup()
            return
        self._last_requested_token = token_lower
        self.suggestions_requested.emit(token)

    def current_token_bounds(self) -> tuple[int, int, str, str]:
        text = self.text()
        cursor = self.cursorPosition()
        left = text[:cursor]
        match = re.search(r"([^\s()]+)$", left)
        if not match:
            return cursor, cursor, "", ""

        start = match.start(1)
        token = match.group(1)
        prefix = "-" if token.startswith("-") else ""
        clean_token = token[1:] if prefix else token
        return start, cursor, prefix, clean_token

    def current_token(self) -> str:
        _start, _end, _prefix, token = self.current_token_bounds()
        return token

    def update_completion_popup(self) -> None:
        token = self.current_token()
        if len(token) < 2 or not self.hasFocus():
            self._completer.popup().hide()
            return

        if not self._model.rowCount():
            self._completer.popup().hide()
            return

        self._completer.setCompletionPrefix("")

        popup = self._completer.popup()
        popup.setMinimumWidth(max(420, self.width()))

        rect = self.cursorRect()
        rect.setWidth(max(420, self.width()))
        self._completer.complete(rect)

    @Slot(str)
    def insert_completion(self, completion: str) -> None:
        text = self.text()
        start, end, prefix, _token = self.current_token_bounds()
        new_text = text[:start] + prefix + completion + " " + text[end:]
        self.setText(new_text)
        self.setCursorPosition(start + len(prefix) + len(completion) + 1)
        self._completer.popup().hide()


class RatingTriStateBox(QCheckBox):
    def __init__(self, rating_code: str, label: str) -> None:
        super().__init__(label)
        self.rating_code = rating_code
        self.base_label = label
        self.setTristate(True)
        self.setCheckState(Qt.Unchecked)
        self.stateChanged.connect(self.update_label)
        self.update_label()

    def rating_state(self) -> str:
        state = self.checkState()
        if state == Qt.Checked:
            return RATING_STATE_INCLUDE
        if state == Qt.PartiallyChecked:
            return RATING_STATE_EXCLUDE
        return RATING_STATE_IGNORE

    def set_rating_state(self, value: str | None) -> None:
        normalized = str(value or RATING_STATE_IGNORE).lower()
        if normalized == RATING_STATE_INCLUDE:
            self.setCheckState(Qt.Checked)
        elif normalized == RATING_STATE_EXCLUDE:
            self.setCheckState(Qt.PartiallyChecked)
        else:
            self.setCheckState(Qt.Unchecked)
        self.update_label()

    def update_label(self, *_args: Any) -> None:
        self.setText(self.base_label)
        self.setToolTip("Click cycle: empty = ignore, check = include, dash = exclude.")


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
        self.suggestion_thread: QThread | None = None
        self.suggestion_worker: TagSuggestionWorker | None = None
        self.pending_suggestion_token: str | None = None

        self.main_layout = QVBoxLayout(self)

        self.info_label = QLabel(tr("fetch.info", config=self.config))
        self.info_label.setWordWrap(True)
        self.main_layout.addWidget(self.info_label)

        self.preset_group = QGroupBox(tr("fetch.preset.group", config=self.config))
        self.preset_layout = QHBoxLayout(self.preset_group)

        self.preset_combo = QComboBox()
        self.preset_combo.setEditable(True)
        self.preset_combo.setMinimumWidth(260)
        self.preset_combo.currentIndexChanged.connect(self.on_preset_selected)
        self.preset_layout.addWidget(QLabel(tr("fetch.preset.label", config=self.config)))
        self.preset_layout.addWidget(self.preset_combo, stretch=1)

        self.save_preset_button = QPushButton(tr("fetch.preset.save", config=self.config))
        self.save_preset_button.clicked.connect(self.save_current_preset)
        self.preset_layout.addWidget(self.save_preset_button)

        self.delete_preset_button = QPushButton(tr("fetch.preset.delete", config=self.config))
        self.delete_preset_button.clicked.connect(self.delete_current_preset)
        self.preset_layout.addWidget(self.delete_preset_button)

        self.main_layout.addWidget(self.preset_group)

        self.source_group = QGroupBox(tr("fetch.source.group", config=self.config))
        self.source_layout = QFormLayout(self.source_group)

        self.source_mode_combo = QComboBox()
        self.source_mode_combo.addItem(tr("fetch.source.manual", config=self.config), "tags")
        self.source_mode_combo.addItem("Saved Searches", "saved_searches")
        self.source_mode_combo.currentIndexChanged.connect(self.on_source_mode_changed)
        self.source_layout.addRow(tr("fetch.source.label", config=self.config), self.source_mode_combo)

        self.main_layout.addWidget(self.source_group)

        self.manual_group = QGroupBox(tr("fetch.manual.group", config=self.config))
        self.manual_layout = QFormLayout(self.manual_group)

        self.manual_query_edit = TagQueryLineEdit()
        self.manual_query_edit.setPlaceholderText(tr("fetch.manual.placeholder", config=self.config))
        self.manual_query_edit.suggestions_requested.connect(self.request_tag_suggestions)
        self.manual_layout.addRow(tr("fetch.manual.query", config=self.config), self.manual_query_edit)

        self.main_layout.addWidget(self.manual_group)

        self.saved_search_group = QGroupBox("Saved Searches")
        self.saved_search_layout = QFormLayout(self.saved_search_group)

        self.saved_search_label_edit = QLineEdit()
        self.saved_search_label_edit.setPlaceholderText(tr("fetch.saved.label_placeholder", config=self.config))
        self.saved_search_layout.addRow("Label:", self.saved_search_label_edit)

        self.saved_search_query_edit = QLineEdit()
        self.saved_search_query_edit.setPlaceholderText(tr("fetch.saved.query_placeholder", config=self.config))
        self.saved_search_layout.addRow(tr("fetch.saved.query_filter", config=self.config), self.saved_search_query_edit)

        self.saved_search_hint = QLabel(tr("fetch.saved.hint", config=self.config))
        self.saved_search_hint.setWordWrap(True)
        self.saved_search_layout.addRow(tr("common.hint", config=self.config), self.saved_search_hint)

        self.main_layout.addWidget(self.saved_search_group)

        self.rating_group = QGroupBox(tr("fetch.rating.group", config=self.config))
        self.rating_layout = QHBoxLayout(self.rating_group)
        self.rating_layout.addWidget(QLabel(tr("fetch.rating.click_state", config=self.config)))
        self.rating_boxes: dict[str, RatingTriStateBox] = {}
        for code, label in RATING_FILTERS:
            box = RatingTriStateBox(code, label)
            self.rating_boxes[code] = box
            self.rating_layout.addWidget(box)
        self.rating_layout.addStretch(1)
        self.main_layout.addWidget(self.rating_group)

        self.options_group = QGroupBox(tr("fetch.options.group", config=self.config))
        self.options_layout = QFormLayout(self.options_group)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 200)
        self.limit_spin.setValue(int(config.get("limit", 100)))
        self.limit_spin.setKeyboardTracking(False)
        self.options_layout.addRow(tr("fetch.options.api_limit", config=self.config), self.limit_spin)

        self.max_posts_per_query_spin = QSpinBox()
        self.max_posts_per_query_spin.setRange(1, 100000)
        self.max_posts_per_query_spin.setValue(int(config.get("max_posts_per_query", 200)))
        self.max_posts_per_query_spin.setKeyboardTracking(False)
        self.max_posts_per_query_spin.setToolTip(tr("fetch.options.max_posts_tip", config=self.config))
        self.options_layout.addRow(tr("fetch.options.max_posts", config=self.config), self.max_posts_per_query_spin)

        self.min_unknown_per_query_spin = QSpinBox()
        self.min_unknown_per_query_spin.setRange(0, 100000)
        self.min_unknown_per_query_spin.setValue(int(config.get("min_unknown_posts_per_query", 0) or 0))
        self.min_unknown_per_query_spin.setKeyboardTracking(False)
        self.min_unknown_per_query_spin.setToolTip(tr("fetch.options.min_unknown_tip", config=self.config))
        self.options_layout.addRow(tr("fetch.options.min_unknown", config=self.config), self.min_unknown_per_query_spin)

        self.max_total_posts_spin = QSpinBox()
        self.max_total_posts_spin.setRange(1, 100000)
        self.max_total_posts_spin.setValue(int(config.get("max_total_posts", 500)))
        self.max_total_posts_spin.setKeyboardTracking(False)
        self.options_layout.addRow(tr("fetch.options.max_total", config=self.config), self.max_total_posts_spin)

        self.main_layout.addWidget(self.options_group)

        self.button_row = QHBoxLayout()

        self.fetch_button = QPushButton(tr("fetch.start", config=self.config))
        self.fetch_button.clicked.connect(self.start_fetch)
        self.button_row.addWidget(self.fetch_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat(tr("fetch.progress.running", config=self.config))
        self.button_row.addWidget(self.progress_bar, stretch=1)

        self.fetch_progress_label = QLabel("")
        self.fetch_progress_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.fetch_progress_label.setStyleSheet("QLabel { color: #cccccc; }")
        self.fetch_progress_label.setVisible(False)
        self.button_row.addWidget(self.fetch_progress_label, stretch=2)

        self.button_row.addStretch(1)
        self.main_layout.addLayout(self.button_row)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(180)
        self.main_layout.addWidget(self.log_text, stretch=1)

        # Tag suggestions are a potentially expensive GROUP BY query over post_tags.
        # Do not load this at application startup; load it only when the search field is actually used.
        # Apparently doing work only when needed still counts as innovation.
        self.load_presets()
        self.load_initial_values()
        self.on_source_mode_changed()

    def request_tag_suggestions(self, token: str) -> None:
        token = str(token or "").strip()
        if len(token) < 2:
            return

        if self.suggestion_thread is not None:
            self.pending_suggestion_token = token
            return

        self.start_tag_suggestion_worker(token)

    def start_tag_suggestion_worker(self, token: str) -> None:
        database_file = Path(str(self.config["database_file"]))
        self.suggestion_thread = QThread(self)
        self.suggestion_worker = TagSuggestionWorker(database_file, token, limit=120)
        self.suggestion_worker.moveToThread(self.suggestion_thread)
        self.suggestion_thread.started.connect(self.suggestion_worker.run)
        self.suggestion_worker.finished.connect(self.on_tag_suggestions_loaded)
        self.suggestion_worker.failed.connect(self.on_tag_suggestions_failed)
        self.suggestion_worker.finished.connect(self.suggestion_thread.quit)
        self.suggestion_worker.failed.connect(self.suggestion_thread.quit)
        self.suggestion_thread.finished.connect(self.cleanup_suggestion_thread)
        self.suggestion_thread.start()

    def on_tag_suggestions_loaded(self, token: str, tags: list[str]) -> None:
        self.manual_query_edit.set_tag_suggestions(token, tags)

    def on_tag_suggestions_failed(self, token: str, traceback_text: str) -> None:
        self.log_text.append(tr("fetch.suggestions.failed", config=self.config, token=token))
        if bool(self.config.get("debug_startup")):
            self.log_text.append(traceback_text)

    def cleanup_suggestion_thread(self) -> None:
        self.suggestion_thread = None
        self.suggestion_worker = None
        pending = self.pending_suggestion_token
        self.pending_suggestion_token = None
        if pending and pending != self.manual_query_edit.current_token():
            pending = self.manual_query_edit.current_token()
        if pending and len(pending) >= 2 and self.manual_query_edit.hasFocus():
            self.start_tag_suggestion_worker(pending)

    def load_presets(self) -> None:
        current = self.preset_combo.currentText()
        self.preset_combo.blockSignals(True)
        try:
            self.preset_combo.clear()
            self.preset_combo.addItem("", "")
            for row in self.db.list_fetch_presets():
                name = str(row["name"])
                self.preset_combo.addItem(name, name)
            if current:
                index = self.preset_combo.findText(current)
                if index >= 0:
                    self.preset_combo.setCurrentIndex(index)
                else:
                    self.preset_combo.setEditText(current)
        finally:
            self.preset_combo.blockSignals(False)

    def load_initial_values(self) -> None:
        last_payload = self.load_last_fetch_payload()
        if last_payload:
            self.apply_payload(last_payload)
        else:
            self.manual_query_edit.setText(str(self.config.get("search_tags", "") or ""))
            self.saved_search_label_edit.setText(", ".join(str(v) for v in self.config.get("saved_search_labels", []) or []))
            self.saved_search_query_edit.setText(", ".join(str(v) for v in self.config.get("saved_search_queries", []) or []))
            mode = "saved_searches" if bool(self.config.get("use_saved_searches", False)) else "tags"
            index = self.source_mode_combo.findData(mode)
            if index >= 0:
                self.source_mode_combo.setCurrentIndex(index)

    def load_last_fetch_payload(self) -> dict[str, Any] | None:
        raw = self.db.get_app_setting("fetch.last_payload")
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def save_last_fetch_payload(self) -> None:
        self.db.set_app_setting("fetch.last_payload", json.dumps(self.current_payload(), ensure_ascii=False, sort_keys=True))

    def on_preset_selected(self, *_args: Any) -> None:
        name = self.current_preset_name()
        if not name:
            return
        payload = self.db.get_fetch_preset(name)
        if payload is not None:
            self.apply_payload(payload)

    def current_preset_name(self) -> str:
        return self.preset_combo.currentText().strip()

    def current_payload(self) -> dict[str, Any]:
        return {
            "source_mode": self.selected_source_mode(),
            "manual_query": self.manual_query_edit.text().strip(),
            "saved_search_labels": self.saved_search_label_edit.text().strip(),
            "saved_search_queries": self.saved_search_query_edit.text().strip(),
            "rating_states": self.rating_states(),
            "limit": int(self.limit_spin.value()),
            "max_posts_per_query": int(self.max_posts_per_query_spin.value()),
            "min_unknown_posts_per_query": int(self.min_unknown_per_query_spin.value()),
            "max_total_posts": int(self.max_total_posts_spin.value()),
        }

    def apply_payload(self, payload: dict[str, Any]) -> None:
        mode = str(payload.get("source_mode") or "tags")
        index = self.source_mode_combo.findData(mode)
        if index >= 0:
            self.source_mode_combo.setCurrentIndex(index)

        self.manual_query_edit.setText(str(payload.get("manual_query") or ""))
        self.saved_search_label_edit.setText(str(payload.get("saved_search_labels") or ""))
        self.saved_search_query_edit.setText(str(payload.get("saved_search_queries") or ""))

        states = payload.get("rating_states", {})
        if isinstance(states, dict):
            self.set_rating_states({str(k): str(v) for k, v in states.items()})

        self.limit_spin.setValue(int(payload.get("limit") or self.config.get("limit", 100)))
        self.max_posts_per_query_spin.setValue(int(payload.get("max_posts_per_query") or self.config.get("max_posts_per_query", 200)))
        self.min_unknown_per_query_spin.setValue(
            int(payload.get("min_unknown_posts_per_query") or self.config.get("min_unknown_posts_per_query", 0) or 0)
        )
        self.max_total_posts_spin.setValue(int(payload.get("max_total_posts") or self.config.get("max_total_posts", 500)))
        self.on_source_mode_changed()

    def save_current_preset(self) -> None:
        name = self.current_preset_name()
        if not name:
            QMessageBox.warning(self, tr("fetch.preset.save_title", config=self.config), tr("fetch.preset.name_missing", config=self.config))
            return
        try:
            self.db.save_fetch_preset(name, self.current_payload())
            self.save_last_fetch_payload()
            self.load_presets()
        except Exception as exc:
            QMessageBox.critical(self, tr("fetch.preset.save_title", config=self.config), str(exc))
            return
        QMessageBox.information(self, tr("fetch.preset.save_title", config=self.config), tr("fetch.preset.saved", config=self.config, name=name))

    def delete_current_preset(self) -> None:
        name = self.current_preset_name()
        if not name:
            return
        if QMessageBox.question(self, tr("fetch.preset.delete_title", config=self.config), tr("fetch.preset.delete_confirm", config=self.config, name=name)) != QMessageBox.Yes:
            return
        self.db.delete_fetch_preset(name)
        self.load_presets()

    def on_source_mode_changed(self, *_args: Any) -> None:
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

    def rating_states(self) -> dict[str, str]:
        return {code: box.rating_state() for code, box in self.rating_boxes.items()}

    def set_rating_states(self, states: dict[str, str]) -> None:
        for code, box in self.rating_boxes.items():
            box.set_rating_state(states.get(code, RATING_STATE_IGNORE))

    def build_rating_clause(self) -> str:
        states = self.rating_states()
        includes = [code for code, state in states.items() if state == RATING_STATE_INCLUDE]
        excludes = [code for code, state in states.items() if state == RATING_STATE_EXCLUDE]

        parts: list[str] = []
        if includes:
            include_terms = [f"rating:{code}" for code in includes]
            if len(include_terms) == 1:
                parts.append(include_terms[0])
            else:
                parts.append("( " + " or ".join(include_terms) + " )")

        for code in excludes:
            parts.append(f"-rating:{code}")

        return " ".join(parts).strip()

    def append_rating_clause(self, query: str) -> str:
        clause = self.build_rating_clause()
        if not clause:
            return query.strip()
        base = query.strip()
        return f"{base} {clause}".strip()

    def build_fetch_config(self) -> dict[str, Any]:
        fetch_config = copy.deepcopy(self.config)

        fetch_config["limit"] = int(self.limit_spin.value())
        fetch_config["max_posts_per_query"] = int(self.max_posts_per_query_spin.value())
        fetch_config["min_unknown_posts_per_query"] = int(self.min_unknown_per_query_spin.value())
        fetch_config["max_total_posts"] = int(self.max_total_posts_spin.value())

        mode = self.selected_source_mode()
        rating_clause = self.build_rating_clause()

        if mode == "tags":
            query = self.manual_query_edit.text().strip()
            query = self.append_rating_clause(query)
            if not query:
                raise ValueError(tr("fetch.error.empty_manual_query", config=self.config))

            fetch_config["use_saved_searches"] = False
            fetch_config["search_tags"] = query
            fetch_config["saved_search_labels"] = []
            fetch_config["saved_search_queries"] = []
            fetch_config["saved_search_extra_tags"] = ""
            return fetch_config

        labels = self.split_csv_text(self.saved_search_label_edit.text())
        queries = self.split_csv_text(self.saved_search_query_edit.text())

        if not labels:
            raise ValueError(tr("fetch.error.missing_saved_label", config=self.config))

        fetch_config["use_saved_searches"] = True
        fetch_config["search_tags"] = ""
        fetch_config["saved_search_labels"] = labels
        fetch_config["saved_search_queries"] = queries
        fetch_config["saved_search_extra_tags"] = rating_clause

        return fetch_config

    def start_fetch(self) -> None:
        if self.thread is not None:
            QMessageBox.information(self, tr("fetch.already_running.title", config=self.config), tr("fetch.already_running.message", config=self.config))
            return

        try:
            fetch_config = self.build_fetch_config()
        except Exception as exc:
            QMessageBox.warning(self, tr("fetch.invalid_config.title", config=self.config), str(exc))
            return

        self.save_last_fetch_payload()
        self.fetch_button.setEnabled(False)
        self.save_preset_button.setEnabled(False)
        self.delete_preset_button.setEnabled(False)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(tr("fetch.progress.starting", config=self.config))
        self.progress_bar.setVisible(True)
        self.fetch_progress_label.setText(tr("fetch.progress.prepare_queries", config=self.config))
        self.fetch_progress_label.setVisible(True)
        self.log_text.append(tr("fetch.log.starting", config=self.config))
        self.fetch_started.emit()

        self.thread = QThread(self)
        self.worker = FetchWorker(fetch_config)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.log_text.append)
        self.worker.progress.connect(self.on_fetch_progress)
        self.worker.finished.connect(self.on_fetch_finished)
        self.worker.failed.connect(self.on_fetch_failed)

        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.cleanup_thread)

        self.thread.start()


    def on_fetch_progress(self, progress: object) -> None:
        if not isinstance(progress, FetchProgress):
            return

        planned_total = max(1, int(progress.planned_total or 1))
        seen_total = max(0, int(progress.seen_total or 0))
        target_unknown = max(0, int(getattr(progress, "target_unknown_for_query", 0) or 0))
        inserted_total = max(0, int(progress.inserted_posts or 0))
        inserted_for_query = max(0, int(getattr(progress, "inserted_for_query", 0) or 0))

        if target_unknown > 0:
            self.progress_bar.setRange(0, planned_total)
            self.progress_bar.setValue(min(inserted_total, planned_total))
        else:
            self.progress_bar.setRange(0, planned_total)
            self.progress_bar.setValue(min(seen_total, planned_total))

        query_index = int(progress.query_index or 0)
        query_total = int(progress.query_total or 0)
        query_text = progress.query.strip()
        query_word = tr("fetch.progress.query", "Query", config=self.config)
        post_word = tr("fetch.progress.post", "Post", config=self.config)
        query_part = f"{query_word} {query_index}/{query_total}" if query_total else f"{query_word} …"
        known_part = f"{tr('fetch.progress.known', 'Known', config=self.config)}: {int(progress.known_posts or 0)}"
        inserted_part = f"{tr('fetch.progress.new', 'New', config=self.config)}: {inserted_total}"
        thumb_part = f"{tr('fetch.progress.thumbs', 'Thumbs', config=self.config)}: {int(progress.cached_thumbnails or 0)}"

        if target_unknown > 0:
            post_part = f"{tr('fetch.progress.unknown_query', 'Unknown this query', config=self.config)}: {inserted_for_query}/{target_unknown}"
            checked_part = f"{tr('fetch.progress.checked', 'Checked', config=self.config)}: {seen_total}"
            self.progress_bar.setFormat(f"{query_part} | {post_part} | {known_part}")
            detail = f"{query_part} | {post_part} | {checked_part} | {known_part} | {inserted_part} | {thumb_part}"
        else:
            post_part = f"{post_word} {seen_total}/{planned_total}"
            self.progress_bar.setFormat(f"{query_part} | {post_part} | {known_part}")
            detail = f"{query_part} | {post_part} | {known_part} | {inserted_part} | {thumb_part}"

        if query_text:
            detail += f" | {query_text[:90]}"
        self.fetch_progress_label.setText(detail)
        self.fetch_progress_label.setToolTip(query_text)
        self.fetch_progress_label.setVisible(True)

    def format_fetch_summary(self, result: object) -> str:
        queries = int(getattr(result, "queries", 0) or 0)
        processed_queries = int(getattr(result, "processed_queries", queries) or 0)
        seen_posts = int(getattr(result, "seen_posts", 0) or 0)
        inserted_posts = int(getattr(result, "inserted_posts", 0) or 0)
        known_posts = int(getattr(result, "updated_posts", 0) or 0)
        cached_thumbnails = int(getattr(result, "cached_thumbnails", 0) or 0)
        target_unknown_per_query = int(getattr(result, "target_unknown_per_query", 0) or 0)
        target_unknown_total = int(getattr(result, "target_unknown_total", 0) or 0)

        query_label = tr("fetch.summary.queries", "Queries", config=self.config)
        if queries:
            query_line = f"{query_label}: {processed_queries}/{queries}"
        else:
            query_line = f"{query_label}: ?"

        new_unknown_line = f"  {tr('fetch.summary.new_unknown', 'New / unknown', config=self.config)}: {inserted_posts}"
        if target_unknown_per_query > 0:
            new_unknown_line += (
                f" / {tr('fetch.summary.target', 'target', config=self.config)} {target_unknown_total} "
                f"({target_unknown_per_query} {tr('fetch.summary.per_query', 'per query', config=self.config)})"
            )

        lines = [
            tr("fetch.summary.title", "Fetch summary", config=self.config),
            f"  {query_line}",
            f"  {tr('fetch.summary.posts_checked', 'Posts checked', config=self.config)}: {seen_posts}",
            new_unknown_line,
            f"  {tr('fetch.summary.known_updated', 'Known updated', config=self.config)}: {known_posts}",
            f"  {tr('fetch.summary.thumbnails', 'Thumbnails', config=self.config)}: {cached_thumbnails}",
        ]

        llm_input = int(getattr(result, "llm_input_posts", 0) or 0)
        llm_candidates = int(getattr(result, "llm_candidate_posts", 0) or 0)
        llm_skipped = int(getattr(result, "llm_skipped_posts", 0) or 0)
        llm_batches = int(getattr(result, "llm_batches_total", 0) or 0)
        llm_payloads = int(getattr(result, "llm_payloads_prepared", 0) or 0)
        llm_sent = int(getattr(result, "llm_requests_sent", 0) or 0)
        llm_saved = int(getattr(result, "llm_decisions_saved", 0) or 0)
        llm_reason = str(getattr(result, "llm_skipped_reason", "") or "")
        if llm_input or llm_candidates or llm_payloads or llm_sent or llm_saved or llm_reason:
            lines.append(
                "  "
                + tr(
                    "fetch.summary.llm",
                    "LLM: input {input}, candidates {candidates}, skipped {skipped}, batches {batches}, payloads {payloads}, requests {requests}, decisions saved {saved}",
                    config=self.config,
                    input=llm_input,
                    candidates=llm_candidates,
                    skipped=llm_skipped,
                    batches=llm_batches,
                    payloads=llm_payloads,
                    requests=llm_sent,
                    saved=llm_saved,
                )
            )
            batch_summaries = getattr(result, "llm_batch_summaries", []) or []
            for batch in batch_summaries[:5]:
                post_ids = batch.get("post_ids", []) if isinstance(batch, dict) else []
                id_text = ", ".join(str(post_id) for post_id in post_ids[:12])
                if len(post_ids) > 12:
                    id_text += ", ..."
                lines.append(
                    "  "
                    + tr(
                        "fetch.summary.llm_batch",
                        "LLM batch {index}/{total}: {count} posts ({ids})",
                        config=self.config,
                        index=batch.get("index"),
                        total=batch.get("total"),
                        count=batch.get("post_count"),
                        ids=id_text,
                    )
                )
            if len(batch_summaries) > 5:
                lines.append(
                    "  "
                    + tr(
                        "fetch.summary.llm_batches_more",
                        "LLM batches: {count} more hidden",
                        config=self.config,
                        count=len(batch_summaries) - 5,
                    )
                )
            if llm_reason:
                lines.append(
                    "  "
                    + tr("fetch.summary.llm_note", "LLM note: {note}", config=self.config, note=llm_reason)
                )
        llm_errors = getattr(result, "llm_errors", []) or []
        for error in llm_errors[:3]:
            lines.append(
                "  "
                + tr("fetch.summary.llm_error", "LLM error: {error}", config=self.config, error=error)
            )
        return "\n".join(lines)

    def on_fetch_finished(self, result: object) -> None:
        summary = self.format_fetch_summary(result)
        self.log_text.append(summary)
        self.fetch_button.setEnabled(True)
        self.save_preset_button.setEnabled(True)
        self.delete_preset_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.fetch_progress_label.setText(summary.replace("\n", " | "))
        self.fetch_progress_label.setToolTip(summary)
        self.fetch_progress_label.setVisible(True)
        self.fetch_finished.emit()
        self.open_preview_requested.emit()

    def on_fetch_failed(self, traceback_text: str) -> None:
        self.log_text.append(tr("fetch.failed", config=self.config))
        self.log_text.append(traceback_text)
        self.fetch_button.setEnabled(True)
        self.save_preset_button.setEnabled(True)
        self.delete_preset_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.fetch_progress_label.setVisible(False)
        self.fetch_failed_signal.emit()
        QMessageBox.critical(self, tr("fetch.failed", config=self.config), traceback_text)

    def cleanup_thread(self) -> None:
        self.thread = None
        self.worker = None
