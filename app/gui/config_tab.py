from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
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
    QFileDialog,
    QDialog,
    QDialogButtonBox,
    QTabWidget,
    QSizePolicy,
)

from app.core.config import DEFAULT_CONFIG, flatten_config
from app.core.database import Database
from app.gui.thumbnail_grid import ThumbnailGrid
from app.i18n.i18n import available_languages, language_from_config, tr
from app.services.post_import_service import PostImportService
from app.services.llm_payload_service import LLMPayloadService


SECRET_SETTING_KEYS = {"api_key"}
SECRET_DISPLAY = "********"
RAW_SETTING_COLLAPSE_KEYS = {
    "fetch.last_payload",
    "llm.last_fetch_payloads",
    "llm.last_fetch_payload_summary",
    "llm.system_prompt",
}
RAW_SETTING_VALUE_PREVIEW_LIMIT = 240

THUMBNAIL_SIZE_PRESETS = {
    "small": 180,
    "medium": 260,
    "large": 340,
    "huge": 520,
}


PREVIEW_CARD_OPTION_KEYS = [
    "show_id",
    "show_rating",
    "show_score",
    "show_parent",
    "show_status",
    "show_recommendation",
    "show_category",
    "show_path",
    "show_tags",
    "show_tag_general",
    "show_tag_character",
    "show_tag_meta",
    "show_tag_copyright",
    "show_tag_artist",
]

PREVIEW_CARD_OPTION_LABELS = {
    "show_id": "ID",
    "show_rating": "Rating",
    "show_score": "Score",
    "show_parent": "Parent / child notice",
    "show_status": "Status",
    "show_recommendation": "Preselection",
    "show_category": "Category",
    "show_path": "Path",
    "show_tags": "Show tags",
    "show_tag_general": "General tags",
    "show_tag_character": "Character tags",
    "show_tag_meta": "Meta tags",
    "show_tag_copyright": "Copyright / series tags",
    "show_tag_artist": "Artist tags",
}

PREVIEW_TAG_DISPLAY_MODES = [
    ("raw", "Raw: single tag line"),
    ("structured", "Structured: Artist / Character / Copyright / …"),
]


def is_secret_setting_key(key: str) -> bool:
    return key in SECRET_SETTING_KEYS or key.endswith(".api_key") or key.endswith("_api_key")


class LLMPayloadDialog(QDialog):
    def __init__(self, payload_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("LLM payload debug")
        self.resize(900, 650)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Debug payload: this input is shown here only and is not sent. "
            "If it looks like a JSON monster, that is because it is one."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.payload_edit = QTextEdit()
        self.payload_edit.setPlainText(payload_text)
        self.payload_edit.setReadOnly(True)
        layout.addWidget(self.payload_edit, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        copy_button = buttons.addButton("Copy to clipboard", QDialogButtonBox.ActionRole)
        copy_button.clicked.connect(self.copy_payload)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def copy_payload(self) -> None:
        QApplication.clipboard().setText(self.payload_edit.toPlainText())


class LastLLMPayloadsDialog(QDialog):
    def __init__(self, payloads: list[dict[str, Any]], summary: dict[str, Any] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.payloads = payloads
        self.summary = summary or {}
        self.setWindowTitle("Last fetch LLM payloads")
        self.resize(980, 720)

        layout = QVBoxLayout(self)

        self.summary_label = QLabel(self.build_summary_text())
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        row = QHBoxLayout()
        row.addWidget(QLabel("Payload:"))
        self.payload_combo = QComboBox()
        for index, payload in enumerate(self.payloads, start=1):
            post_ids = self.payload_post_ids(payload)
            preview_ids = ", ".join(str(post_id) for post_id in post_ids[:5])
            if len(post_ids) > 5:
                preview_ids += ", ..."
            self.payload_combo.addItem(f"{index}/{len(self.payloads)} · {len(post_ids)} Posts · {preview_ids}", index - 1)
        self.payload_combo.currentIndexChanged.connect(self.update_payload_view)
        row.addWidget(self.payload_combo, stretch=1)
        layout.addLayout(row)

        self.payload_info = QLabel("")
        self.payload_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.payload_info.setWordWrap(True)
        layout.addWidget(self.payload_info)

        self.payload_edit = QTextEdit()
        self.payload_edit.setReadOnly(True)
        layout.addWidget(self.payload_edit, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        copy_current_button = buttons.addButton("Copy current payload", QDialogButtonBox.ActionRole)
        copy_all_button = buttons.addButton("Copy all payloads", QDialogButtonBox.ActionRole)
        copy_current_button.clicked.connect(self.copy_current_payload)
        copy_all_button.clicked.connect(self.copy_all_payloads)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.update_payload_view()

    @staticmethod
    def payload_post_ids(payload: dict[str, Any]) -> list[int]:
        ids: list[int] = []
        posts = payload.get("posts", [])
        if not isinstance(posts, list):
            return ids
        for post in posts:
            if not isinstance(post, dict):
                continue
            try:
                ids.append(int(post.get("post_id")))
            except Exception:
                continue
        return ids

    def build_summary_text(self) -> str:
        if not self.summary:
            return "No batch summary was stored. Only the payloads themselves are available."
        return (
            f"Input: {int(self.summary.get('input_posts', 0) or 0)} posts · "
            f"Candidates: {int(self.summary.get('candidate_posts', 0) or 0)} · "
            f"Skipped: {int(self.summary.get('skipped_posts', 0) or 0)} · "
            f"Batches: {int(self.summary.get('batches_total', 0) or 0)} · "
            f"Payloads: {int(self.summary.get('payloads_prepared', 0) or 0)}"
        )

    def selected_payload(self) -> dict[str, Any] | None:
        if not self.payloads:
            return None
        index = self.payload_combo.currentData()
        try:
            return self.payloads[int(index)]
        except Exception:
            return self.payloads[0]

    def update_payload_view(self, *_args: Any) -> None:
        payload = self.selected_payload()
        if payload is None:
            self.payload_info.setText("No payload available.")
            self.payload_edit.clear()
            return
        post_ids = self.payload_post_ids(payload)
        batch = payload.get("batch", {}) if isinstance(payload.get("batch"), dict) else {}
        self.payload_info.setText(
            f"Batch {batch.get('index', self.payload_combo.currentIndex() + 1)}/{batch.get('total', len(self.payloads))} · "
            f"Posts: {len(post_ids)} · IDs: {', '.join(str(post_id) for post_id in post_ids)}"
        )
        self.payload_edit.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))

    def copy_current_payload(self) -> None:
        QApplication.clipboard().setText(self.payload_edit.toPlainText())

    def copy_all_payloads(self) -> None:
        QApplication.clipboard().setText(json.dumps(self.payloads, ensure_ascii=False, indent=2))


class ConfigTab(QWidget):
    config_changed = Signal()

    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db

        self.main_layout = QVBoxLayout(self)

        self.info_label = QLabel(tr("config.info", config=self.config))
        self.info_label.setWordWrap(True)
        self.main_layout.addWidget(self.info_label)

        self.config_tabs = QTabWidget()
        self.config_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.main_layout.addWidget(self.config_tabs, stretch=1)

        self.basis_page, self.basis_layout = self._make_tab_page()
        self.fetch_page, self.fetch_layout = self._make_tab_page()
        self.gui_page, self.gui_layout = self._make_tab_page()
        self.filename_page, self.filename_layout = self._make_tab_page()
        self.scoring_page, self.scoring_layout = self._make_tab_page()
        self.custom_page, self.custom_layout = self._make_tab_page()

        self.config_tabs.addTab(self.basis_page, tr("config.tabs.base", config=self.config))
        self.config_tabs.addTab(self.fetch_page, tr("config.tabs.fetch", config=self.config))
        self.config_tabs.addTab(self.gui_page, tr("config.tabs.gui", config=self.config))
        self.config_tabs.addTab(self.filename_page, tr("config.tabs.filename", config=self.config))
        self.config_tabs.addTab(self.scoring_page, tr("config.tabs.scoring", config=self.config))
        self.config_tabs.addTab(self.custom_page, tr("config.tabs.custom", config=self.config))

        self.general_group = QGroupBox(tr("config.group.paths", config=self.config))
        self.general_form = QFormLayout(self.general_group)

        self.work_dir_edit = QLineEdit(str(config.get("work_dir", "./danbooru_manager_data")))
        self.database_file_edit = QLineEdit(str(config.get("database_file", "./danbooru_manager_data/danbooru_manager.db")))
        self.default_output_dir_edit = QLineEdit(str(config.get("default_output_dir", "./danbooru_saved")))
        self.original_cache_dir_edit = QLineEdit(str(config.get("original_cache_dir", "./danbooru_manager_data/originals/cache")))
        self.active_thumbnail_dir_edit = QLineEdit(str(config.get("active_thumbnail_dir", config.get("thumbnail_dir", "./danbooru_manager_data/thumbnails/active"))))
        self.saved_thumbnail_dir_edit = QLineEdit(str(config.get("saved_thumbnail_dir", "./danbooru_manager_data/thumbnails/saved")))
        self.rejected_thumbnail_dir_edit = QLineEdit(str(config.get("rejected_thumbnail_dir", "./danbooru_manager_data/thumbnails/rejected")))

        self.general_form.addRow("work_dir:", self.work_dir_edit)
        self.general_form.addRow("database_file:", self.database_file_edit)
        self.general_form.addRow("default_output_dir:", self.default_output_dir_edit)
        self.general_form.addRow("original_cache_dir:", self.original_cache_dir_edit)
        self.general_form.addRow("active_thumbnail_dir:", self.active_thumbnail_dir_edit)
        self.general_form.addRow("saved_thumbnail_dir:", self.saved_thumbnail_dir_edit)
        self.general_form.addRow("rejected_thumbnail_dir:", self.rejected_thumbnail_dir_edit)

        self.basis_layout.addWidget(self.general_group)

        self.interface_group = QGroupBox(tr("config.group.interface", config=self.config))
        self.interface_form = QFormLayout(self.interface_group)
        self.language_combo = QComboBox()
        for language_code, language_name in available_languages():
            self.language_combo.addItem(language_name, language_code)
        current_language = language_from_config(config)
        language_index = self.language_combo.findData(current_language)
        if language_index >= 0:
            self.language_combo.setCurrentIndex(language_index)
        self.language_hint_label = QLabel(tr("config.language_hint", config=self.config))
        self.language_hint_label.setWordWrap(True)
        self.interface_form.addRow(tr("config.language", config=self.config), self.language_combo)
        self.interface_form.addRow("", self.language_hint_label)
        self.basis_layout.addWidget(self.interface_group)

        self.fetch_group = QGroupBox("Fetch")
        self.fetch_form = QFormLayout(self.fetch_group)

        self.base_url_edit = QLineEdit(str(config.get("base_url", "https://danbooru.donmai.us")))
        self.search_tags_edit = QLineEdit(str(config.get("search_tags", "order:id_desc")))
        self.saved_search_extra_tags_edit = QLineEdit(str(config.get("saved_search_extra_tags", "")))

        self.username_edit = QLineEdit(str(config.get("username") or ""))
        self.username_edit.setPlaceholderText("Danbooru username, optional")

        self.api_key_edit = QLineEdit(str(config.get("api_key") or ""))
        self.api_key_edit.setPlaceholderText("Danbooru API key, optional")
        self.api_key_edit.setEchoMode(QLineEdit.Password)

        self.show_api_key_checkbox = QCheckBox("Show API key")
        self.show_api_key_checkbox.toggled.connect(self.toggle_api_key_visibility)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 200)
        self.limit_spin.setValue(int(config.get("limit", 100)))
        self.limit_spin.setKeyboardTracking(False)

        self.fetch_form.addRow("base_url:", self.base_url_edit)
        self.fetch_form.addRow("username:", self.username_edit)
        self.fetch_form.addRow("api_key:", self.api_key_edit)
        self.fetch_form.addRow("", self.show_api_key_checkbox)
        self.fetch_form.addRow("Default search_tags:", self.search_tags_edit)
        self.fetch_form.addRow("Default saved_search_extra_tags:", self.saved_search_extra_tags_edit)
        self.fetch_form.addRow("API page limit:", self.limit_spin)

        self.fetch_layout.addWidget(self.fetch_group)

        self.gui_group = QGroupBox("GUI / Preview")
        self.gui_form = QFormLayout(self.gui_group)

        gui_config = config.get("gui", {}) or {}
        viewer_config = config.get("viewer", {}) or {}

        current_thumbnail_size = int(gui_config.get("thumbnail_size", config.get("thumbnail_size", 340)))

        self.thumbnail_preset_combo = QComboBox()
        self.thumbnail_preset_combo.addItem("Small", "small")
        self.thumbnail_preset_combo.addItem("Medium", "medium")
        self.thumbnail_preset_combo.addItem("Large", "large")
        self.thumbnail_preset_combo.addItem("Huge", "huge")
        self.thumbnail_preset_combo.addItem("Custom", "custom")
        preset_key = self._thumbnail_preset_for_size(current_thumbnail_size)
        preset_index = self.thumbnail_preset_combo.findData(preset_key)
        if preset_index >= 0:
            self.thumbnail_preset_combo.setCurrentIndex(preset_index)
        self.thumbnail_preset_combo.currentIndexChanged.connect(self.on_thumbnail_preset_changed)

        self.thumbnail_size_spin = QSpinBox()
        self.thumbnail_size_spin.setRange(80, 1200)
        self.thumbnail_size_spin.setValue(current_thumbnail_size)
        self.thumbnail_size_spin.setKeyboardTracking(False)
        self.thumbnail_size_spin.valueChanged.connect(self.update_thumbnail_preview)

        self.thumbnail_preview_host = QWidget()
        self.thumbnail_preview_host_layout = QVBoxLayout(self.thumbnail_preview_host)
        self.thumbnail_preview_host_layout.setContentsMargins(0, 0, 0, 0)
        self.thumbnail_preview_host_layout.setSpacing(6)
        self.thumbnail_preview_card: QWidget | QLabel | None = None

        self.thumbnail_preview_text = QLabel()
        self.thumbnail_preview_text.setWordWrap(True)

        self.thumbnail_min_spin = QSpinBox()
        self.thumbnail_min_spin.setRange(50, 1200)
        self.thumbnail_min_spin.setValue(int(gui_config.get("thumbnail_size_min", 120)))
        self.thumbnail_min_spin.setKeyboardTracking(False)

        self.thumbnail_max_spin = QSpinBox()
        self.thumbnail_max_spin.setRange(80, 2000)
        self.thumbnail_max_spin.setValue(int(gui_config.get("thumbnail_size_max", 700)))
        self.thumbnail_max_spin.setKeyboardTracking(False)

        self.card_width_extra_spin = QSpinBox()
        self.card_width_extra_spin.setRange(0, 500)
        self.card_width_extra_spin.setValue(int(gui_config.get("card_width_extra", 100)))
        self.card_width_extra_spin.setKeyboardTracking(False)
        self.card_width_extra_spin.valueChanged.connect(self.update_thumbnail_preview)

        self.viewer_default_view_combo = QComboBox()
        for value, label in [
            ("filtered", "Status filter"),
            ("worklist", "Worklist"),
            ("saved", "Saved"),
            ("rejected", "Rejected"),
            ("known", "Known/imported"),
            ("all", "All known posts"),
        ]:
            self.viewer_default_view_combo.addItem(label, value)

        default_view = str(viewer_config.get("default_view", "worklist"))
        index = self.viewer_default_view_combo.findData(default_view)
        if index >= 0:
            self.viewer_default_view_combo.setCurrentIndex(index)

        self.auto_advance_after_save_checkbox = QCheckBox("Auto-advance after saving")
        self.auto_advance_after_save_checkbox.setChecked(bool(viewer_config.get("auto_advance_after_save", True)))

        self.auto_advance_after_reject_checkbox = QCheckBox("Auto-advance after rejecting")
        self.auto_advance_after_reject_checkbox.setChecked(bool(viewer_config.get("auto_advance_after_reject", True)))

        preview_card_config = gui_config.get("preview_card", {}) or {}
        self.preview_card_group = QGroupBox("Preview card contents")
        self.preview_card_layout = QVBoxLayout(self.preview_card_group)
        self.preview_card_checkboxes: dict[str, QCheckBox] = {}

        for key in PREVIEW_CARD_OPTION_KEYS:
            checkbox = QCheckBox(PREVIEW_CARD_OPTION_LABELS[key])
            checkbox.setChecked(bool(preview_card_config.get(key, True)))
            checkbox.toggled.connect(self.update_thumbnail_preview)
            self.preview_card_checkboxes[key] = checkbox
            self.preview_card_layout.addWidget(checkbox)

        self.preview_tag_display_mode_combo = QComboBox()
        for value, label in PREVIEW_TAG_DISPLAY_MODES:
            self.preview_tag_display_mode_combo.addItem(label, value)
        current_tag_mode = str(preview_card_config.get("tag_display_mode", "raw") or "raw")
        tag_mode_index = self.preview_tag_display_mode_combo.findData(current_tag_mode)
        if tag_mode_index < 0:
            tag_mode_index = self.preview_tag_display_mode_combo.findData("raw")
        self.preview_tag_display_mode_combo.setCurrentIndex(max(0, tag_mode_index))
        self.preview_tag_display_mode_combo.currentIndexChanged.connect(self.update_thumbnail_preview)
        self.preview_card_layout.addWidget(QLabel("Tag display:"))
        self.preview_card_layout.addWidget(self.preview_tag_display_mode_combo)

        tag_hint = QLabel(
            "Tag types only apply when 'Show tags' is enabled. "
            "The rating is shown on the card as a full Danbooru value with color."
        )
        tag_hint.setWordWrap(True)
        self.preview_card_layout.addWidget(tag_hint)

        self.preview_layout_widget = QWidget()
        self.preview_layout = QHBoxLayout(self.preview_layout_widget)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_layout.setSpacing(16)

        self.preview_left_group = QGroupBox("Preview")
        self.preview_left_layout = QFormLayout(self.preview_left_group)
        self.preview_left_layout.addRow("Thumbnail-Preset:", self.thumbnail_preset_combo)
        self.preview_left_layout.addRow("thumbnail_size:", self.thumbnail_size_spin)
        self.preview_left_layout.addRow("Preview:", self.thumbnail_preview_host)
        self.preview_left_layout.addRow("", self.thumbnail_preview_text)

        self.preview_card_group.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.preview_left_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.preview_layout.addWidget(self.preview_left_group, stretch=1)
        self.preview_layout.addWidget(self.preview_card_group, stretch=0, alignment=Qt.AlignTop)

        self.gui_form.addRow("Preview:", self.preview_layout_widget)
        self.gui_form.addRow("thumbnail_size_min:", self.thumbnail_min_spin)
        self.gui_form.addRow("thumbnail_size_max:", self.thumbnail_max_spin)
        self.gui_form.addRow("card_width_extra:", self.card_width_extra_spin)
        self.gui_form.addRow("default_view:", self.viewer_default_view_combo)
        self.gui_form.addRow("", self.auto_advance_after_save_checkbox)
        self.gui_form.addRow("", self.auto_advance_after_reject_checkbox)

        self.gui_layout.addWidget(self.gui_group)

        self.filename_group = QGroupBox("Filename")
        self.filename_form = QFormLayout(self.filename_group)

        filename_config = config.get("filename", {}) or {}

        self.filename_pattern_edit = QLineEdit(str(filename_config.get("pattern", "%artists%_%characters%_%general%_%postid%")))

        self.filename_tags_count_spin = QSpinBox()
        self.filename_tags_count_spin.setRange(0, 100)
        self.filename_tags_count_spin.setValue(int(filename_config.get("tags_count", 8)))
        self.filename_tags_count_spin.setKeyboardTracking(False)

        self.filename_max_length_spin = QSpinBox()
        self.filename_max_length_spin.setRange(32, 255)
        self.filename_max_length_spin.setValue(int(filename_config.get("max_length", 180)))
        self.filename_max_length_spin.setKeyboardTracking(False)

        self.filename_hash_length_spin = QSpinBox()
        self.filename_hash_length_spin.setRange(1, 40)
        self.filename_hash_length_spin.setValue(int(filename_config.get("hash_length", 8)))
        self.filename_hash_length_spin.setKeyboardTracking(False)

        self.filename_tag_order_combo = QComboBox()
        self.filename_tag_order_combo.addItem("Original / previous order", False)
        self.filename_tag_order_combo.addItem("Prioritize by tag scoring", True)
        tag_order_index = self.filename_tag_order_combo.findData(bool(filename_config.get("sort_tags_by_average_rating", False)))
        if tag_order_index >= 0:
            self.filename_tag_order_combo.setCurrentIndex(tag_order_index)

        filename_help = QLabel(
            "Placeholders: %artist%/%artists%, %character%/%characters%, "
            "%copyright%/%series%, %general%, %meta%, %tags%, %postid%/%postID%, %hash%, %ext%"
        )
        filename_help.setWordWrap(True)

        self.filename_form.addRow("pattern:", self.filename_pattern_edit)
        self.filename_form.addRow("tags_count:", self.filename_tags_count_spin)
        self.filename_form.addRow("max_length:", self.filename_max_length_spin)
        self.filename_form.addRow("hash_length:", self.filename_hash_length_spin)
        self.filename_form.addRow("Tag order:", self.filename_tag_order_combo)
        self.filename_form.addRow("", filename_help)

        self.filename_layout.addWidget(self.filename_group)

        self.scoring_llm_group = QGroupBox("Scoring / LLM tag privacy")
        self.scoring_llm_form = QFormLayout(self.scoring_llm_group)

        scoring_config = config.get("scoring", {}) or {}
        llm_config = config.get("llm", {}) or {}

        self.scoring_aliases_checkbox = QCheckBox("Merge aliases for scoring")
        self.scoring_aliases_checkbox.setChecked(bool(scoring_config.get("use_aliases_for_scoring", True)))

        self.scoring_ignore_excluded_checkbox = QCheckBox("Ignore scoring exclusions")
        self.scoring_ignore_excluded_checkbox.setChecked(bool(scoring_config.get("ignore_scoring_excluded_tags", True)))

        self.llm_enabled_checkbox = QCheckBox("Enable LLM integration")
        self.llm_enabled_checkbox.setChecked(bool(llm_config.get("enabled", False)))
        self.llm_enabled_checkbox.setToolTip(
            "Master switch for LLM requests. The same setting is also shown in the Fetch tab "
            "so it can be changed while preparing a fetch preset."
        )

        self.llm_backend_combo = QComboBox()
        for value, label in [
            ("none", "No provider / build payload only"),
            ("openai_compatible", "OpenAI-compatible chat endpoint"),
            ("local", "Local LLM endpoint"),
        ]:
            self.llm_backend_combo.addItem(label, value)
        backend_index = self.llm_backend_combo.findData(str(llm_config.get("backend", "none")))
        if backend_index >= 0:
            self.llm_backend_combo.setCurrentIndex(backend_index)

        self.llm_endpoint_url_edit = QLineEdit(str(llm_config.get("endpoint_url", "") or ""))
        self.llm_endpoint_url_edit.setPlaceholderText("e.g. http://localhost:11434/... or an OpenAI-compatible /chat/completions endpoint")

        self.llm_model_edit = QLineEdit(str(llm_config.get("model", "") or ""))
        self.llm_model_edit.setPlaceholderText("Model name, e.g. a locally configured model identifier")

        self.llm_api_key_edit = QLineEdit(str(llm_config.get("api_key", "") or ""))
        self.llm_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.llm_api_key_edit.setPlaceholderText("Optional: store OpenAI/API key directly, e.g. sk-...; stays local in SQLite")
        self.llm_api_key_edit.setToolTip(
            "Optional API key. The key is masked and not written to logs, "
            "but it is stored locally in the SQLite configuration."
        )

        self.show_llm_api_key_checkbox = QCheckBox("Show LLM API key")
        self.show_llm_api_key_checkbox.toggled.connect(self.toggle_llm_api_key_visibility)

        self.llm_timeout_spin = QSpinBox()
        self.llm_timeout_spin.setRange(1, 600)
        self.llm_timeout_spin.setValue(int(llm_config.get("request_timeout_seconds", 60)))
        self.llm_timeout_spin.setSuffix(" s")
        self.llm_timeout_spin.setKeyboardTracking(False)

        self.llm_run_after_fetch_checkbox = QCheckBox("Preselect as batch after fetch")
        self.llm_run_after_fetch_checkbox.setChecked(bool(llm_config.get("run_after_fetch", False)))
        self.llm_run_after_fetch_checkbox.setToolTip(
            "When enabled, all new matching posts are prepared or scored in LLM batches after a fetch."
        )

        self.llm_skip_scored_checkbox = QCheckBox("Skip posts already scored by the LLM")
        self.llm_skip_scored_checkbox.setChecked(bool(llm_config.get("skip_already_scored", True)))
        self.llm_skip_scored_checkbox.setToolTip(
            "Prevents already scored posts from being sent to the LLM again on the next fetch. "
            "Generous of us toward API costs, somehow."
        )

        self.llm_max_posts_spin = QSpinBox()
        self.llm_max_posts_spin.setRange(1, 200)
        self.llm_max_posts_spin.setValue(int(llm_config.get("max_posts_per_request", 20)))
        self.llm_max_posts_spin.setKeyboardTracking(False)

        self.llm_max_tags_spin = QSpinBox()
        self.llm_max_tags_spin.setRange(1, 500)
        self.llm_max_tags_spin.setValue(int(llm_config.get("max_tags_per_post", 80)))
        self.llm_max_tags_spin.setKeyboardTracking(False)

        self.llm_include_preference_context_checkbox = QCheckBox("Send previous ratings as preference context")
        self.llm_include_preference_context_checkbox.setChecked(bool(llm_config.get("include_preference_context", True)))

        self.llm_max_preference_tags_spin = QSpinBox()
        self.llm_max_preference_tags_spin.setRange(0, 1000)
        self.llm_max_preference_tags_spin.setValue(int(llm_config.get("max_preference_tags", 80)))
        self.llm_max_preference_tags_spin.setKeyboardTracking(False)

        self.llm_max_positive_examples_spin = QSpinBox()
        self.llm_max_positive_examples_spin.setRange(0, 100)
        self.llm_max_positive_examples_spin.setValue(int(llm_config.get("max_positive_examples", 8)))
        self.llm_max_positive_examples_spin.setKeyboardTracking(False)

        self.llm_max_negative_examples_spin = QSpinBox()
        self.llm_max_negative_examples_spin.setRange(0, 100)
        self.llm_max_negative_examples_spin.setValue(int(llm_config.get("max_negative_examples", 8)))
        self.llm_max_negative_examples_spin.setKeyboardTracking(False)

        self.llm_max_category_examples_spin = QSpinBox()
        self.llm_max_category_examples_spin.setRange(0, 50)
        self.llm_max_category_examples_spin.setValue(int(llm_config.get("max_category_examples", 3)))
        self.llm_max_category_examples_spin.setKeyboardTracking(False)

        self.llm_max_example_tags_spin = QSpinBox()
        self.llm_max_example_tags_spin.setRange(1, 200)
        self.llm_max_example_tags_spin.setValue(int(llm_config.get("max_example_tags", 30)))
        self.llm_max_example_tags_spin.setKeyboardTracking(False)

        self.llm_system_prompt_edit = QTextEdit()
        self.llm_system_prompt_edit.setPlainText(str(llm_config.get("system_prompt", "") or ""))
        self.llm_system_prompt_edit.setPlaceholderText("Leave empty for the default prompt. Expects a short JSON decision per post.")
        self.llm_system_prompt_edit.setMinimumHeight(90)

        self.llm_tag_export_mode_combo = QComboBox()
        for value, label in [
            ("original", "Original tags (plain text)"),
            ("alias", "Alias/canonical tags (plain text, grouped)"),
            ("hashed_alias", "Hashed alias tags (privacy mode)"),
        ]:
            self.llm_tag_export_mode_combo.addItem(label, value)
        mode_index = self.llm_tag_export_mode_combo.findData(str(llm_config.get("tag_export_mode", "hashed_alias")))
        if mode_index >= 0:
            self.llm_tag_export_mode_combo.setCurrentIndex(mode_index)

        self.llm_hash_prefix_edit = QLineEdit(str(llm_config.get("hash_prefix", "tag_")))

        self.llm_hash_length_spin = QSpinBox()
        self.llm_hash_length_spin.setRange(4, 64)
        self.llm_hash_length_spin.setValue(int(llm_config.get("hash_length", 12)))
        self.llm_hash_length_spin.setKeyboardTracking(False)

        self.llm_category_export_mode_combo = QComboBox()
        for value, label in [
            ("hashed", "Hashed categories (privacy mode)"),
            ("original", "Original categories (plain text)"),
        ]:
            self.llm_category_export_mode_combo.addItem(label, value)
        category_mode_index = self.llm_category_export_mode_combo.findData(str(llm_config.get("category_export_mode", "hashed")))
        if category_mode_index >= 0:
            self.llm_category_export_mode_combo.setCurrentIndex(category_mode_index)

        self.llm_category_hash_prefix_edit = QLineEdit(str(llm_config.get("category_hash_prefix", "cat_")))

        self.llm_category_hash_length_spin = QSpinBox()
        self.llm_category_hash_length_spin.setRange(4, 64)
        self.llm_category_hash_length_spin.setValue(int(llm_config.get("category_hash_length", llm_config.get("hash_length", 12))))
        self.llm_category_hash_length_spin.setKeyboardTracking(False)

        self.llm_include_category_legend_checkbox = QCheckBox("Send category legend to LLM (less private)")
        self.llm_include_category_legend_checkbox.setChecked(bool(llm_config.get("include_category_legend", False)))

        self.llm_include_legend_checkbox = QCheckBox("Send tag legend to LLM (less private)")
        self.llm_include_legend_checkbox.setChecked(bool(llm_config.get("include_tag_legend", False)))

        llm_help = QLabel(
            "LLM debug tools are collected here: sample payload and last fetch payloads. "
            "Depending on the backend, payloads are sent automatically after fetching. Flow: original tag -> alias/canonical -> optional salted hash. "
            "Categories are anonymized separately and mapped back before saving. "
            "API keys are stored directly and locally in SQLite. "
            "The salt stays local in app_settings. Hashes are pseudonymization, not a magic invisibility cloak."
        )
        llm_help.setWordWrap(True)

        self.scoring_llm_form.addRow("Scoring:", self.scoring_aliases_checkbox)
        self.scoring_llm_form.addRow("", self.scoring_ignore_excluded_checkbox)
        self.scoring_llm_form.addRow("LLM:", self.llm_enabled_checkbox)
        self.scoring_llm_form.addRow("Backend:", self.llm_backend_combo)
        self.scoring_llm_form.addRow("Endpoint:", self.llm_endpoint_url_edit)
        self.scoring_llm_form.addRow("Model:", self.llm_model_edit)
        self.scoring_llm_form.addRow("API-Key:", self.llm_api_key_edit)
        self.scoring_llm_form.addRow("", self.show_llm_api_key_checkbox)
        self.scoring_llm_form.addRow("Timeout:", self.llm_timeout_spin)
        self.scoring_llm_form.addRow("After fetch:", self.llm_run_after_fetch_checkbox)
        self.scoring_llm_form.addRow("", self.llm_skip_scored_checkbox)
        self.scoring_llm_form.addRow("Posts/Request:", self.llm_max_posts_spin)
        self.scoring_llm_form.addRow("Tags/Post:", self.llm_max_tags_spin)
        self.scoring_llm_form.addRow("Preference context:", self.llm_include_preference_context_checkbox)
        self.scoring_llm_form.addRow("Preference tags:", self.llm_max_preference_tags_spin)
        self.scoring_llm_form.addRow("Positive examples:", self.llm_max_positive_examples_spin)
        self.scoring_llm_form.addRow("Negative examples:", self.llm_max_negative_examples_spin)
        self.scoring_llm_form.addRow("Examples/category:", self.llm_max_category_examples_spin)
        self.scoring_llm_form.addRow("Tags/example:", self.llm_max_example_tags_spin)
        self.scoring_llm_form.addRow("System-Prompt:", self.llm_system_prompt_edit)
        self.scoring_llm_form.addRow("LLM-Export:", self.llm_tag_export_mode_combo)
        self.scoring_llm_form.addRow("Hash-Prefix:", self.llm_hash_prefix_edit)
        self.scoring_llm_form.addRow("Hash length:", self.llm_hash_length_spin)
        self.scoring_llm_form.addRow("Category export:", self.llm_category_export_mode_combo)
        self.scoring_llm_form.addRow("Category prefix:", self.llm_category_hash_prefix_edit)
        self.scoring_llm_form.addRow("Category hash length:", self.llm_category_hash_length_spin)
        self.scoring_llm_form.addRow("", self.llm_include_category_legend_checkbox)
        self.scoring_llm_form.addRow("", self.llm_include_legend_checkbox)

        self.llm_debug_buttons_row = QHBoxLayout()
        self.llm_sample_payload_button = QPushButton("LLM payload sample post")
        self.llm_sample_payload_button.setToolTip("Builds a debug payload for the GUI preview sample post ID. Nothing is sent.")
        self.llm_sample_payload_button.clicked.connect(self.show_llm_payload_for_sample_post)
        self.llm_debug_buttons_row.addWidget(self.llm_sample_payload_button)

        self.last_llm_payloads_button = QPushButton("Last fetch LLM payloads")
        self.last_llm_payloads_button.setToolTip("Shows the LLM batch payloads most recently prepared after a fetch, including post IDs.")
        self.last_llm_payloads_button.clicked.connect(self.show_last_fetch_llm_payloads)
        self.llm_debug_buttons_row.addWidget(self.last_llm_payloads_button)
        self.llm_debug_buttons_row.addStretch(1)
        self.scoring_llm_form.addRow("LLM debug:", self.llm_debug_buttons_row)
        self.scoring_llm_form.addRow("", llm_help)

        self.scoring_layout.addWidget(self.scoring_llm_group)

        self.workflow_group = QGroupBox("Workflow")
        self.workflow_form = QFormLayout(self.workflow_group)

        workflow_config = config.get("workflow", {}) or {}

        self.worklist_statuses_edit = QLineEdit(
            ", ".join(str(v) for v in workflow_config.get("worklist_statuses", ["new", "potential"]))
        )

        self.rejected_retention_spin = QSpinBox()
        self.rejected_retention_spin.setRange(1, 3650)
        self.rejected_retention_spin.setValue(int(workflow_config.get("rejected_thumbnail_retention_days", 7)))
        self.rejected_retention_spin.setKeyboardTracking(False)

        self.workflow_form.addRow("worklist_statuses:", self.worklist_statuses_edit)
        self.workflow_form.addRow("rejected_thumbnail_retention_days:", self.rejected_retention_spin)

        self.basis_layout.addWidget(self.workflow_group)

        self.preview_sample_group = QGroupBox("GUI preview sample post")
        self.preview_sample_form = QFormLayout(self.preview_sample_group)

        self.preview_sample_post_id_spin = QSpinBox()
        self.preview_sample_post_id_spin.setRange(1, 2_147_483_647)
        self.preview_sample_post_id_spin.setValue(int(config.get("gui", {}).get("preview_sample_post_id", config.get("preview_sample_post_id", 1)) or 1))
        self.preview_sample_post_id_spin.setKeyboardTracking(False)
        self.preview_sample_post_id_spin.valueChanged.connect(self.on_preview_sample_post_id_changed)

        self.preview_sample_fetch_button = QPushButton("Load/update sample post")
        self.preview_sample_fetch_button.clicked.connect(self.fetch_preview_sample_post)

        self.preview_sample_status_label = QLabel(
            "The sample post is fetched from Danbooru only when you press the button and is then shown locally from the DB/thumbnail file."
        )
        self.preview_sample_status_label.setWordWrap(True)

        self.preview_sample_form.addRow("Danbooru post ID:", self.preview_sample_post_id_spin)
        self.preview_sample_form.addRow("", self.preview_sample_fetch_button)
        self.preview_sample_form.addRow("", self.preview_sample_status_label)
        self.custom_layout.addWidget(self.preview_sample_group)

        self.raw_group = QGroupBox(tr("config.raw_settings.title", "Raw app_settings", config=self.config))
        self.raw_layout = QVBoxLayout(self.raw_group)

        self.raw_hint_label = QLabel(
            tr(
                "config.raw_settings.hint",
                "Diagnostic view only. Large debug payloads and prompts are collapsed here; edit them in the dedicated fields above.",
                config=self.config,
            )
        )
        self.raw_hint_label.setWordWrap(True)
        self.raw_layout.addWidget(self.raw_hint_label)

        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setMinimumHeight(120)
        self.raw_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.raw_layout.addWidget(self.raw_text, stretch=1)

        self.raw_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.custom_layout.addWidget(self.raw_group, stretch=1)

        self.basis_layout.addStretch(1)
        self.fetch_layout.addStretch(1)
        self.gui_layout.addStretch(1)
        self.filename_layout.addStretch(1)
        self.scoring_layout.addStretch(1)

        self.button_row = QHBoxLayout()

        self.save_button = QPushButton(tr("config.save", config=self.config))
        self.save_button.clicked.connect(self.save_config)
        self.button_row.addWidget(self.save_button)

        self.reload_button = QPushButton(tr("config.reload_sql", config=self.config))
        self.reload_button.clicked.connect(self.reload_from_sql)
        self.button_row.addWidget(self.reload_button)

        self.runtime_reload_button = QPushButton(tr("config.reset_form", config=self.config))
        self.runtime_reload_button.clicked.connect(self.reload_from_runtime)
        self.button_row.addWidget(self.runtime_reload_button)

        self.export_button = QPushButton(tr("config.export", config=self.config))
        self.export_button.clicked.connect(self.export_configuration)
        self.button_row.addWidget(self.export_button)

        self.import_button = QPushButton(tr("config.import", config=self.config))
        self.import_button.clicked.connect(self.import_configuration)
        self.button_row.addWidget(self.import_button)

        self.reset_defaults_button = QPushButton(tr("config.reset_defaults", config=self.config))
        self.reset_defaults_button.clicked.connect(self.reset_sql_config_to_defaults)
        self.button_row.addWidget(self.reset_defaults_button)

        self.button_row.addStretch(1)
        self.main_layout.addLayout(self.button_row)

        self.apply_sql_settings_to_runtime()
        self.reload_from_runtime()
        self.on_thumbnail_preset_changed()
        self.refresh_raw_settings()


    def _make_tab_page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(page)
        return page, layout

    def _thumbnail_preset_for_size(self, size: int) -> str:
        for key, preset_size in THUMBNAIL_SIZE_PRESETS.items():
            if int(size) == int(preset_size):
                return key
        return "custom"

    def on_thumbnail_preset_changed(self) -> None:
        preset = str(self.thumbnail_preset_combo.currentData() or "custom")
        is_custom = preset == "custom"
        self.thumbnail_size_spin.setVisible(is_custom)
        thumbnail_size_label = None
        if hasattr(self, "preview_left_layout"):
            thumbnail_size_label = self.preview_left_layout.labelForField(self.thumbnail_size_spin)
        if thumbnail_size_label is None:
            thumbnail_size_label = self.gui_form.labelForField(self.thumbnail_size_spin)
        if thumbnail_size_label is not None:
            thumbnail_size_label.setVisible(is_custom)
        if not is_custom:
            size = THUMBNAIL_SIZE_PRESETS.get(preset, 340)
            if self.thumbnail_size_spin.value() != size:
                self.thumbnail_size_spin.blockSignals(True)
                self.thumbnail_size_spin.setValue(size)
                self.thumbnail_size_spin.blockSignals(False)
        self.update_thumbnail_preview()

    def update_thumbnail_preview(self) -> None:
        size = int(self.thumbnail_size_spin.value())
        card_width_extra = int(self.card_width_extra_spin.value()) if hasattr(self, "card_width_extra_spin") else 100
        card_width = size + card_width_extra

        self._clear_thumbnail_preview_card()

        post_id = self._current_preview_sample_post_id()
        row = self.db.get_post_detail(post_id) if post_id else None

        if row is not None:
            preview_config = copy.deepcopy(self.config)
            preview_config.setdefault("gui", {})["thumbnail_size"] = size
            preview_config.setdefault("gui", {})["card_width_extra"] = card_width_extra
            preview_config.setdefault("gui", {})["preview_render_batch_size"] = 1
            preview_card_config = self.preview_card_options_from_form()
            preview_card_config["tag_display_mode"] = self.preview_tag_display_mode_from_form()
            preview_config.setdefault("gui", {})["preview_card"] = preview_card_config

            # Do not embed ThumbnailCard directly: in the real previewer the card sits
            # inside ThumbnailGrid/QScrollArea. That context affects background,
            # width, scrolling behavior, and therefore the visible layout. Direct
            # embedding looked similar, but it was exactly the kind of UI lie that
            # causes trouble later.
            grid = ThumbnailGrid(self.db, preview_config)
            grid.setFocusPolicy(Qt.NoFocus)
            grid.setMinimumWidth(card_width + 40)
            grid.setMinimumHeight(min(max(size + 260, 420), 900))
            grid.setMaximumHeight(min(max(size + 360, 520), 1000))
            grid.set_posts([row])

            self.thumbnail_preview_card = grid
            self.thumbnail_preview_host_layout.addWidget(grid, alignment=Qt.AlignLeft)
            self.thumbnail_preview_text.setText(
                f"Real preview view using ThumbnailGrid: thumbnail {size}px, "
                f"card width approx. {card_width}px. Sample post: {post_id}."
            )
        else:
            placeholder = QLabel(
                f"No local sample post for ID {post_id}.\n"
                "Load/update it in Custom (Expert)."
            )
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setMinimumSize(min(max(260, card_width), 760), 180)
            placeholder.setWordWrap(True)
            placeholder.setStyleSheet(
                "QLabel {"
                " border: 1px dashed #777;"
                " border-radius: 8px;"
                " background: #202020;"
                " color: #dddddd;"
                " padding: 12px;"
                "}"
            )
            self.thumbnail_preview_card = placeholder
            self.thumbnail_preview_host_layout.addWidget(placeholder, alignment=Qt.AlignLeft)
            self.thumbnail_preview_text.setText(
                f"Preview card not loaded locally yet. Target: thumbnail {size}px, "
                f"card width approx. {card_width}px."
            )

    def _clear_thumbnail_preview_card(self) -> None:
        widget = self.thumbnail_preview_card
        self.thumbnail_preview_card = None
        if widget is None:
            return
        self.thumbnail_preview_host_layout.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()

    def _current_preview_sample_post_id(self) -> int:
        if hasattr(self, "preview_sample_post_id_spin"):
            return int(self.preview_sample_post_id_spin.value())
        try:
            return int(self.runtime_value("gui.preview_sample_post_id", 1) or 1)
        except Exception:
            return 1

    def on_preview_sample_post_id_changed(self) -> None:
        post_id = self._current_preview_sample_post_id()
        self.set_runtime_value("gui.preview_sample_post_id", post_id)
        self.update_thumbnail_preview()

    def fetch_preview_sample_post(self) -> None:
        post_id = self._current_preview_sample_post_id()
        self.preview_sample_fetch_button.setEnabled(False)
        self.preview_sample_status_label.setText(f"Loading sample post {post_id}…")
        try:
            fetch_config = copy.deepcopy(self.config)
            # Use current form values even if they have not been saved yet.
            for key, value in self.collect_values().items():
                self._set_nested_value(fetch_config, key, value)

            service = PostImportService(fetch_config, self.db)
            post = service.api.get_post(post_id)
            service.store_post(post)
            thumbnail_path = service.thumbnail_cache.cache_thumbnail(post, force=True)
            if thumbnail_path:
                service.set_thumbnail_path(post_id, thumbnail_path)

            self.set_setting("gui.preview_sample_post_id", post_id)
            self.set_runtime_value("gui.preview_sample_post_id", post_id)
            self.db.commit()
            self.refresh_raw_settings()
            self.preview_sample_status_label.setText(
                f"Sample post {post_id} loaded. Thumbnail: {thumbnail_path or 'not available'}"
            )
            self.update_thumbnail_preview()
        except Exception as exc:
            self.preview_sample_status_label.setText(f"Error loading sample post {post_id}: {exc}")
            QMessageBox.critical(self, "Load sample post", str(exc))
        finally:
            self.preview_sample_fetch_button.setEnabled(True)

    def _set_nested_value(self, target: dict[str, Any], dotted_key: str, value: Any) -> None:
        parts = dotted_key.split(".")
        if not parts:
            return
        current: Any = target
        for part in parts[:-1]:
            child = current.get(part) if isinstance(current, dict) else None
            if not isinstance(child, dict):
                child = {}
                current[part] = child
            current = child
        if isinstance(current, dict):
            current[parts[-1]] = value

    def preview_card_options_from_form(self) -> dict[str, bool]:
        if not hasattr(self, "preview_card_checkboxes"):
            return {key: True for key in PREVIEW_CARD_OPTION_KEYS}
        return {key: checkbox.isChecked() for key, checkbox in self.preview_card_checkboxes.items()}

    def preview_tag_display_mode_from_form(self) -> str:
        if not hasattr(self, "preview_tag_display_mode_combo"):
            return "raw"
        value = str(self.preview_tag_display_mode_combo.currentData() or "raw")
        return value if value in {"raw", "structured"} else "raw"

    def set_preview_tag_display_mode_to_form(self, mode: Any) -> None:
        if not hasattr(self, "preview_tag_display_mode_combo"):
            return
        value = str(mode or "raw")
        index = self.preview_tag_display_mode_combo.findData(value)
        if index < 0:
            index = self.preview_tag_display_mode_combo.findData("raw")
        self.preview_tag_display_mode_combo.blockSignals(True)
        self.preview_tag_display_mode_combo.setCurrentIndex(max(0, index))
        self.preview_tag_display_mode_combo.blockSignals(False)

    def set_preview_card_options_to_form(self, options: dict[str, Any] | None) -> None:
        if not hasattr(self, "preview_card_checkboxes"):
            return
        configured = options or {}
        for key, checkbox in self.preview_card_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(configured.get(key, True)))
            checkbox.blockSignals(False)


    def _config_with_form_values(self) -> dict[str, Any]:
        config = copy.deepcopy(self.config)
        values = self.collect_values()
        for key, value in values.items():
            target = config
            parts = key.split(".")
            for part in parts[:-1]:
                current = target.get(part)
                if not isinstance(current, dict):
                    current = {}
                    target[part] = current
                target = current
            target[parts[-1]] = value
        return config

    def show_llm_payload_for_sample_post(self) -> None:
        post_id = int(self.preview_sample_post_id_spin.value())
        try:
            payload_config = self._config_with_form_values()
            payload = LLMPayloadService(payload_config, self.db).build_payload_for_posts([post_id])
        except Exception as exc:
            QMessageBox.critical(
                self,
                "LLM payload sample post",
                f"Payload for post {post_id} could not be built:\n{exc}",
            )
            return

        dialog = LLMPayloadDialog(json.dumps(payload, ensure_ascii=False, indent=2), self)
        dialog.exec()

    def show_last_fetch_llm_payloads(self) -> None:
        raw_payloads = self.db.get_app_setting("llm.last_fetch_payloads", "[]") or "[]"
        raw_summary = self.db.get_app_setting("llm.last_fetch_payload_summary", "{}") or "{}"
        try:
            payloads_data = json.loads(raw_payloads)
            summary_data = json.loads(raw_summary)
        except Exception as exc:
            QMessageBox.critical(self, "Latest LLM payloads", f"Stored payloads could not be read:\n{exc}")
            return

        if isinstance(payloads_data, dict):
            payloads = [payloads_data]
        elif isinstance(payloads_data, list):
            payloads = [payload for payload in payloads_data if isinstance(payload, dict)]
        else:
            payloads = []

        summary = summary_data if isinstance(summary_data, dict) else {}

        if not payloads:
            if summary:
                info = (
                    f"Input: {int(summary.get('input_posts', 0) or 0)} posts\n"
                    f"Candidates: {int(summary.get('candidate_posts', 0) or 0)}\n"
                    f"Skipped: {int(summary.get('skipped_posts', 0) or 0)}\n"
                    f"Batches: {int(summary.get('batches_total', 0) or 0)}\n"
                    f"Payloads: {int(summary.get('payloads_prepared', 0) or 0)}"
                )
                reason = str(summary.get("skipped_reason", "") or "")
                if reason:
                    info += f"\n\nNote: {reason}"
            else:
                info = "No fetch LLM payloads are stored. Start a fetch with LLM batch preparation enabled."
            QMessageBox.information(self, "Latest LLM payloads", info)
            return

        dialog = LastLLMPayloadsDialog(payloads, summary, self)
        dialog.exec()

    def toggle_api_key_visibility(self, visible: bool) -> None:
        self.api_key_edit.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)

    def toggle_llm_api_key_visibility(self, visible: bool) -> None:
        self.llm_api_key_edit.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)

    # -------------------------------------------------------------------------
    # SQL app_settings
    # -------------------------------------------------------------------------

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.db.execute(
            """
            SELECT value
            FROM app_settings
            WHERE key = ?
            """,
            (key,),
        ).fetchone()

        if row is None:
            return default

        value = row["value"]
        try:
            return json.loads(value)
        except Exception:
            return value

    def set_setting(self, key: str, value: Any) -> None:
        encoded = json.dumps(value, ensure_ascii=False)
        self.db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, encoded),
        )

    def _format_raw_setting_value(self, key: str, raw_value: Any) -> str:
        raw_text = "" if raw_value is None else str(raw_value)
        if is_secret_setting_key(key) and raw_text:
            return SECRET_DISPLAY

        if key in RAW_SETTING_COLLAPSE_KEYS and raw_text:
            return tr(
                "config.raw_settings.collapsed_value",
                "<collapsed: {chars} characters>",
                config=self.config,
                chars=len(raw_text),
            )

        single_line = raw_text.replace("\r", "\n").replace("\n", "\\n")
        if len(single_line) > RAW_SETTING_VALUE_PREVIEW_LIMIT:
            return tr(
                "config.raw_settings.truncated_value",
                "{preview}… <truncated: {chars} characters total>",
                config=self.config,
                preview=single_line[:RAW_SETTING_VALUE_PREVIEW_LIMIT],
                chars=len(raw_text),
            )
        return single_line

    def refresh_raw_settings(self) -> None:
        rows = self.db.execute(
            """
            SELECT key, value, updated_at
            FROM app_settings
            ORDER BY key ASC
            """
        ).fetchall()

        lines: list[str] = []
        for row in rows:
            key = str(row["key"])
            value = self._format_raw_setting_value(key, row["value"])
            lines.append(f"{key} = {value}    ({row['updated_at']})")

        self.raw_text.setPlainText("\n".join(lines))

    def apply_sql_settings_to_runtime(self) -> None:
        rows = self.db.execute(
            """
            SELECT key, value
            FROM app_settings
            """
        ).fetchall()

        for row in rows:
            key = str(row["key"])
            raw_value = row["value"]

            try:
                value = json.loads(raw_value)
            except Exception:
                value = raw_value

            self.set_runtime_value(key, value)

    def set_runtime_value(self, dotted_key: str, value: Any) -> None:
        parts = dotted_key.split(".")
        if not parts:
            return

        target = self.config
        for part in parts[:-1]:
            child = target.get(part)
            if not isinstance(child, dict):
                child = {}
                target[part] = child
            target = child

        target[parts[-1]] = value

    def runtime_value(self, dotted_key: str, default: Any = None) -> Any:
        parts = dotted_key.split(".")
        target: Any = self.config

        for part in parts:
            if not isinstance(target, dict) or part not in target:
                return default
            target = target[part]

        return target

    # -------------------------------------------------------------------------
    # UI <-> Runtime
    # -------------------------------------------------------------------------

    def reload_from_sql(self) -> None:
        self.apply_sql_settings_to_runtime()
        self.reload_from_runtime()
        self.on_thumbnail_preset_changed()
        self.refresh_raw_settings()

    def reload_from_runtime(self) -> None:
        language_index = self.language_combo.findData(str(self.runtime_value("ui.language", language_from_config(self.config))))
        if language_index >= 0:
            self.language_combo.setCurrentIndex(language_index)

        self.work_dir_edit.setText(str(self.runtime_value("work_dir", "./danbooru_manager_data")))
        self.database_file_edit.setText(str(self.runtime_value("database_file", "./danbooru_manager_data/danbooru_manager.db")))
        self.default_output_dir_edit.setText(str(self.runtime_value("default_output_dir", "./danbooru_saved")))
        self.original_cache_dir_edit.setText(str(self.runtime_value("original_cache_dir", "./danbooru_manager_data/originals/cache")))
        self.active_thumbnail_dir_edit.setText(str(self.runtime_value("active_thumbnail_dir", self.runtime_value("thumbnail_dir", "./danbooru_manager_data/thumbnails/active"))))
        self.saved_thumbnail_dir_edit.setText(str(self.runtime_value("saved_thumbnail_dir", "./danbooru_manager_data/thumbnails/saved")))
        self.rejected_thumbnail_dir_edit.setText(str(self.runtime_value("rejected_thumbnail_dir", "./danbooru_manager_data/thumbnails/rejected")))

        self.base_url_edit.setText(str(self.runtime_value("base_url", "https://danbooru.donmai.us")))
        self.username_edit.setText(str(self.runtime_value("username", "") or ""))
        self.api_key_edit.setText(str(self.runtime_value("api_key", "") or ""))
        self.search_tags_edit.setText(str(self.runtime_value("search_tags", "order:id_desc")))
        self.saved_search_extra_tags_edit.setText(str(self.runtime_value("saved_search_extra_tags", "")))
        self.limit_spin.setValue(int(self.runtime_value("limit", 100)))

        thumbnail_size = int(self.runtime_value("gui.thumbnail_size", 340))
        self.thumbnail_size_spin.setValue(thumbnail_size)
        preset_key = self._thumbnail_preset_for_size(thumbnail_size)
        preset_index = self.thumbnail_preset_combo.findData(preset_key)
        if preset_index >= 0:
            self.thumbnail_preset_combo.setCurrentIndex(preset_index)
        self.on_thumbnail_preset_changed()
        self.thumbnail_min_spin.setValue(int(self.runtime_value("gui.thumbnail_size_min", 120)))
        self.thumbnail_max_spin.setValue(int(self.runtime_value("gui.thumbnail_size_max", 700)))
        self.card_width_extra_spin.setValue(int(self.runtime_value("gui.card_width_extra", 100)))
        preview_card_config = self.runtime_value("gui.preview_card", {}) or {}
        self.set_preview_card_options_to_form(preview_card_config)
        self.set_preview_tag_display_mode_to_form(preview_card_config.get("tag_display_mode", "raw") if isinstance(preview_card_config, dict) else "raw")
        if hasattr(self, "preview_sample_post_id_spin"):
            self.preview_sample_post_id_spin.setValue(int(self.runtime_value("gui.preview_sample_post_id", 1) or 1))

        default_view = str(self.runtime_value("viewer.default_view", "worklist"))
        index = self.viewer_default_view_combo.findData(default_view)
        if index >= 0:
            self.viewer_default_view_combo.setCurrentIndex(index)

        self.auto_advance_after_save_checkbox.setChecked(bool(self.runtime_value("viewer.auto_advance_after_save", True)))
        self.auto_advance_after_reject_checkbox.setChecked(bool(self.runtime_value("viewer.auto_advance_after_reject", True)))

        self.filename_pattern_edit.setText(str(self.runtime_value("filename.pattern", "%artists%_%characters%_%general%_%postid%")))
        self.filename_tags_count_spin.setValue(int(self.runtime_value("filename.tags_count", 8)))
        self.filename_max_length_spin.setValue(int(self.runtime_value("filename.max_length", 180)))
        self.filename_hash_length_spin.setValue(int(self.runtime_value("filename.hash_length", 8)))
        tag_order_index = self.filename_tag_order_combo.findData(bool(self.runtime_value("filename.sort_tags_by_average_rating", False)))
        if tag_order_index >= 0:
            self.filename_tag_order_combo.setCurrentIndex(tag_order_index)

        self.scoring_aliases_checkbox.setChecked(bool(self.runtime_value("scoring.use_aliases_for_scoring", True)))
        self.scoring_ignore_excluded_checkbox.setChecked(bool(self.runtime_value("scoring.ignore_scoring_excluded_tags", True)))
        backend_index = self.llm_backend_combo.findData(str(self.runtime_value("llm.backend", "none")))
        if backend_index >= 0:
            self.llm_backend_combo.setCurrentIndex(backend_index)
        self.llm_endpoint_url_edit.setText(str(self.runtime_value("llm.endpoint_url", "") or ""))
        self.llm_model_edit.setText(str(self.runtime_value("llm.model", "") or ""))
        self.llm_api_key_edit.setText(str(self.runtime_value("llm.api_key", "") or ""))
        self.llm_timeout_spin.setValue(int(self.runtime_value("llm.request_timeout_seconds", 60)))
        self.llm_enabled_checkbox.setChecked(bool(self.runtime_value("llm.enabled", False)))
        self.llm_run_after_fetch_checkbox.setChecked(bool(self.runtime_value("llm.run_after_fetch", False)))
        self.llm_skip_scored_checkbox.setChecked(bool(self.runtime_value("llm.skip_already_scored", True)))
        self.llm_max_posts_spin.setValue(int(self.runtime_value("llm.max_posts_per_request", 20)))
        self.llm_max_tags_spin.setValue(int(self.runtime_value("llm.max_tags_per_post", 80)))
        self.llm_include_preference_context_checkbox.setChecked(bool(self.runtime_value("llm.include_preference_context", True)))
        self.llm_max_preference_tags_spin.setValue(int(self.runtime_value("llm.max_preference_tags", 80)))
        self.llm_max_positive_examples_spin.setValue(int(self.runtime_value("llm.max_positive_examples", 8)))
        self.llm_max_negative_examples_spin.setValue(int(self.runtime_value("llm.max_negative_examples", 8)))
        self.llm_max_category_examples_spin.setValue(int(self.runtime_value("llm.max_category_examples", 3)))
        self.llm_max_example_tags_spin.setValue(int(self.runtime_value("llm.max_example_tags", 30)))
        self.llm_system_prompt_edit.setPlainText(str(self.runtime_value("llm.system_prompt", "") or ""))
        mode_index = self.llm_tag_export_mode_combo.findData(str(self.runtime_value("llm.tag_export_mode", "hashed_alias")))
        if mode_index >= 0:
            self.llm_tag_export_mode_combo.setCurrentIndex(mode_index)
        self.llm_hash_prefix_edit.setText(str(self.runtime_value("llm.hash_prefix", "tag_")))
        self.llm_hash_length_spin.setValue(int(self.runtime_value("llm.hash_length", 12)))
        category_mode_index = self.llm_category_export_mode_combo.findData(str(self.runtime_value("llm.category_export_mode", "hashed")))
        if category_mode_index >= 0:
            self.llm_category_export_mode_combo.setCurrentIndex(category_mode_index)
        self.llm_category_hash_prefix_edit.setText(str(self.runtime_value("llm.category_hash_prefix", "cat_")))
        self.llm_category_hash_length_spin.setValue(int(self.runtime_value("llm.category_hash_length", self.runtime_value("llm.hash_length", 12))))
        self.llm_include_category_legend_checkbox.setChecked(bool(self.runtime_value("llm.include_category_legend", False)))
        self.llm_include_legend_checkbox.setChecked(bool(self.runtime_value("llm.include_tag_legend", False)))

        workflow_statuses = self.runtime_value("workflow.worklist_statuses", ["new", "potential"])
        if isinstance(workflow_statuses, list):
            self.worklist_statuses_edit.setText(", ".join(str(v) for v in workflow_statuses))
        else:
            self.worklist_statuses_edit.setText(str(workflow_statuses))

        self.rejected_retention_spin.setValue(int(self.runtime_value("workflow.rejected_thumbnail_retention_days", 7)))

    def collect_values(self) -> dict[str, Any]:
        statuses = [
            status.strip()
            for status in self.worklist_statuses_edit.text().split(",")
            if status.strip()
        ]

        return {
            "ui.language": str(self.language_combo.currentData() or "en"),

            "work_dir": self.work_dir_edit.text().strip(),
            "database_file": self.database_file_edit.text().strip(),
            "default_output_dir": self.default_output_dir_edit.text().strip(),
            "original_cache_dir": self.original_cache_dir_edit.text().strip(),
            "active_thumbnail_dir": self.active_thumbnail_dir_edit.text().strip(),
            "thumbnail_dir": self.active_thumbnail_dir_edit.text().strip(),
            "saved_thumbnail_dir": self.saved_thumbnail_dir_edit.text().strip(),
            "rejected_thumbnail_dir": self.rejected_thumbnail_dir_edit.text().strip(),

            "base_url": self.base_url_edit.text().strip(),
            "username": self.username_edit.text().strip() or None,
            "api_key": self.api_key_edit.text().strip() or None,
            "search_tags": self.search_tags_edit.text().strip(),
            "saved_search_extra_tags": self.saved_search_extra_tags_edit.text().strip(),
            "use_saved_searches": False,
            "limit": int(self.limit_spin.value()),

            "gui.thumbnail_size": int(self.thumbnail_size_spin.value()),
            "gui.thumbnail_size_min": int(self.thumbnail_min_spin.value()),
            "gui.thumbnail_size_max": int(self.thumbnail_max_spin.value()),
            "gui.card_width_extra": int(self.card_width_extra_spin.value()),
            "gui.preview_sample_post_id": int(self.preview_sample_post_id_spin.value()),
            "gui.preview_card.tag_display_mode": self.preview_tag_display_mode_from_form(),
            **{f"gui.preview_card.{key}": value for key, value in self.preview_card_options_from_form().items()},

            "viewer.default_view": str(self.viewer_default_view_combo.currentData()),
            "viewer.auto_advance_after_save": self.auto_advance_after_save_checkbox.isChecked(),
            "viewer.auto_advance_after_reject": self.auto_advance_after_reject_checkbox.isChecked(),

            "filename.pattern": self.filename_pattern_edit.text().strip() or "%artists%_%characters%_%general%_%postid%",
            "filename.tags_count": int(self.filename_tags_count_spin.value()),
            "filename.max_length": int(self.filename_max_length_spin.value()),
            "filename.hash_length": int(self.filename_hash_length_spin.value()),
            "filename.sort_tags_by_average_rating": bool(self.filename_tag_order_combo.currentData()),

            "scoring.use_aliases_for_scoring": self.scoring_aliases_checkbox.isChecked(),
            "scoring.ignore_scoring_excluded_tags": self.scoring_ignore_excluded_checkbox.isChecked(),
            "llm.backend": str(self.llm_backend_combo.currentData()),
            "llm.endpoint_url": self.llm_endpoint_url_edit.text().strip(),
            "llm.model": self.llm_model_edit.text().strip(),
            "llm.api_key": self.llm_api_key_edit.text().strip(),
            "llm.request_timeout_seconds": int(self.llm_timeout_spin.value()),
            "llm.enabled": self.llm_enabled_checkbox.isChecked(),
            "llm.run_after_fetch": self.llm_run_after_fetch_checkbox.isChecked(),
            "llm.skip_already_scored": self.llm_skip_scored_checkbox.isChecked(),
            "llm.after_fetch_statuses": ["new", "potential"],
            "llm.max_posts_per_request": int(self.llm_max_posts_spin.value()),
            "llm.max_tags_per_post": int(self.llm_max_tags_spin.value()),
            "llm.include_preference_context": self.llm_include_preference_context_checkbox.isChecked(),
            "llm.max_preference_tags": int(self.llm_max_preference_tags_spin.value()),
            "llm.max_positive_examples": int(self.llm_max_positive_examples_spin.value()),
            "llm.max_negative_examples": int(self.llm_max_negative_examples_spin.value()),
            "llm.max_category_examples": int(self.llm_max_category_examples_spin.value()),
            "llm.max_example_tags": int(self.llm_max_example_tags_spin.value()),
            "llm.system_prompt": self.llm_system_prompt_edit.toPlainText().strip(),
            "llm.tag_export_mode": str(self.llm_tag_export_mode_combo.currentData()),
            "llm.hash_prefix": self.llm_hash_prefix_edit.text().strip() or "tag_",
            "llm.hash_length": int(self.llm_hash_length_spin.value()),
            "llm.category_export_mode": str(self.llm_category_export_mode_combo.currentData()),
            "llm.category_hash_prefix": self.llm_category_hash_prefix_edit.text().strip() or "cat_",
            "llm.category_hash_length": int(self.llm_category_hash_length_spin.value()),
            "llm.include_category_legend": self.llm_include_category_legend_checkbox.isChecked(),
            "llm.include_tag_legend": self.llm_include_legend_checkbox.isChecked(),

            "workflow.worklist_statuses": statuses,
            "workflow.rejected_thumbnail_retention_days": int(self.rejected_retention_spin.value()),
        }

    def save_config(self) -> None:
        values = self.collect_values()

        try:
            for key, value in values.items():
                self.set_setting(key, value)
                self.set_runtime_value(key, value)

            self.db.commit()
            self.refresh_raw_settings()
            self.config_changed.emit()

        except Exception as exc:
            QMessageBox.critical(self, tr("config.save_error_title", config=self.config), str(exc))
            return

        QMessageBox.information(
            self,
            tr("config.saved_title", config=self.config),
            tr("config.saved_message", config=self.config),
        )


    # -------------------------------------------------------------------------
    # Export / Import / Defaults
    # -------------------------------------------------------------------------

    def _json_value(self, raw_value: Any) -> Any:
        if raw_value is None:
            return None
        if not isinstance(raw_value, str):
            return raw_value
        try:
            return json.loads(raw_value)
        except Exception:
            return raw_value

    def _export_payload(self) -> dict[str, Any]:
        settings_rows = self.db.execute(
            """
            SELECT key, value
            FROM app_settings
            ORDER BY key ASC
            """
        ).fetchall()
        app_settings: dict[str, Any] = {}
        for row in settings_rows:
            key = str(row["key"])
            if is_secret_setting_key(key):
                # Do not leak secrets into config exports. The UI stores them in
                # SQLite, but exports are usually copied around like cursed
                # confetti.
                app_settings[key] = SECRET_DISPLAY if row["value"] else None
            else:
                app_settings[key] = self._json_value(row["value"])

        category_rows = self.db.execute(
            """
            SELECT id, name, folder_name, output_path, hotkey, sort_order
            FROM categories
            ORDER BY sort_order ASC, name COLLATE NOCASE ASC
            """
        ).fetchall()
        categories: list[dict[str, Any]] = []
        for category in category_rows:
            rules = self.db.list_category_rules(int(category["id"]))
            categories.append(
                {
                    "name": category["name"],
                    "folder_name": category["folder_name"],
                    "output_path": category["output_path"],
                    "hotkey": category["hotkey"],
                    "sort_order": category["sort_order"],
                    "rules": [
                        {"rule_type": rule["rule_type"], "tag": rule["tag"]}
                        for rule in rules
                    ],
                }
            )

        filename_excluded_tags = [
            {"tag": row["tag"], "reason": row["reason"]}
            for row in self.db.execute(
                """
                SELECT tag, reason
                FROM filename_excluded_tags
                ORDER BY tag COLLATE NOCASE ASC
                """
            ).fetchall()
        ]
        tag_aliases = [
            {"original_tag": row["original_tag"], "alias_tag": row["alias_tag"]}
            for row in self.db.execute(
                """
                SELECT original_tag, alias_tag
                FROM tag_aliases
                ORDER BY original_tag COLLATE NOCASE ASC
                """
            ).fetchall()
        ]
        tag_scores = [
            {
                "tag": row["tag"],
                "manual_score": row["manual_score"],
                "scoring_excluded": bool(row["scoring_excluded"]),
            }
            for row in self.db.execute(
                """
                SELECT tag, manual_score, COALESCE(scoring_excluded, 0) AS scoring_excluded
                FROM tag_scores
                WHERE manual_score IS NOT NULL OR COALESCE(scoring_excluded, 0) != 0
                ORDER BY tag COLLATE NOCASE ASC
                """
            ).fetchall()
        ]

        fetch_presets = []
        for row in self.db.list_fetch_presets():
            try:
                payload = json.loads(str(row["payload"] or "{}"))
            except Exception:
                payload = {}
            fetch_presets.append(
                {
                    "name": row["name"],
                    "payload": payload,
                    "updated_at": row["updated_at"],
                }
            )

        return {
            "format": "danbooru_downloader_config_export",
            "version": 1,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "app_settings": app_settings,
            "categories": categories,
            "filename_excluded_tags": filename_excluded_tags,
            "tag_aliases": tag_aliases,
            "tag_scores": tag_scores,
            "fetch_presets": fetch_presets,
        }

    def export_configuration(self) -> None:
        default_name = f"danbooru_downloader_config_export_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Export configuration",
            default_name,
            "JSON (*.json);;All files (*)",
        )
        if not file_name:
            return

        try:
            payload = self._export_payload()
            Path(file_name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "Export configuration", str(exc))
            return

        QMessageBox.information(self, "Configuration exported", f"Export saved:\n{file_name}")

    def import_configuration(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Import configuration",
            "",
            "JSON (*.json);;All files (*)",
        )
        if not file_name:
            return

        answer = QMessageBox.question(
            self,
            "Import configuration",
            "The configuration from the JSON file will be imported into the SQLite configuration.\n"
            "Categories, filename exclusions, aliases, and manual tag weights are added/updated, not deleted.\n\n"
            "Start import?",
        )
        if answer != QMessageBox.Yes:
            return

        try:
            payload = json.loads(Path(file_name).read_text(encoding="utf-8"))
            settings = payload.get("app_settings", {}) or {}
            if isinstance(settings, list):
                settings = {str(item.get("key")): item.get("value") for item in settings if isinstance(item, dict) and item.get("key")}
            if not isinstance(settings, dict):
                raise ValueError("app_settings must be an object")

            for key, value in settings.items():
                key = str(key)
                if is_secret_setting_key(key) and value in {SECRET_DISPLAY, "", None}:
                    continue
                self.set_setting(key, value)
                self.set_runtime_value(key, value)

            for category in payload.get("categories", []) or []:
                if not isinstance(category, dict) or not category.get("name"):
                    continue
                category_id = self.db.upsert_category(
                    name=str(category["name"]),
                    folder_name=str(category.get("folder_name") or category["name"]),
                    output_path=category.get("output_path"),
                    hotkey=category.get("hotkey"),
                    sort_order=int(category.get("sort_order") or self.db.next_category_sort_order()),
                )
                for rule in category.get("rules", []) or []:
                    if isinstance(rule, dict) and rule.get("tag") and rule.get("rule_type"):
                        self.db.add_category_rule(category_id, str(rule["rule_type"]), str(rule["tag"]))

            for item in payload.get("filename_excluded_tags", []) or []:
                if isinstance(item, dict) and item.get("tag"):
                    self.db.add_filename_excluded_tag(str(item["tag"]), str(item.get("reason") or "config-import"))
                elif isinstance(item, str):
                    self.db.add_filename_excluded_tag(item, "config-import")

            for item in payload.get("tag_aliases", []) or []:
                if isinstance(item, dict) and item.get("original_tag"):
                    self.db.set_tag_alias(str(item["original_tag"]), str(item.get("alias_tag") or ""))

            for item in payload.get("tag_scores", []) or []:
                if isinstance(item, dict) and item.get("tag"):
                    tag = str(item["tag"])
                    if "manual_score" in item:
                        self.db.set_tag_manual_score(tag, item.get("manual_score"))
                    if "scoring_excluded" in item:
                        self.db.set_tag_scoring_excluded(tag, bool(item.get("scoring_excluded")))

            for item in payload.get("fetch_presets", []) or []:
                if isinstance(item, dict) and item.get("name"):
                    preset_payload = item.get("payload") or {}
                    if isinstance(preset_payload, dict):
                        self.db.save_fetch_preset(str(item["name"]), preset_payload)

            self.db.commit()
            self.reload_from_sql()
            self.config_changed.emit()
        except Exception as exc:
            QMessageBox.critical(self, "Import configuration", str(exc))
            return

        QMessageBox.information(self, "Configuration imported", "Import completed.")

    def reset_sql_config_to_defaults(self) -> None:
        answer = QMessageBox.warning(
            self,
            "Reset SQLite configuration to defaults",
            "Values in app_settings will be deleted and recreated from the internal defaults.\n"
            "Categories, tags, aliases, weights, posts, and downloads stay intact.\n\n"
            "So this is not a database nuclear strike, just configuration housekeeping. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            self.db.execute("DELETE FROM app_settings")
            default_settings = flatten_config(DEFAULT_CONFIG)
            # categories are managed in their own tables; empty defaults must not destroy existing categories.
            default_settings.pop("categories", None)
            for key, value in default_settings.items():
                self.set_setting(key, value)
                self.set_runtime_value(key, value)
            self.db.commit()
            self.reload_from_sql()
            self.config_changed.emit()
        except Exception as exc:
            QMessageBox.critical(self, "Restore defaults", str(exc))
            return

        QMessageBox.information(
            self,
            "Defaults restored",
            "SQLite configuration was reset to internal defaults.\n"
            "Some paths only take full effect after restarting.",
        )
