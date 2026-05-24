from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
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
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QTabWidget,
    QSizePolicy,
)

from app.core.config import DEFAULT_CONFIG, flatten_config
from app.core.database import Database
from app.gui.thumbnail_grid import ThumbnailGrid
from app.services.post_import_service import PostImportService


SECRET_SETTING_KEYS = {"api_key"}
SECRET_DISPLAY = "********"

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
    "show_parent": "Parent / Child-Hinweis",
    "show_status": "Status",
    "show_recommendation": "Vorauswahl",
    "show_category": "Kategorie",
    "show_path": "Pfad",
    "show_tags": "Tags anzeigen",
    "show_tag_general": "General-Tags",
    "show_tag_character": "Character-Tags",
    "show_tag_meta": "Meta-Tags",
    "show_tag_copyright": "Copyright/Serie-Tags",
    "show_tag_artist": "Artist-Tags",
}

PREVIEW_TAG_DISPLAY_MODES = [
    ("raw", "Raw: einfache Tag-Zeile"),
    ("structured", "Aufgeschlüsselt: Artist / Character / Copyright / …"),
]


def is_secret_setting_key(key: str) -> bool:
    return key in SECRET_SETTING_KEYS or key.endswith(".api_key") or key.endswith("_api_key")


class ConfigTab(QWidget):
    config_changed = Signal()

    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db

        self.main_layout = QVBoxLayout(self)

        self.info_label = QLabel(
            "Konfiguration wird in SQLite geführt. Eine YAML-Datei ist nicht mehr nötig; "
            "sie wird nur noch optional als altes Start-Overlay gelesen, wenn sie existiert."
        )
        self.info_label.setWordWrap(True)
        self.main_layout.addWidget(self.info_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)

        self.config_tabs = QTabWidget()
        self.content_layout.addWidget(self.config_tabs)

        self.basis_page, self.basis_layout = self._make_tab_page()
        self.fetch_page, self.fetch_layout = self._make_tab_page()
        self.gui_page, self.gui_layout = self._make_tab_page()
        self.filename_page, self.filename_layout = self._make_tab_page()
        self.scoring_page, self.scoring_layout = self._make_tab_page()
        self.custom_page, self.custom_layout = self._make_tab_page()

        self.config_tabs.addTab(self.basis_page, "Basis")
        self.config_tabs.addTab(self.fetch_page, "Fetch")
        self.config_tabs.addTab(self.gui_page, "GUI")
        self.config_tabs.addTab(self.filename_page, "Filename")
        self.config_tabs.addTab(self.scoring_page, "Scoring")
        self.config_tabs.addTab(self.custom_page, "Custom (Expert)")

        self.general_group = QGroupBox("Pfade / Basis")
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

        self.fetch_group = QGroupBox("Fetch")
        self.fetch_form = QFormLayout(self.fetch_group)

        self.base_url_edit = QLineEdit(str(config.get("base_url", "https://danbooru.donmai.us")))
        self.search_tags_edit = QLineEdit(str(config.get("search_tags", "order:id_desc")))
        self.saved_search_extra_tags_edit = QLineEdit(str(config.get("saved_search_extra_tags", "")))

        self.username_edit = QLineEdit(str(config.get("username") or ""))
        self.username_edit.setPlaceholderText("Danbooru-Username, optional")

        self.api_key_edit = QLineEdit(str(config.get("api_key") or ""))
        self.api_key_edit.setPlaceholderText("Danbooru API-Key, optional")
        self.api_key_edit.setEchoMode(QLineEdit.Password)

        self.show_api_key_checkbox = QCheckBox("API-Key anzeigen")
        self.show_api_key_checkbox.toggled.connect(self.toggle_api_key_visibility)

        self.legacy_saved_searches_label = QLabel(
            "Saved Searches werden im neuen Workflow ueber Fetch-Presets gesteuert. "
            "Der alte globale Schalter bleibt intern auf false, damit Presets nicht von einer Altlast ueberschrieben werden."
        )
        self.legacy_saved_searches_label.setWordWrap(True)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 200)
        self.limit_spin.setValue(int(config.get("limit", 100)))
        self.limit_spin.setKeyboardTracking(False)

        self.max_posts_per_query_spin = QSpinBox()
        self.max_posts_per_query_spin.setRange(1, 100000)
        self.max_posts_per_query_spin.setValue(int(config.get("max_posts_per_query", 500)))
        self.max_posts_per_query_spin.setKeyboardTracking(False)

        self.max_total_posts_spin = QSpinBox()
        self.max_total_posts_spin.setRange(1, 100000)
        self.max_total_posts_spin.setValue(int(config.get("max_total_posts", 1000)))
        self.max_total_posts_spin.setKeyboardTracking(False)

        self.fetch_form.addRow("base_url:", self.base_url_edit)
        self.fetch_form.addRow("username:", self.username_edit)
        self.fetch_form.addRow("api_key:", self.api_key_edit)
        self.fetch_form.addRow("", self.show_api_key_checkbox)
        self.fetch_form.addRow("Default search_tags:", self.search_tags_edit)
        self.fetch_form.addRow("Default saved_search_extra_tags:", self.saved_search_extra_tags_edit)
        self.fetch_form.addRow("Saved Searches:", self.legacy_saved_searches_label)
        self.fetch_form.addRow("limit:", self.limit_spin)
        self.fetch_form.addRow("max_posts_per_query:", self.max_posts_per_query_spin)
        self.fetch_form.addRow("max_total_posts:", self.max_total_posts_spin)

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
            ("filtered", "Status-Filter"),
            ("worklist", "Arbeitsliste"),
            ("saved", "Gespeichert"),
            ("rejected", "Aussortiert"),
            ("known", "Bekannte/importierte"),
            ("all", "Alle bekannten Posts"),
        ]:
            self.viewer_default_view_combo.addItem(label, value)

        default_view = str(viewer_config.get("default_view", "worklist"))
        index = self.viewer_default_view_combo.findData(default_view)
        if index >= 0:
            self.viewer_default_view_combo.setCurrentIndex(index)

        self.auto_advance_after_save_checkbox = QCheckBox("Nach finalem Speichern automatisch weiter")
        self.auto_advance_after_save_checkbox.setChecked(bool(viewer_config.get("auto_advance_after_save", True)))

        self.auto_advance_after_reject_checkbox = QCheckBox("Nach Ablehnen automatisch weiter")
        self.auto_advance_after_reject_checkbox.setChecked(bool(viewer_config.get("auto_advance_after_reject", True)))

        preview_card_config = gui_config.get("preview_card", {}) or {}
        self.preview_card_group = QGroupBox("Preview-Karten-Inhalte")
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
        self.preview_card_layout.addWidget(QLabel("Tag-Darstellung:"))
        self.preview_card_layout.addWidget(self.preview_tag_display_mode_combo)

        tag_hint = QLabel(
            "Die Tag-Typen wirken nur, wenn 'Tags anzeigen' aktiv ist. "
            "Das Rating wird in der Karte als ausgeschriebener Danbooru-Wert mit Farbe angezeigt."
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
        self.preview_left_layout.addRow("Vorschau:", self.thumbnail_preview_host)
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

        self.filename_group = QGroupBox("Dateiname")
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
        self.filename_tag_order_combo.addItem("Original / bisherige Reihenfolge", False)
        self.filename_tag_order_combo.addItem("Nach Tag-Scoring priorisieren", True)
        tag_order_index = self.filename_tag_order_combo.findData(bool(filename_config.get("sort_tags_by_average_rating", False)))
        if tag_order_index >= 0:
            self.filename_tag_order_combo.setCurrentIndex(tag_order_index)

        filename_help = QLabel(
            "Platzhalter: %artist%/%artists%, %character%/%characters%, "
            "%copyright%/%series%, %general%, %meta%, %tags%, %postid%/%postID%, %hash%, %ext%"
        )
        filename_help.setWordWrap(True)

        self.filename_form.addRow("pattern:", self.filename_pattern_edit)
        self.filename_form.addRow("tags_count:", self.filename_tags_count_spin)
        self.filename_form.addRow("max_length:", self.filename_max_length_spin)
        self.filename_form.addRow("hash_length:", self.filename_hash_length_spin)
        self.filename_form.addRow("Tag-Reihenfolge:", self.filename_tag_order_combo)
        self.filename_form.addRow("", filename_help)

        self.filename_layout.addWidget(self.filename_group)

        self.scoring_llm_group = QGroupBox("Scoring / LLM-Tag-Privacy")
        self.scoring_llm_form = QFormLayout(self.scoring_llm_group)

        scoring_config = config.get("scoring", {}) or {}
        llm_config = config.get("llm", {}) or {}

        self.scoring_aliases_checkbox = QCheckBox("Aliase fuer Scoring zusammenfassen")
        self.scoring_aliases_checkbox.setChecked(bool(scoring_config.get("use_aliases_for_scoring", True)))

        self.scoring_ignore_excluded_checkbox = QCheckBox("Scoring-Ausschluesse ignorieren")
        self.scoring_ignore_excluded_checkbox.setChecked(bool(scoring_config.get("ignore_scoring_excluded_tags", True)))

        self.llm_tag_export_mode_combo = QComboBox()
        for value, label in [
            ("original", "Original-Tags (Klartext)"),
            ("alias", "Alias/Canonical-Tags (Klartext, gruppiert)"),
            ("hashed_alias", "Gehashte Alias-Tags (Privacy-Modus)"),
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

        self.llm_include_legend_checkbox = QCheckBox("Tag-Legende an LLM mitsenden (weniger privat)")
        self.llm_include_legend_checkbox.setChecked(bool(llm_config.get("include_tag_legend", False)))

        llm_help = QLabel(
            "Ablauf: Original-Tag -> Alias/Canonical -> optional Salted Hash. "
            "Der Salt bleibt lokal in app_settings. Hashes sind Pseudonymisierung, kein magischer Tarnumhang."
        )
        llm_help.setWordWrap(True)

        self.scoring_llm_form.addRow("Scoring:", self.scoring_aliases_checkbox)
        self.scoring_llm_form.addRow("", self.scoring_ignore_excluded_checkbox)
        self.scoring_llm_form.addRow("LLM-Export:", self.llm_tag_export_mode_combo)
        self.scoring_llm_form.addRow("Hash-Prefix:", self.llm_hash_prefix_edit)
        self.scoring_llm_form.addRow("Hash-Laenge:", self.llm_hash_length_spin)
        self.scoring_llm_form.addRow("", self.llm_include_legend_checkbox)
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

        self.preview_sample_group = QGroupBox("GUI-Vorschau Beispielpost")
        self.preview_sample_form = QFormLayout(self.preview_sample_group)

        self.preview_sample_post_id_spin = QSpinBox()
        self.preview_sample_post_id_spin.setRange(1, 2_147_483_647)
        self.preview_sample_post_id_spin.setValue(int(config.get("gui", {}).get("preview_sample_post_id", config.get("preview_sample_post_id", 1)) or 1))
        self.preview_sample_post_id_spin.setKeyboardTracking(False)
        self.preview_sample_post_id_spin.valueChanged.connect(self.on_preview_sample_post_id_changed)

        self.preview_sample_fetch_button = QPushButton("Beispielpost laden/aktualisieren")
        self.preview_sample_fetch_button.clicked.connect(self.fetch_preview_sample_post)

        self.preview_sample_status_label = QLabel(
            "Der Beispielpost wird nur auf Knopfdruck von Danbooru geladen und danach lokal aus der DB/Thumbnail-Datei angezeigt."
        )
        self.preview_sample_status_label.setWordWrap(True)

        self.preview_sample_form.addRow("Danbooru Post-ID:", self.preview_sample_post_id_spin)
        self.preview_sample_form.addRow("", self.preview_sample_fetch_button)
        self.preview_sample_form.addRow("", self.preview_sample_status_label)
        self.custom_layout.addWidget(self.preview_sample_group)

        self.raw_group = QGroupBox("Raw app_settings")
        self.raw_layout = QVBoxLayout(self.raw_group)

        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setMinimumHeight(160)
        self.raw_layout.addWidget(self.raw_text)

        self.custom_layout.addWidget(self.raw_group)

        self.basis_layout.addStretch(1)
        self.fetch_layout.addStretch(1)
        self.gui_layout.addStretch(1)
        self.filename_layout.addStretch(1)
        self.scoring_layout.addStretch(1)
        self.custom_layout.addStretch(1)

        self.scroll.setWidget(self.content)
        self.main_layout.addWidget(self.scroll, stretch=1)

        self.button_row = QHBoxLayout()

        self.save_button = QPushButton("Speichern")
        self.save_button.clicked.connect(self.save_config)
        self.button_row.addWidget(self.save_button)

        self.reload_button = QPushButton("Aus SQL neu laden")
        self.reload_button.clicked.connect(self.reload_from_sql)
        self.button_row.addWidget(self.reload_button)

        self.runtime_reload_button = QPushButton("Formular zurücksetzen")
        self.runtime_reload_button.clicked.connect(self.reload_from_runtime)
        self.button_row.addWidget(self.runtime_reload_button)

        self.export_button = QPushButton("Konfiguration exportieren")
        self.export_button.clicked.connect(self.export_configuration)
        self.button_row.addWidget(self.export_button)

        self.import_button = QPushButton("Konfiguration importieren")
        self.import_button.clicked.connect(self.import_configuration)
        self.button_row.addWidget(self.import_button)

        self.reset_defaults_button = QPushButton("SQLite-Konfiguration auf Defaults")
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
        self.gui_form.labelForField(self.thumbnail_size_spin).setVisible(is_custom)
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

            # Nicht direkt ThumbnailCard einbetten: Im echten Previewer sitzt die Karte
            # in ThumbnailGrid/QScrollArea. Genau dieser Kontext beeinflusst Hintergrund,
            # Breite, Scroll-Verhalten und damit das sichtbare Layout. Direktes Einbetten
            # sah ähnlich aus, war aber genau die Art UI-Lüge, die später Ärger macht.
            grid = ThumbnailGrid(self.db, preview_config)
            grid.setFocusPolicy(Qt.NoFocus)
            grid.setMinimumWidth(card_width + 40)
            grid.setMinimumHeight(min(max(size + 260, 420), 900))
            grid.setMaximumHeight(min(max(size + 360, 520), 1000))
            grid.set_posts([row])

            self.thumbnail_preview_card = grid
            self.thumbnail_preview_host_layout.addWidget(grid, alignment=Qt.AlignLeft)
            self.thumbnail_preview_text.setText(
                f"Echte Preview-Ansicht mit ThumbnailGrid: Thumbnail {size}px, "
                f"Kartenbreite ca. {card_width}px. Beispielpost: {post_id}."
            )
        else:
            placeholder = QLabel(
                f"Kein lokaler Beispielpost für ID {post_id}.\n"
                "In Custom (Expert) laden/aktualisieren."
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
                f"Preview-Karte noch nicht lokal geladen. Ziel: Thumbnail {size}px, "
                f"Kartenbreite ca. {card_width}px."
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
        self.preview_sample_status_label.setText(f"Lade Beispielpost {post_id}…")
        try:
            fetch_config = copy.deepcopy(self.config)
            # Aktuelle Formularwerte nutzen, auch wenn sie noch nicht gespeichert sind.
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
                f"Beispielpost {post_id} geladen. Thumbnail: {thumbnail_path or 'nicht verfügbar'}"
            )
            self.update_thumbnail_preview()
        except Exception as exc:
            self.preview_sample_status_label.setText(f"Fehler beim Laden von Beispielpost {post_id}: {exc}")
            QMessageBox.critical(self, "Beispielpost laden", str(exc))
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

    def toggle_api_key_visibility(self, visible: bool) -> None:
        self.api_key_edit.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)

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
            value = SECRET_DISPLAY if is_secret_setting_key(key) and row["value"] else row["value"]
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
        self.max_posts_per_query_spin.setValue(int(self.runtime_value("max_posts_per_query", 500)))
        self.max_total_posts_spin.setValue(int(self.runtime_value("max_total_posts", 1000)))

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
        mode_index = self.llm_tag_export_mode_combo.findData(str(self.runtime_value("llm.tag_export_mode", "hashed_alias")))
        if mode_index >= 0:
            self.llm_tag_export_mode_combo.setCurrentIndex(mode_index)
        self.llm_hash_prefix_edit.setText(str(self.runtime_value("llm.hash_prefix", "tag_")))
        self.llm_hash_length_spin.setValue(int(self.runtime_value("llm.hash_length", 12)))
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
            "max_posts_per_query": int(self.max_posts_per_query_spin.value()),
            "max_total_posts": int(self.max_total_posts_spin.value()),

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
            "llm.tag_export_mode": str(self.llm_tag_export_mode_combo.currentData()),
            "llm.hash_prefix": self.llm_hash_prefix_edit.text().strip() or "tag_",
            "llm.hash_length": int(self.llm_hash_length_spin.value()),
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
            QMessageBox.critical(self, "Konfiguration speichern", str(exc))
            return

        QMessageBox.information(
            self,
            "Konfiguration gespeichert",
            "Konfiguration wurde in SQLite gespeichert.\n"
            "Einige Werte wirken sofort, andere erst beim nächsten Start oder neuem Fetch.",
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
            "Konfiguration exportieren",
            default_name,
            "JSON (*.json);;Alle Dateien (*)",
        )
        if not file_name:
            return

        try:
            payload = self._export_payload()
            Path(file_name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "Konfiguration exportieren", str(exc))
            return

        QMessageBox.information(self, "Konfiguration exportiert", f"Export gespeichert:\n{file_name}")

    def import_configuration(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Konfiguration importieren",
            "",
            "JSON (*.json);;Alle Dateien (*)",
        )
        if not file_name:
            return

        answer = QMessageBox.question(
            self,
            "Konfiguration importieren",
            "Die Konfiguration aus der JSON-Datei wird in die SQLite-Konfiguration übernommen.\n"
            "Kategorien, Filename-Ausschlüsse, Aliase und manuelle Tag-Gewichtungen werden ergänzt/aktualisiert, nicht gelöscht.\n\n"
            "Import starten?",
        )
        if answer != QMessageBox.Yes:
            return

        try:
            payload = json.loads(Path(file_name).read_text(encoding="utf-8"))
            settings = payload.get("app_settings", {}) or {}
            if isinstance(settings, list):
                settings = {str(item.get("key")): item.get("value") for item in settings if isinstance(item, dict) and item.get("key")}
            if not isinstance(settings, dict):
                raise ValueError("app_settings muss ein Objekt sein")

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
            QMessageBox.critical(self, "Konfiguration importieren", str(exc))
            return

        QMessageBox.information(self, "Konfiguration importiert", "Import abgeschlossen.")

    def reset_sql_config_to_defaults(self) -> None:
        answer = QMessageBox.warning(
            self,
            "SQLite-Konfiguration auf Defaults",
            "Die Werte in app_settings werden gelöscht und aus den internen Defaults neu geschrieben.\n"
            "Kategorien, Tags, Aliase, Gewichtungen, Posts und Downloads bleiben erhalten.\n\n"
            "Das ist also kein Datenbank-Nuklearangriff, nur Konfig-Putzdienst. Fortfahren?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            self.db.execute("DELETE FROM app_settings")
            default_settings = flatten_config(DEFAULT_CONFIG)
            # categories wird in eigenen Tabellen verwaltet; leere Defaults sollen vorhandene Kategorien nicht vernichten.
            default_settings.pop("categories", None)
            for key, value in default_settings.items():
                self.set_setting(key, value)
                self.set_runtime_value(key, value)
            self.db.commit()
            self.reload_from_sql()
            self.config_changed.emit()
        except Exception as exc:
            QMessageBox.critical(self, "Defaults wiederherstellen", str(exc))
            return

        QMessageBox.information(
            self,
            "Defaults wiederhergestellt",
            "SQLite-Konfiguration wurde auf interne Defaults zurückgesetzt.\n"
            "Einige Pfade wirken erst nach einem Neustart vollständig.",
        )
