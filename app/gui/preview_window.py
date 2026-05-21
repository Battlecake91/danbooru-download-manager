from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.core.database import Database
from app.gui.image_viewer import ImageViewerWindow
from app.gui.thumbnail_grid import ThumbnailGrid
from app.services.final_save_service import AlreadySavedError, FinalSaveService


STATUS_LABELS: dict[str, str] = {
    "new": "Ungeprüft",
    "potential": "Hohes Potential",
    "review": "Prüfen",
    "selected_save": "Zum Speichern",
    "auto_rejected": "Automatisch aussortiert",
    "rejected": "Abgelehnt",
    "accepted": "Akzeptiert",
    "already_known": "Bereits bekannt",
    "downloaded": "Heruntergeladen/alt",
    "saved": "Gespeichert",
}


STATUS_ORDER: list[str] = [
    "new",
    "potential",
    "review",
    "selected_save",
    "auto_rejected",
    "rejected",
    "accepted",
    "already_known",
    "downloaded",
    "saved",
]


DEFAULT_VISIBLE_STATUSES: set[str] = {
    "new",
    "potential",
    "review",
    "selected_save",
}


VIEW_LABELS: dict[str, str] = {
    "filtered": "Status-Filter",
    "worklist": "Arbeitsliste",
    "saved": "Gespeichert",
    "rejected": "Aussortiert",
    "known": "Bekannte/importierte",
    "all": "Alle bekannten Posts",
}


class PreviewWindow(QMainWindow):
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.final_save_service = FinalSaveService(config, db)
        self.current_limit = 500
        self.current_offset = 0

        self.viewer_windows_by_post_id: dict[int, ImageViewerWindow] = {}

        self._applying_viewer_query = False
        self._pending_viewer_query: str | None = None
        self._is_reloading = False
        self._reload_pending = False
        self._syncing_status_checkboxes = False

        self.status_checkboxes: dict[str, QCheckBox] = {}
        self.category_rule_cache: list[dict[str, Any]] = []

        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.setInterval(250)
        self.reload_timer.timeout.connect(self.reload_posts)

        gui_config = config.get("gui", {}) or {}

        self.setWindowTitle("Danbooru Manager - Preview")

        self.toolbar = QToolBar("Preview")
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.reload_button = QPushButton("Neu laden")
        self.reload_button.clicked.connect(self.reload_posts)
        self.toolbar.addWidget(self.reload_button)

        self.final_save_button = QPushButton("Final speichern (F)")
        self.final_save_button.clicked.connect(self.final_save_selected_posts)
        self.toolbar.addWidget(self.final_save_button)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Ansicht: "))
        self.view_mode = QComboBox()
        for view_mode, label in VIEW_LABELS.items():
            self.view_mode.addItem(label, view_mode)

        self.view_mode.setCurrentIndex(self.view_mode.findData("filtered"))
        self.view_mode.currentIndexChanged.connect(self.on_view_mode_changed)
        self.toolbar.addWidget(self.view_mode)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Status: "))

        self.all_status_checkbox = QCheckBox("Alle")
        self.all_status_checkbox.setChecked(False)
        self.all_status_checkbox.stateChanged.connect(self.on_all_status_changed)
        self.toolbar.addWidget(self.all_status_checkbox)

        for status in STATUS_ORDER:
            checkbox = QCheckBox(STATUS_LABELS[status])
            checkbox.setChecked(status in DEFAULT_VISIBLE_STATUSES)
            checkbox.stateChanged.connect(self.on_status_checkbox_changed)
            self.status_checkboxes[status] = checkbox
            self.toolbar.addWidget(checkbox)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Kategorie: "))
        self.category_filter = QComboBox()
        self.category_filter.currentIndexChanged.connect(self.schedule_reload)
        self.toolbar.addWidget(self.category_filter)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Suche: "))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("ID, Tag oder Pfad suchen...")
        self.search_edit.returnPressed.connect(self.reload_posts)
        self.search_edit.setMinimumWidth(260)
        self.toolbar.addWidget(self.search_edit)

        self.search_button = QPushButton("Suchen")
        self.search_button.clicked.connect(self.reload_posts)
        self.toolbar.addWidget(self.search_button)

        self.clear_search_button = QPushButton("Leeren")
        self.clear_search_button.clicked.connect(self.clear_search)
        self.toolbar.addWidget(self.clear_search_button)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Limit: "))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(50, 5000)
        self.limit_spin.setSingleStep(50)
        self.limit_spin.setValue(self.current_limit)
        self.limit_spin.setKeyboardTracking(False)
        self.limit_spin.valueChanged.connect(self.schedule_reload)
        self.limit_spin.editingFinished.connect(self.schedule_reload)
        self.toolbar.addWidget(self.limit_spin)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Thumbnail: "))
        self.thumbnail_size_spin = QSpinBox()
        self.thumbnail_size_spin.setRange(
            int(gui_config.get("thumbnail_size_min", 120)),
            int(gui_config.get("thumbnail_size_max", 600)),
        )
        self.thumbnail_size_spin.setSingleStep(int(gui_config.get("thumbnail_size_step", 20)))
        self.thumbnail_size_spin.setSuffix(" px")
        self.thumbnail_size_spin.setValue(int(gui_config.get("thumbnail_size", 280)))
        self.thumbnail_size_spin.setKeyboardTracking(False)
        self.thumbnail_size_spin.valueChanged.connect(self.on_thumbnail_size_changed)
        self.toolbar.addWidget(self.thumbnail_size_spin)

        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout(self.main_widget)

        self.info_label = QLabel("")
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.main_layout.addWidget(self.info_label)

        self.grid = ThumbnailGrid(self.db, self.config)
        self.grid.status_changed.connect(self.on_status_changed)
        self.grid.request_reload.connect(self.schedule_reload)
        self.grid.open_viewer_requested.connect(self.open_viewer)
        self.grid.final_save_requested.connect(self.final_save_posts)
        self.grid.category_assign_requested.connect(self.assign_category_to_posts)
        self.main_layout.addWidget(self.grid)

        self.setCentralWidget(self.main_widget)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.sync_all_checkbox_from_statuses()
        self.reload_category_filter()
        self.reload_posts()

    # -------------------------------------------------------------------------
    # Kategorie-Filter / Kategorie-Vorschlag
    # -------------------------------------------------------------------------

    def reload_category_filter(self) -> None:
        current_value = self.category_filter.currentData()

        self.category_filter.blockSignals(True)
        try:
            self.category_filter.clear()
            self.category_filter.addItem("Alle Kategorien", "__all__")
            self.category_filter.addItem("_unmatched / keine Kategorie", "__unmatched__")

            for row in self.db.list_categories_full():
                name = str(row["name"])
                self.category_filter.addItem(name, name)

            if current_value is not None:
                index = self.category_filter.findData(current_value)
                if index >= 0:
                    self.category_filter.setCurrentIndex(index)
        finally:
            self.category_filter.blockSignals(False)

    def selected_category_filter(self) -> str:
        value = self.category_filter.currentData()
        return str(value) if value is not None else "__all__"

    def load_category_rule_cache(self) -> None:
        categories = self.db.list_categories_full()
        rules = self.db.list_category_rules()

        by_category: dict[int, dict[str, Any]] = {}

        for category in categories:
            category_id = int(category["id"])
            by_category[category_id] = {
                "id": category_id,
                "name": str(category["name"]),
                "folder_name": str(category["folder_name"]),
                "sort_order": int(category["sort_order"] or 0),
                "include": set(),
                "exclude": set(),
                "groups": {},
            }

        for rule in rules:
            category_id = int(rule["category_id"])
            if category_id not in by_category:
                continue

            rule_type = str(rule["rule_type"])
            tag = str(rule["tag"])

            if rule_type == "include":
                by_category[category_id]["include"].add(tag)
            elif rule_type == "exclude":
                by_category[category_id]["exclude"].add(tag)
            elif rule_type.startswith("include_group_"):
                by_category[category_id]["groups"].setdefault(rule_type, set()).add(tag)

        self.category_rule_cache = sorted(
            by_category.values(),
            key=lambda entry: (entry["sort_order"], entry["name"]),
        )

    def suggest_category_from_tags(self, tags_text: str) -> str:
        tags = set(tags_text.split())

        for category in self.category_rule_cache:
            name = category["name"]

            if category["exclude"].intersection(tags):
                continue

            include = category["include"]
            groups = category["groups"]

            if include and not include.intersection(tags):
                continue

            if groups:
                group_match = False
                for group_tags in groups.values():
                    if group_tags and group_tags.issubset(tags):
                        group_match = True
                        break
                if not group_match:
                    continue

            if include or groups:
                return name

        return "_unmatched"

    def enrich_preview_rows_with_categories(self, rows: list[Any]) -> list[dict[str, Any]]:
        self.load_category_rule_cache()

        enriched: list[dict[str, Any]] = []

        for row in rows:
            data = dict(row)
            tags_text = str(data.get("tags") or "")

            assigned_category = data.get("assigned_category_name")
            assigned_source = data.get("assigned_category_source")

            if assigned_category:
                data["preview_category_name"] = str(assigned_category)
                data["preview_category_source"] = str(assigned_source or "manual")
            else:
                data["preview_category_name"] = self.suggest_category_from_tags(tags_text)
                data["preview_category_source"] = "auto"

            enriched.append(data)

        return enriched

    def category_matches_filter(self, row: dict[str, Any], category_filter: str) -> bool:
        if category_filter == "__all__":
            return True

        category_name = str(row.get("preview_category_name") or "_unmatched")

        if category_filter == "__unmatched__":
            return category_name in {"", "_unmatched", "None"}

        return category_name == category_filter

    def assign_category_to_posts(self, post_ids: list[int], category_name: str) -> None:
        if not post_ids:
            return

        category = self.db.get_category_by_name(category_name)
        if category is None:
            self.status_bar.showMessage(f"Kategorie nicht gefunden: {category_name}")
            return

        category_id = int(category["id"])

        for post_id in post_ids:
            self.db.execute(
                """
                DELETE FROM post_categories
                WHERE post_id = ?
                """,
                (int(post_id),),
            )
            self.db.execute(
                """
                INSERT INTO post_categories (post_id, category_id, source)
                VALUES (?, ?, ?)
                """,
                (int(post_id), category_id, "manual"),
            )

            self.grid.update_card_category(int(post_id), category_name, "manual")

        self.db.commit()

        # Absichtlich kein Popup. Review-Workflow soll nicht von Dialogen zerhackt werden.
        self.status_bar.showMessage(f"{len(post_ids)} Post(s) → Kategorie {category_name}")

    # -------------------------------------------------------------------------
    # Status-Checkbox-Filter
    # -------------------------------------------------------------------------

    def on_view_mode_changed(self, *_args) -> None:
        mode = self.selected_view_mode()

        if mode == "filtered":
            self.schedule_reload()
            return

        presets: dict[str, set[str]] = {
            "worklist": {"new", "potential", "review", "selected_save"},
            "saved": {"saved"},
            "rejected": {"rejected", "auto_rejected"},
            "known": {"already_known", "downloaded"},
            "all": set(STATUS_ORDER),
        }

        statuses = presets.get(mode, DEFAULT_VISIBLE_STATUSES)
        self.set_checked_statuses(statuses)
        self.schedule_reload()

    def on_all_status_changed(self, state: int) -> None:
        if self._syncing_status_checkboxes:
            return

        checked = state == Qt.Checked

        self._syncing_status_checkboxes = True
        try:
            for checkbox in self.status_checkboxes.values():
                checkbox.setChecked(checked)
        finally:
            self._syncing_status_checkboxes = False

        self.schedule_reload()

    def on_status_checkbox_changed(self, *_args) -> None:
        if self._syncing_status_checkboxes:
            return

        self.sync_all_checkbox_from_statuses()

        if self.selected_view_mode() != "filtered":
            filtered_index = self.view_mode.findData("filtered")
            if filtered_index >= 0:
                self.view_mode.blockSignals(True)
                try:
                    self.view_mode.setCurrentIndex(filtered_index)
                finally:
                    self.view_mode.blockSignals(False)

        self.schedule_reload()

    def sync_all_checkbox_from_statuses(self) -> None:
        all_checked = all(checkbox.isChecked() for checkbox in self.status_checkboxes.values())

        self._syncing_status_checkboxes = True
        try:
            self.all_status_checkbox.setChecked(all_checked)
        finally:
            self._syncing_status_checkboxes = False

    def set_checked_statuses(self, statuses: set[str]) -> None:
        self._syncing_status_checkboxes = True
        try:
            for status, checkbox in self.status_checkboxes.items():
                checkbox.setChecked(status in statuses)
        finally:
            self._syncing_status_checkboxes = False

        self.sync_all_checkbox_from_statuses()

    def selected_statuses(self) -> list[str]:
        return [
            status
            for status in STATUS_ORDER
            if self.status_checkboxes[status].isChecked()
        ]

    # -------------------------------------------------------------------------
    # Reload / Filter
    # -------------------------------------------------------------------------

    def schedule_reload(self, *_args) -> None:
        if self._applying_viewer_query:
            return

        if self._is_reloading:
            self._reload_pending = True
            return

        self.reload_timer.start()

    def selected_view_mode(self) -> str:
        return str(self.view_mode.currentData())

    def current_search_text(self) -> str | None:
        text = self.search_edit.text().strip()
        return text or None

    def clear_search(self) -> None:
        self.search_edit.clear()
        self.reload_posts()

    def on_thumbnail_size_changed(self, size: int) -> None:
        self.grid.set_thumbnail_size(int(size))
        self.status_bar.showMessage(f"Thumbnail-Größe: {size}px")

    def reload_posts(self) -> None:
        if self._applying_viewer_query:
            return

        if self._is_reloading:
            self._reload_pending = True
            return

        self.reload_timer.stop()
        self._is_reloading = True

        try:
            statuses = self.selected_statuses()
            text_filter = self.current_search_text()
            category_filter = self.selected_category_filter()
            self.current_limit = int(self.limit_spin.value())

            internal_limit = self.current_limit if category_filter == "__all__" else max(self.current_limit * 5, 2000)

            candidates = self.fetch_preview_posts_by_statuses(
                statuses=statuses,
                text_filter=text_filter,
                limit=internal_limit,
                offset=self.current_offset,
            )
            enriched = self.enrich_preview_rows_with_categories(candidates)
            filtered = [
                row
                for row in enriched
                if self.category_matches_filter(row, category_filter)
            ]

            posts = filtered[: self.current_limit]
            total = len(filtered)

            self.grid.set_posts(posts)

            status_text = self.status_filter_description(statuses)
            category_text = self.category_filter.currentText()

            self.info_label.setText(
                f"Ansicht: {VIEW_LABELS.get(self.selected_view_mode(), self.selected_view_mode())} | "
                f"Angezeigt: {len(posts)} / Treffer im geladenen Bereich: {total} | "
                f"Status: {status_text} | Kategorie: {category_text} | "
                f"Thumbnail: {self.grid.thumbnail_size}px"
            )
            self.status_bar.showMessage("Preview geladen")

        finally:
            self._is_reloading = False

        if self._reload_pending:
            self._reload_pending = False
            self.schedule_reload()

    def status_filter_description(self, statuses: list[str]) -> str:
        if not statuses:
            return "Keine"

        if set(statuses) == set(STATUS_ORDER):
            return "Alle"

        return ", ".join(STATUS_LABELS.get(status, status) for status in statuses)

    def build_preview_where(
        self,
        statuses: list[str],
        text_filter: str | None,
    ) -> tuple[str, list[Any]]:
        where_parts: list[str] = []
        parameters: list[Any] = []

        if not statuses:
            where_parts.append("1 = 0")
        elif set(statuses) != set(STATUS_ORDER):
            placeholders = ", ".join("?" for _ in statuses)
            where_parts.append(f"p.status IN ({placeholders})")
            parameters.extend(statuses)

        if text_filter:
            pattern = f"%{text_filter.strip()}%"
            where_parts.append(
                """
                (
                    CAST(p.id AS TEXT) LIKE ?
                    OR p.final_file_path LIKE ?
                    OR p.final_directory LIKE ?
                    OR EXISTS (
                        SELECT 1
                        FROM post_tags pt
                        WHERE pt.post_id = p.id
                        AND pt.tag LIKE ?
                    )
                )
                """
            )
            parameters.extend([pattern, pattern, pattern, pattern])

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        return where_sql, parameters

    def fetch_preview_posts_by_statuses(
        self,
        statuses: list[str],
        text_filter: str | None,
        limit: int,
        offset: int,
    ) -> list[Any]:
        where_sql, parameters = self.build_preview_where(statuses, text_filter)
        parameters.extend([limit, offset])

        return list(
            self.db.execute(
                f"""
                SELECT
                    p.id,
                    p.rating,
                    p.score,
                    p.fav_count,
                    p.thumbnail_path,
                    p.rejected_thumbnail_path,
                    p.parent_id,
                    p.has_children,
                    p.status,
                    p.local_score,
                    p.llm_score,
                    p.final_score,
                    p.final_file_path,
                    p.final_directory,
                    p.rejected_at,
                    p.saved_at,
                    p.already_known_at,

                    assigned_category.name AS assigned_category_name,
                    pc.source AS assigned_category_source,

                    CASE
                        WHEN p.parent_id IS NOT NULL
                         AND EXISTS (SELECT 1 FROM posts parent WHERE parent.id = p.parent_id)
                        THEN 1
                        ELSE 0
                    END AS known_parent_loaded,

                    (
                        SELECT COUNT(*)
                        FROM posts child
                        WHERE child.parent_id = p.id
                    ) AS known_child_count,

                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id
                        ORDER BY
                            CASE pt.tag_type
                                WHEN 'copyright' THEN 1
                                WHEN 'character' THEN 2
                                WHEN 'artist' THEN 3
                                WHEN 'general' THEN 4
                                WHEN 'meta' THEN 5
                                ELSE 9
                            END,
                            pt.tag
                    ) AS tags
                FROM posts p
                LEFT JOIN post_categories pc ON pc.post_id = p.id
                LEFT JOIN categories assigned_category ON assigned_category.id = pc.category_id
                {where_sql}
                GROUP BY p.id
                ORDER BY p.id DESC
                LIMIT ?
                OFFSET ?
                """,
                parameters,
            ).fetchall()
        )

    # -------------------------------------------------------------------------
    # Final speichern aus Preview
    # -------------------------------------------------------------------------

    def final_save_selected_posts(self) -> None:
        post_ids = self.grid.selected_or_current_post_ids()
        self.final_save_posts(post_ids)

    def final_save_posts(self, post_ids: list[int]) -> None:
        if not post_ids:
            self.status_bar.showMessage("Final speichern: keine Posts ausgewählt.")
            return

        saved: list[str] = []
        skipped: list[str] = []
        failed: list[str] = []

        self.final_save_button.setEnabled(False)
        try:
            for post_id in post_ids:
                try:
                    result = self.final_save_service.save_post(int(post_id), category=None)
                    saved.append(f"{post_id}: {result.final_path}")
                    self.grid.update_card_status(int(post_id), "saved")
                    self.grid.update_card_category(int(post_id), result.category.name, result.category_source)
                except AlreadySavedError as exc:
                    skipped.append(str(exc))
                    self.grid.update_card_status(int(post_id), "saved")
                except Exception as exc:
                    failed.append(f"{post_id}: {exc}")
        finally:
            self.final_save_button.setEnabled(True)

        parts: list[str] = []

        if saved:
            parts.append(f"Gespeichert: {len(saved)}")
        if skipped:
            parts.append(f"Bereits gespeichert/übersprungen: {len(skipped)}")
        if failed:
            parts.append(f"Fehler: {len(failed)}")

        summary = " | ".join(parts) if parts else "Nichts erledigt."
        self.status_bar.showMessage(summary)

        if failed:
            QMessageBox.warning(
                self,
                "Final speichern",
                summary + "\n\nFehler:\n" + "\n".join(failed[:10]),
            )

    # -------------------------------------------------------------------------
    # Viewer / Status
    # -------------------------------------------------------------------------

    def on_status_changed(self, post_id: int, status: str) -> None:
        self.grid.update_card_status(post_id, status)
        self.status_bar.showMessage(f"Post {post_id} → {STATUS_LABELS.get(status, status)}")

    def open_viewer(self, post_id: int) -> None:
        post_id = int(post_id)

        existing = self.viewer_windows_by_post_id.get(post_id)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return

        post_ids = self.grid.visible_post_ids()
        viewer = ImageViewerWindow(self.config, self.db, post_ids, post_id)
        viewer.status_changed.connect(self.on_status_changed)
        viewer.query_requested.connect(self.schedule_viewer_query)
        viewer.destroyed.connect(lambda *_args, pid=post_id: self.remove_viewer(pid))

        self.viewer_windows_by_post_id[post_id] = viewer

        viewer.resize(1500, 950)
        viewer.show()

    def remove_viewer(self, post_id: int) -> None:
        self.viewer_windows_by_post_id.pop(int(post_id), None)

    def schedule_viewer_query(self, query: str) -> None:
        query = query.strip()
        if not query:
            return

        self._pending_viewer_query = query
        QTimer.singleShot(0, self.apply_pending_viewer_query)

    def apply_pending_viewer_query(self) -> None:
        query = self._pending_viewer_query
        self._pending_viewer_query = None

        if not query:
            return

        self._applying_viewer_query = True
        try:
            self.search_edit.setText(query)

            filtered_index = self.view_mode.findData("filtered")
            if filtered_index >= 0:
                self.view_mode.blockSignals(True)
                try:
                    self.view_mode.setCurrentIndex(filtered_index)
                finally:
                    self.view_mode.blockSignals(False)

            self.set_checked_statuses(set(STATUS_ORDER))

        finally:
            self._applying_viewer_query = False

        self.reload_posts()
        self.status_bar.showMessage(f"Query aus Viewer übernommen: {query}")

    def cleanup_viewers(self) -> None:
        self.viewer_windows_by_post_id = {
            post_id: viewer
            for post_id, viewer in self.viewer_windows_by_post_id.items()
            if viewer.isVisible()
        }
