from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.core.database import Database
from app.i18n.i18n import tr
from app.services.post_import_service import PostImportService
from app.services.tag_catalog_service import TagCatalogService


class FirstRunSetupDialog(QDialog):
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()
        self.config = config
        self.db = db
        self.setWindowTitle(tr("setup.title", "First start setup", config=config))
        self.resize(720, 460)

        layout = QVBoxLayout(self)
        intro = QLabel(
            tr(
                "setup.intro",
                "Set the optional Danbooru credentials and prepare the local tag catalog. "
                "This can be skipped and repeated later, but doing it once now makes the tag tools useful immediately.",
                config=config,
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.username_edit = QLineEdit(str(config.get("username") or ""))
        self.api_key_edit = QLineEdit(str(config.get("api_key") or ""))
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.show_key_checkbox = QCheckBox(tr("setup.show_api_key", "Show API key", config=config))
        self.show_key_checkbox.toggled.connect(self._toggle_key_visibility)

        key_row = QHBoxLayout()
        key_row.addWidget(self.api_key_edit, stretch=1)
        key_row.addWidget(self.show_key_checkbox)

        self.tag_limit_spin = QSpinBox()
        self.tag_limit_spin.setRange(0, 500_000)
        self.tag_limit_spin.setSingleStep(1000)
        self.tag_limit_spin.setValue(int(config.get("tag_catalog", {}).get("popular_tag_limit", 10000)))

        self.min_count_spin = QSpinBox()
        self.min_count_spin.setRange(0, 10_000_000)
        self.min_count_spin.setSingleStep(25)
        self.min_count_spin.setValue(int(config.get("tag_catalog", {}).get("popular_tag_min_post_count", 50)))

        first_run_config = config.get("first_run", {}) or {}
        self.sample_post_spin = QSpinBox()
        self.sample_post_spin.setRange(1, 2_147_483_647)
        self.sample_post_spin.setValue(int(first_run_config.get("sample_post_id") or config.get("gui", {}).get("preview_sample_post_id") or 11199825))

        form.addRow(tr("setup.username", "Danbooru username:", config=config), self.username_edit)
        form.addRow(tr("setup.api_key", "Danbooru API key:", config=config), key_row)
        form.addRow(tr("setup.popular_tag_limit", "Popular tags to import:", config=config), self.tag_limit_spin)
        form.addRow(tr("setup.min_post_count", "Minimum Danbooru post count:", config=config), self.min_count_spin)
        form.addRow(tr("setup.sample_post_id", "Preview sample post ID:", config=config), self.sample_post_spin)
        layout.addLayout(form)

        self.import_tags_checkbox = QCheckBox(tr("setup.import_popular_tags", "Import popular Danbooru tags now", config=config))
        self.import_tags_checkbox.setChecked(bool(first_run_config.get("import_popular_tags", True)))
        self.fetch_sample_checkbox = QCheckBox(tr("setup.fetch_sample_post", "Fetch preview sample post now", config=config))
        self.fetch_sample_checkbox.setChecked(bool(first_run_config.get("fetch_sample_post", True)))
        layout.addWidget(self.import_tags_checkbox)
        layout.addWidget(self.fetch_sample_checkbox)

        self.status_label = QLabel(tr("setup.status.ready", "Ready.", config=config))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        buttons = QDialogButtonBox()
        self.run_button = QPushButton(tr("setup.run", "Run setup", config=config))
        self.skip_button = QPushButton(tr("setup.skip", "Skip", config=config))
        buttons.addButton(self.run_button, QDialogButtonBox.AcceptRole)
        buttons.addButton(self.skip_button, QDialogButtonBox.RejectRole)
        self.run_button.clicked.connect(self.run_setup)
        self.skip_button.clicked.connect(self.skip_setup)
        layout.addWidget(buttons)

    def _toggle_key_visibility(self, checked: bool) -> None:
        self.api_key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def _set_setting(self, key: str, value: Any) -> None:
        import json

        self.db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, json.dumps(value, ensure_ascii=False)),
        )

    def _apply_basic_settings(self) -> None:
        username = self.username_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        tag_limit = int(self.tag_limit_spin.value())
        min_count = int(self.min_count_spin.value())
        sample_post_id = int(self.sample_post_spin.value())

        self.config["username"] = username or None
        self.config["api_key"] = api_key or None
        self.config.setdefault("tag_catalog", {})["popular_tag_limit"] = tag_limit
        self.config.setdefault("tag_catalog", {})["popular_tag_min_post_count"] = min_count
        self.config.setdefault("gui", {})["preview_sample_post_id"] = sample_post_id
        self.config.setdefault("first_run", {})["sample_post_id"] = sample_post_id

        self._set_setting("username", username or None)
        self._set_setting("api_key", api_key or None)
        self._set_setting("tag_catalog.popular_tag_limit", tag_limit)
        self._set_setting("tag_catalog.popular_tag_min_post_count", min_count)
        self._set_setting("gui.preview_sample_post_id", sample_post_id)
        self._set_setting("first_run.sample_post_id", sample_post_id)

    def run_setup(self) -> None:
        self.run_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        try:
            self._apply_basic_settings()
            self.progress_bar.setValue(5)

            if self.import_tags_checkbox.isChecked() and self.tag_limit_spin.value() > 0:
                self.status_label.setText(tr("setup.status.importing_tags", "Importing popular Danbooru tags…", config=self.config))
                service = TagCatalogService(self.config, self.db)

                def progress(category: str, done: int, total: int) -> None:
                    self.status_label.setText(
                        tr(
                            "setup.status.importing_tags_progress",
                            "Importing tags: {done}/{total} ({category})",
                            config=self.config,
                            done=done,
                            total=total,
                            category=category,
                        )
                    )
                    if total > 0:
                        self.progress_bar.setValue(min(75, 10 + int(done / total * 60)))

                result = service.import_popular_tags(
                    limit=int(self.tag_limit_spin.value()),
                    min_post_count=int(self.min_count_spin.value()),
                    progress_callback=progress,
                )
                self.status_label.setText(
                    tr(
                        "setup.status.tags_done",
                        "Imported {count} Danbooru tags.",
                        config=self.config,
                        count=result.stored,
                    )
                )
                self.progress_bar.setValue(80)

            if self.fetch_sample_checkbox.isChecked():
                post_id = int(self.sample_post_spin.value())
                self.status_label.setText(tr("setup.status.fetching_sample", "Fetching sample post {post_id}…", config=self.config, post_id=post_id))
                fetch_config = copy.deepcopy(self.config)
                service = PostImportService(fetch_config, self.db)
                post = service.api.get_post(post_id)
                service.store_post(post)
                thumbnail_path = service.thumbnail_cache.cache_thumbnail(post, force=True)
                if thumbnail_path:
                    service.set_thumbnail_path(post_id, thumbnail_path)
                self.progress_bar.setValue(95)

            self._set_setting("setup.first_run_completed", True)
            self.db.commit()
            self.progress_bar.setValue(100)
            self.status_label.setText(tr("setup.status.done", "Setup finished.", config=self.config))
            self.accept()
        except Exception as exc:
            self.run_button.setEnabled(True)
            self.skip_button.setEnabled(True)
            self.status_label.setText(tr("setup.status.error", "Setup failed: {error}", config=self.config, error=exc))
            QMessageBox.critical(self, tr("setup.error.title", "Setup failed", config=self.config), str(exc))

    def skip_setup(self) -> None:
        self._set_setting("setup.first_run_completed", True)
        self.db.commit()
        self.reject()


def should_show_first_run_setup(db: Database) -> bool:
    row = db.execute("SELECT value FROM app_settings WHERE key = ?", ("setup.first_run_completed",)).fetchone()
    if row is None:
        return True
    return str(row["value"] or "").strip().lower() not in {"true", "1", '"true"'}
