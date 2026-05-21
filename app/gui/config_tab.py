from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import Signal
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
)

from app.core.database import Database


class ConfigTab(QWidget):
    config_changed = Signal()

    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db

        self.main_layout = QVBoxLayout(self)

        self.info_label = QLabel(
            "Konfiguration aus SQLite. config.yaml bleibt Import-/Default-Basis. "
            "Änderungen hier gelten für laufende GUI/Future-Starts, soweit der Code die Werte aus app_settings lädt."
        )
        self.info_label.setWordWrap(True)
        self.main_layout.addWidget(self.info_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)

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

        self.content_layout.addWidget(self.general_group)

        self.fetch_group = QGroupBox("Fetch")
        self.fetch_form = QFormLayout(self.fetch_group)

        self.base_url_edit = QLineEdit(str(config.get("base_url", "https://danbooru.donmai.us")))
        self.search_tags_edit = QLineEdit(str(config.get("search_tags", "order:id_desc")))
        self.saved_search_extra_tags_edit = QLineEdit(str(config.get("saved_search_extra_tags", "")))

        self.use_saved_searches_checkbox = QCheckBox("Saved Searches verwenden")
        self.use_saved_searches_checkbox.setChecked(bool(config.get("use_saved_searches", False)))

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
        self.fetch_form.addRow("search_tags:", self.search_tags_edit)
        self.fetch_form.addRow("saved_search_extra_tags:", self.saved_search_extra_tags_edit)
        self.fetch_form.addRow("", self.use_saved_searches_checkbox)
        self.fetch_form.addRow("limit:", self.limit_spin)
        self.fetch_form.addRow("max_posts_per_query:", self.max_posts_per_query_spin)
        self.fetch_form.addRow("max_total_posts:", self.max_total_posts_spin)

        self.content_layout.addWidget(self.fetch_group)

        self.gui_group = QGroupBox("GUI / Preview")
        self.gui_form = QFormLayout(self.gui_group)

        gui_config = config.get("gui", {}) or {}
        viewer_config = config.get("viewer", {}) or {}

        self.thumbnail_size_spin = QSpinBox()
        self.thumbnail_size_spin.setRange(80, 1200)
        self.thumbnail_size_spin.setValue(int(gui_config.get("thumbnail_size", config.get("thumbnail_size", 340))))
        self.thumbnail_size_spin.setKeyboardTracking(False)

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

        self.gui_form.addRow("thumbnail_size:", self.thumbnail_size_spin)
        self.gui_form.addRow("thumbnail_size_min:", self.thumbnail_min_spin)
        self.gui_form.addRow("thumbnail_size_max:", self.thumbnail_max_spin)
        self.gui_form.addRow("card_width_extra:", self.card_width_extra_spin)
        self.gui_form.addRow("default_view:", self.viewer_default_view_combo)
        self.gui_form.addRow("", self.auto_advance_after_save_checkbox)
        self.gui_form.addRow("", self.auto_advance_after_reject_checkbox)

        self.content_layout.addWidget(self.gui_group)

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

        filename_help = QLabel(
            "Platzhalter: %artist%/%artists%, %character%/%characters%, "
            "%copyright%/%series%, %general%, %meta%, %tags%, %postid%/%postID%, %hash%, %ext%"
        )
        filename_help.setWordWrap(True)

        self.filename_form.addRow("pattern:", self.filename_pattern_edit)
        self.filename_form.addRow("tags_count:", self.filename_tags_count_spin)
        self.filename_form.addRow("max_length:", self.filename_max_length_spin)
        self.filename_form.addRow("hash_length:", self.filename_hash_length_spin)
        self.filename_form.addRow("", filename_help)

        self.content_layout.addWidget(self.filename_group)

        self.workflow_group = QGroupBox("Workflow")
        self.workflow_form = QFormLayout(self.workflow_group)

        workflow_config = config.get("workflow", {}) or {}

        self.worklist_statuses_edit = QLineEdit(
            ", ".join(str(v) for v in workflow_config.get("worklist_statuses", ["new", "potential", "review", "selected_save"]))
        )

        self.rejected_retention_spin = QSpinBox()
        self.rejected_retention_spin.setRange(1, 3650)
        self.rejected_retention_spin.setValue(int(workflow_config.get("rejected_thumbnail_retention_days", 7)))
        self.rejected_retention_spin.setKeyboardTracking(False)

        self.workflow_form.addRow("worklist_statuses:", self.worklist_statuses_edit)
        self.workflow_form.addRow("rejected_thumbnail_retention_days:", self.rejected_retention_spin)

        self.content_layout.addWidget(self.workflow_group)

        self.raw_group = QGroupBox("Raw app_settings")
        self.raw_layout = QVBoxLayout(self.raw_group)

        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setMinimumHeight(160)
        self.raw_layout.addWidget(self.raw_text)

        self.content_layout.addWidget(self.raw_group)

        self.content_layout.addStretch(1)

        self.scroll.setWidget(self.content)
        self.main_layout.addWidget(self.scroll, stretch=1)

        self.button_row = QHBoxLayout()

        self.save_button = QPushButton("Speichern")
        self.save_button.clicked.connect(self.save_config)
        self.button_row.addWidget(self.save_button)

        self.reload_button = QPushButton("Aus SQL neu laden")
        self.reload_button.clicked.connect(self.reload_from_sql)
        self.button_row.addWidget(self.reload_button)

        self.reset_button = QPushButton("Aus aktueller YAML/Runtime neu anzeigen")
        self.reset_button.clicked.connect(self.reload_from_runtime)
        self.button_row.addWidget(self.reset_button)

        self.button_row.addStretch(1)
        self.main_layout.addLayout(self.button_row)

        self.apply_sql_settings_to_runtime()
        self.reload_from_runtime()
        self.refresh_raw_settings()

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
            lines.append(f"{row['key']} = {row['value']}    ({row['updated_at']})")

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
        self.search_tags_edit.setText(str(self.runtime_value("search_tags", "order:id_desc")))
        self.saved_search_extra_tags_edit.setText(str(self.runtime_value("saved_search_extra_tags", "")))
        self.use_saved_searches_checkbox.setChecked(bool(self.runtime_value("use_saved_searches", False)))
        self.limit_spin.setValue(int(self.runtime_value("limit", 100)))
        self.max_posts_per_query_spin.setValue(int(self.runtime_value("max_posts_per_query", 500)))
        self.max_total_posts_spin.setValue(int(self.runtime_value("max_total_posts", 1000)))

        self.thumbnail_size_spin.setValue(int(self.runtime_value("gui.thumbnail_size", 340)))
        self.thumbnail_min_spin.setValue(int(self.runtime_value("gui.thumbnail_size_min", 120)))
        self.thumbnail_max_spin.setValue(int(self.runtime_value("gui.thumbnail_size_max", 700)))
        self.card_width_extra_spin.setValue(int(self.runtime_value("gui.card_width_extra", 100)))

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

        workflow_statuses = self.runtime_value("workflow.worklist_statuses", ["new", "potential", "review", "selected_save"])
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
            "search_tags": self.search_tags_edit.text().strip(),
            "saved_search_extra_tags": self.saved_search_extra_tags_edit.text().strip(),
            "use_saved_searches": self.use_saved_searches_checkbox.isChecked(),
            "limit": int(self.limit_spin.value()),
            "max_posts_per_query": int(self.max_posts_per_query_spin.value()),
            "max_total_posts": int(self.max_total_posts_spin.value()),

            "gui.thumbnail_size": int(self.thumbnail_size_spin.value()),
            "gui.thumbnail_size_min": int(self.thumbnail_min_spin.value()),
            "gui.thumbnail_size_max": int(self.thumbnail_max_spin.value()),
            "gui.card_width_extra": int(self.card_width_extra_spin.value()),

            "viewer.default_view": str(self.viewer_default_view_combo.currentData()),
            "viewer.auto_advance_after_save": self.auto_advance_after_save_checkbox.isChecked(),
            "viewer.auto_advance_after_reject": self.auto_advance_after_reject_checkbox.isChecked(),

            "filename.pattern": self.filename_pattern_edit.text().strip() or "%artists%_%characters%_%general%_%postid%",
            "filename.tags_count": int(self.filename_tags_count_spin.value()),
            "filename.max_length": int(self.filename_max_length_spin.value()),
            "filename.hash_length": int(self.filename_hash_length_spin.value()),

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
