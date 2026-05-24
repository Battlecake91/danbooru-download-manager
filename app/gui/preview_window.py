from __future__ import annotations

import shlex
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QStackedWidget,
)

from app.core.database import Database
from app.core.category_engine import build_category_match_groups
from app.core.recommendation_engine import RecommendationEngine
from app.gui.image_viewer import ImageViewerWindow
from app.gui.icon_utils import ensure_app_icon
from app.gui.fetch_tab import TagQueryLineEdit
from app.gui.thumbnail_grid import ThumbnailGrid
from app.danbooru.api import DanbooruApi
from app.danbooru.thumbnail_cache import ThumbnailCache
from app.services.final_save_service import AlreadySavedError, FinalSaveService


def parse_preview_search_terms(search_text: str) -> tuple[list[str], list[str]]:
    try:
        tokens = shlex.split(search_text)
    except ValueError:
        tokens = search_text.split()

    positive: list[str] = []
    negative: list[str] = []

    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token.startswith("-") and len(token) > 1:
            negative.append(token[1:].strip())
        else:
            positive.append(token)

    return positive, negative


STATUS_LABELS: dict[str, str] = {
    "new": "Ungeprüft",
    "potential": "Hohes Potential",
    "rejected": "Abgelehnt",
    "already_known": "Bereits bekannt",
    "saved": "Gespeichert",
}


STATUS_ORDER: list[str] = [
    "new",
    "potential",
    "rejected",
    "already_known",
    "saved",
]


DEFAULT_VISIBLE_STATUSES: set[str] = {
    "new",
    "potential",
}


VIEW_LABELS: dict[str, str] = {
    "filtered": "Status-Filter",
    "worklist": "Arbeitsliste",
    "saved": "Gespeichert",
    "rejected": "Aussortiert",
    "known": "Bereits bekannt",
    "all": "Alle bekannten Posts",
}


SORT_LABELS: dict[str, str] = {
    "id_desc": "Post-ID: neueste zuerst",
    "id_asc": "Post-ID: älteste zuerst",
    "score_desc": "Danbooru-Score: hoch → niedrig",
    "score_asc": "Danbooru-Score: niedrig → hoch",
    "recommendation_desc": "Vorauswahl: hoch → niedrig",
    "recommendation_asc": "Vorauswahl: niedrig → hoch",
    "personal_desc": "Persönliches Rating: hoch → niedrig",
    "personal_asc": "Persönliches Rating: niedrig → hoch",
    "rating": "Danbooru-Rating: general → explicit",
    "status": "Status",
    "category": "Kategorie",
    "saved_desc": "Zuletzt gespeichert",
    "seen_desc": "Zuletzt gesehen",
    "resolution_desc": "Auflösung: groß → klein",
    "filesize_desc": "Dateigröße: groß → klein",
}


SQL_SORT_ORDER: dict[str, str] = {
    "id_desc": "p.id DESC",
    "id_asc": "p.id ASC",
    "score_desc": "COALESCE(p.score, -999999) DESC, p.id DESC",
    "score_asc": "COALESCE(p.score, 999999) ASC, p.id DESC",
    "personal_desc": "COALESCE(pr.stars, -1) DESC, p.id DESC",
    "personal_asc": "COALESCE(pr.stars, 999) ASC, p.id DESC",
    "rating": "CASE p.rating WHEN 'g' THEN 0 WHEN 's' THEN 1 WHEN 'q' THEN 2 WHEN 'e' THEN 3 ELSE 9 END ASC, p.id DESC",
    "status": "CASE p.status WHEN 'new' THEN 0 WHEN 'potential' THEN 1 WHEN 'saved' THEN 2 WHEN 'already_known' THEN 3 WHEN 'rejected' THEN 4 ELSE 9 END ASC, p.id DESC",
    "saved_desc": "COALESCE(p.saved_at, '') DESC, p.id DESC",
    "seen_desc": "COALESCE(p.last_seen_at, '') DESC, p.id DESC",
    "resolution_desc": "COALESCE(p.image_width, 0) * COALESCE(p.image_height, 0) DESC, p.id DESC",
    "filesize_desc": "COALESCE(p.file_size, 0) DESC, p.id DESC",
}


class PreviewWindow(QMainWindow):
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.final_save_service = FinalSaveService(config, db)
        self.recommendation_engine = RecommendationEngine(db)
        self.current_limit = int((config.get("gui", {}) or {}).get("preview_limit", 100))
        self.current_offset = 0

        self.viewer_windows_by_post_id: dict[int, ImageViewerWindow] = {}

        self._applying_viewer_query = False
        self._pending_viewer_query: str | None = None
        self._is_reloading = False
        self._reload_pending = False
        self._syncing_status_checkboxes = False
        self._fetch_running = False
        self._has_loaded_once = False
        self._filters_dirty = True

        self.status_checkboxes: dict[str, QCheckBox] = {}
        self.category_rule_cache: list[dict[str, Any]] = []

        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.setInterval(250)
        self.reload_timer.timeout.connect(self.reload_posts)

        gui_config = config.get("gui", {}) or {}

        self.setWindowTitle("Danbooru Manager - Preview")
        self.setWindowIcon(ensure_app_icon(config))
        self.setAutoFillBackground(True)
        self.setStyleSheet("QMainWindow { background: #151515; }")

        self.toolbar = QToolBar("Preview")
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.reload_button = QPushButton("Neu laden")
        self.reload_button.clicked.connect(self.reload_posts)
        self.toolbar.addWidget(self.reload_button)

        self.reload_thumbnails_button = QPushButton("Thumbnail neu laden")
        self.reload_thumbnails_button.setToolTip("Lädt die Thumbnails der ausgewählten Posts neu. Hilft gegen graue Platzhalter, dieser digitale Schimmel.")
        self.reload_thumbnails_button.clicked.connect(self.reload_selected_thumbnails)
        self.toolbar.addWidget(self.reload_thumbnails_button)

        self.fetch_status_label = QLabel("Fetch läuft…")
        self.fetch_status_label.setToolTip("Es werden gerade Posts von Danbooru geholt. Preview kann währenddessen noch unvollständig sein.")
        self.fetch_status_label.setStyleSheet(
            "QLabel { padding: 3px 8px; border: 1px solid #d6a000; "
            "border-radius: 6px; color: #ffd166; background: rgba(214, 160, 0, 0.12); }"
        )
        self.fetch_status_label.setVisible(False)
        self.toolbar.addWidget(self.fetch_status_label)

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
        # Kategorie ist ein Filter: Änderung erst mit "Neu laden" anwenden.
        self.category_filter.currentIndexChanged.connect(self.on_passive_filter_changed)
        self.toolbar.addWidget(self.category_filter)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Sortierung: "))
        self.sort_combo = QComboBox()
        for sort_key, sort_label in SORT_LABELS.items():
            self.sort_combo.addItem(sort_label, sort_key)
        self.sort_combo.setCurrentIndex(self.sort_combo.findData("id_desc"))
        # Sortierung ebenfalls passiv, damit Filtersetzen nicht sofort neu rendert.
        self.sort_combo.currentIndexChanged.connect(self.on_passive_filter_changed)
        self.toolbar.addWidget(self.sort_combo)

        self.toolbar.addSeparator()

        self.recommendation_filter_checkbox = QCheckBox("Vorauswahl ≥")
        self.recommendation_filter_checkbox.setToolTip(
            "Filtert die geladenen Preview-Kandidaten nach lokalem Vorauswahl-Score. "
            "Ausgeschaltet bedeutet: kein Score-Filter."
        )
        self.recommendation_filter_checkbox.stateChanged.connect(self.on_passive_filter_changed)
        self.toolbar.addWidget(self.recommendation_filter_checkbox)

        self.recommendation_min_spin = QDoubleSpinBox()
        self.recommendation_min_spin.setRange(-10.0, 10.0)
        self.recommendation_min_spin.setSingleStep(0.5)
        self.recommendation_min_spin.setDecimals(1)
        self.recommendation_min_spin.setValue(0.0)
        self.recommendation_min_spin.setKeyboardTracking(False)
        self.recommendation_min_spin.setToolTip(
            "Mindestwert fuer die lokale Vorauswahl. Der Filter greift nur, "
            "wenn die Checkbox links aktiv ist."
        )
        self.recommendation_min_spin.valueChanged.connect(self.on_passive_filter_changed)
        self.toolbar.addWidget(self.recommendation_min_spin)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel("Suche: "))
        self.search_edit = TagQueryLineEdit()
        self.search_edit.setPlaceholderText("Exakte Tags suchen, z. B. brown_eyes -red_hair")
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
        self.limit_spin.lineEdit().returnPressed.connect(self.reload_posts)
        self.limit_spin.valueChanged.connect(self.on_passive_filter_changed)
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
        self.main_widget.setAutoFillBackground(True)
        self.main_widget.setStyleSheet("QWidget { background: #151515; }")
        self.main_layout = QVBoxLayout(self.main_widget)

        self.info_label = QLabel("")
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_label.setStyleSheet("QLabel { color: #dddddd; }")
        self.main_layout.addWidget(self.info_label)

        self.content_stack = QStackedWidget()
        self.content_stack.setAutoFillBackground(True)
        self.content_stack.setStyleSheet("QStackedWidget { background: #151515; }")

        self.loading_panel = self.create_loading_panel()

        self.grid = ThumbnailGrid(self.db, self.config)
        self.grid.status_changed.connect(self.on_status_changed)
        self.grid.statuses_changed.connect(self.on_statuses_changed)
        self.grid.request_reload.connect(self.schedule_reload)
        self.grid.open_viewer_requested.connect(self.open_viewer)
        self.grid.final_save_requested.connect(self.final_save_posts)
        self.grid.category_assign_requested.connect(self.assign_category_to_posts)
        self.grid.thumbnail_reload_requested.connect(self.reload_thumbnails_for_posts)
        self.grid.build_started.connect(self.on_grid_build_started)
        self.grid.build_progress.connect(self.on_grid_build_progress)
        self.grid.build_finished.connect(self.on_grid_build_finished)

        self.content_stack.addWidget(self.loading_panel)
        self.content_stack.addWidget(self.grid)
        self.content_stack.setCurrentWidget(self.loading_panel)
        self.main_layout.addWidget(self.content_stack, stretch=1)

        self.setCentralWidget(self.main_widget)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.sync_all_checkbox_from_statuses()
        self.reload_category_filter()
        self.reload_tag_suggestions()
        self.show_preview_loading("Preview bereit. Öffne den Tab oder klicke auf Neu laden.")



    def create_loading_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("previewMainLoadingPanel")
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        panel.setStyleSheet(
            "QFrame#previewMainLoadingPanel { background: #151515; }"
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        layout.addStretch(1)

        self.loading_label = QLabel("Lädt Preview…")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet(
            "QLabel { color: #eeeeee; font-size: 20px; font-weight: bold; }"
        )
        layout.addWidget(self.loading_label)

        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setMinimumHeight(20)
        self.loading_bar.setMaximumWidth(520)
        layout.addWidget(self.loading_bar, alignment=Qt.AlignHCenter)

        layout.addStretch(1)
        return panel

    def show_preview_loading(self, message: str = "Lädt Preview…") -> None:
        self.loading_label.setText(message)
        self.loading_bar.setRange(0, 0)
        self.content_stack.setCurrentWidget(self.loading_panel)
        self.loading_panel.show()
        self.loading_panel.raise_()
        self.content_stack.update()
        self.main_widget.update()
        self.update()
        QApplication.processEvents()

    def hide_preview_loading(self) -> None:
        self.content_stack.setCurrentWidget(self.grid)
        self.grid.setVisible(True)
        self.grid.viewport().setVisible(True)
        self.grid.container.setVisible(True)
        self.grid.setUpdatesEnabled(True)
        self.grid.viewport().setUpdatesEnabled(True)
        self.grid.container.setUpdatesEnabled(True)
        self.grid.update_columns()
        if self.grid.items:
            self.grid.relayout()
        self.grid.container.adjustSize()
        self.grid.container.updateGeometry()
        self.grid.viewport().update()
        self.grid.updateGeometry()
        self.grid.update()
        self.content_stack.updateGeometry()
        self.content_stack.update()
        self.main_widget.updateGeometry()
        self.main_widget.update()
        self.update()
        QTimer.singleShot(0, self._force_preview_grid_repaint)

    def _force_preview_grid_repaint(self) -> None:
        if self.content_stack.currentWidget() is not self.grid:
            self.content_stack.setCurrentWidget(self.grid)
        self.grid.update_columns()
        if self.grid.items:
            self.grid.relayout()
        self.grid.viewport().update()
        self.grid.container.update()
        self.grid.update()
        self.content_stack.update()



    def reload_tag_suggestions(self) -> None:
        try:
            self.search_edit.set_tag_suggestions(self.db.suggest_tags(limit=2500))
        except Exception:
            self.search_edit.set_tag_suggestions([])

    def on_grid_build_started(self, total: int) -> None:
        if total > 0:
            self.show_preview_loading(f"Lädt Thumbnails… 0/{total}")
            self.status_bar.showMessage(f"Lädt Preview-Karten… 0/{total}")

    def on_grid_build_progress(self, current: int, total: int) -> None:
        if total > 0:
            self.loading_label.setText(f"Lädt Thumbnails… {current}/{total}")
            self.status_bar.showMessage(f"Lädt Preview-Karten… {current}/{total}")
            QApplication.processEvents()

    def on_grid_build_finished(self, total: int) -> None:
        self.status_bar.showMessage(f"Preview geladen: {total} Thumbnail(s)", 5000)
        QTimer.singleShot(0, self.hide_preview_loading)

    @staticmethod
    def is_path_like_search_term(term: str) -> bool:
        return any(marker in term for marker in ("/", "\\", "."))

    def set_fetch_running(self, running: bool) -> None:
        self._fetch_running = bool(running)
        self.fetch_status_label.setVisible(self._fetch_running)

        if self._fetch_running:
            self.status_bar.showMessage("Fetch läuft: Preview wird aktualisiert, sobald neue Posts geladen wurden.")
            if not self.grid.has_visible_content():
                self.grid.show_empty_message("Fetch läuft… Noch keine Posts in dieser Ansicht.")
        else:
            self.status_bar.showMessage("Fetch beendet. Preview wird aktualisiert.", 5000)

        self.grid.viewport().update()
        self.grid.update()
        self.update()

    def preview_needs_reload(self) -> bool:
        if self._is_reloading or self._reload_pending:
            return True
        if self._filters_dirty or not self._has_loaded_once:
            return True
        if not self.grid.items and not self.grid.current_posts:
            return True
        return False

    def show_preview_grid_without_reload(self) -> None:
        self.content_stack.setCurrentWidget(self.grid)
        self.grid.setVisible(True)
        self.grid.viewport().setVisible(True)
        self.grid.container.setVisible(True)
        self.grid.update_columns()
        if self.grid.items:
            self.grid.relayout()
        self.grid.viewport().update()
        self.grid.container.update()
        self.grid.update()
        self.content_stack.update()
        self.main_widget.update()
        self.update()

    def on_tab_activated(self) -> None:
        # Nicht mehr bei jedem Tabwechsel stumpf neu laden. Wenn schon gültige
        # Thumbnails da sind, werden sie nur wieder eingeblendet. Reload nur bei
        # erstem Öffnen oder geänderten Filtern. Revolutionär: nicht unnötig arbeiten.
        if not self.preview_needs_reload():
            self.show_preview_grid_without_reload()
            self.status_bar.showMessage("Preview bereit.", 3000)
            return

        self.show_preview_loading("Lädt Preview…")
        self.content_stack.setCurrentWidget(self.loading_panel)
        self.loading_panel.raise_()
        self.content_stack.repaint()
        self.main_widget.repaint()
        self.repaint()
        QTimer.singleShot(80, self.reload_posts)


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

    def selected_sort_key(self) -> str:
        value = self.sort_combo.currentData()
        return str(value) if value is not None else "id_desc"

    def selected_recommendation_minimum(self) -> float | None:
        if not self.recommendation_filter_checkbox.isChecked():
            return None
        return float(self.recommendation_min_spin.value())

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

        rules_by_category: dict[int, list[Any]] = {}
        for rule in rules:
            category_id = int(rule["category_id"])
            if category_id not in by_category:
                continue
            rules_by_category.setdefault(category_id, []).append(rule)

        for category_id, category_rules in rules_by_category.items():
            by_category[category_id]["match_groups"] = build_category_match_groups(category_rules)

        self.category_rule_cache = sorted(
            by_category.values(),
            key=lambda entry: (entry["sort_order"], entry["name"]),
        )

    def suggest_category_from_tags(self, tags_text: str) -> str:
        tags = set(tags_text.split())

        for category in self.category_rule_cache:
            name = category["name"]

            match_groups = category.get("match_groups", [])
            if not match_groups:
                continue

            for required_tags, forbidden_tags in match_groups:
                if forbidden_tags.intersection(tags):
                    continue
                if required_tags and required_tags.issubset(tags):
                    return name

        return "_unmatched"

    def enrich_preview_rows_with_categories(self, rows: list[Any]) -> list[dict[str, Any]]:
        self.load_category_rule_cache()

        enriched: list[dict[str, Any]] = []

        for row in rows:
            data = dict(row)
            tags_text = str(data.get("tags") or "")
            tags = {tag for tag in tags_text.split() if tag}

            assigned_category = data.get("assigned_category_name")
            assigned_source = data.get("assigned_category_source")

            if assigned_category:
                data["preview_category_name"] = str(assigned_category)
                data["preview_category_source"] = str(assigned_source or "manual")
            else:
                data["preview_category_name"] = self.suggest_category_from_tags(tags_text)
                data["preview_category_source"] = "auto"

            recommendation = self.recommendation_engine.score_tags(tags)
            data["local_score"] = recommendation.score
            data["recommendation_score"] = recommendation.score
            data["recommendation_positive"] = ", ".join(recommendation.positive)
            data["recommendation_negative"] = ", ".join(recommendation.negative)
            data["recommendation_ignored_count"] = len(recommendation.ignored)
            data["recommendation_used_count"] = recommendation.used_count

            # Until a later LLM scorer exists, final_score mirrors the local
            # recommendation value when no explicit final_score was persisted.
            if data.get("final_score") is None:
                data["final_score"] = recommendation.score

            enriched.append(data)

        return enriched

    def sort_preview_rows_in_python(self, rows: list[dict[str, Any]], sort_key: str) -> list[dict[str, Any]]:
        if sort_key == "category":
            return sorted(
                rows,
                key=lambda row: (
                    str(row.get("preview_category_name") or "_unmatched").lower(),
                    -int(row.get("id") or 0),
                ),
            )

        if sort_key == "recommendation_desc":
            return sorted(
                rows,
                key=lambda row: (
                    -float(row.get("recommendation_score") or 0.0),
                    -int(row.get("id") or 0),
                ),
            )

        if sort_key == "recommendation_asc":
            return sorted(
                rows,
                key=lambda row: (
                    float(row.get("recommendation_score") or 0.0),
                    -int(row.get("id") or 0),
                ),
            )

        return rows

    def category_matches_filter(self, row: dict[str, Any], category_filter: str) -> bool:
        if category_filter == "__all__":
            return True

        category_name = str(row.get("preview_category_name") or "_unmatched")

        if category_filter == "__unmatched__":
            return category_name in {"", "_unmatched", "None"}

        return category_name == category_filter

    def recommendation_matches_filter(self, row: dict[str, Any], minimum: float | None) -> bool:
        if minimum is None:
            return True
        try:
            score = float(row.get("recommendation_score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        return score >= minimum

    def preview_score_summary(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "Vorauswahl: keine Treffer"

        scores: list[float] = []
        for row in rows:
            try:
                scores.append(float(row.get("recommendation_score") or 0.0))
            except (TypeError, ValueError):
                scores.append(0.0)

        positive = sum(1 for score in scores if score > 0.0)
        negative = sum(1 for score in scores if score < 0.0)
        neutral = len(scores) - positive - negative
        best = max(scores) if scores else 0.0
        worst = min(scores) if scores else 0.0
        average = sum(scores) / len(scores) if scores else 0.0
        return (
            f"Vorauswahl: +{positive} / 0:{neutral} / -{negative} | "
            f"Ø {average:+.1f} | Best {best:+.1f} | Worst {worst:+.1f}"
        )

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
            "worklist": {"new", "potential"},
            "saved": {"saved"},
            "rejected": {"rejected"},
            "known": {"already_known"},
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
        self._fetch_running = False

        self.on_passive_filter_changed()

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

        self.on_passive_filter_changed()

    def sync_all_checkbox_from_statuses(self) -> None:
        all_checked = all(checkbox.isChecked() for checkbox in self.status_checkboxes.values())

        self._syncing_status_checkboxes = True
        try:
            self.all_status_checkbox.setChecked(all_checked)
        finally:
            self._syncing_status_checkboxes = False
        self._fetch_running = False

    def set_checked_statuses(self, statuses: set[str]) -> None:
        self._syncing_status_checkboxes = True
        try:
            for status, checkbox in self.status_checkboxes.items():
                checkbox.setChecked(status in statuses)
        finally:
            self._syncing_status_checkboxes = False
        self._fetch_running = False

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

    def on_passive_filter_changed(self, *_args) -> None:
        self._filters_dirty = True
        self.status_bar.showMessage("Filter geändert. Klicke auf Neu laden oder drücke Enter im Such-/Limit-Feld.", 4000)

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
        self.show_preview_loading("Lädt Preview…")
        self.status_bar.showMessage("Lädt Preview…")
        QApplication.processEvents()

        try:
            statuses = self.selected_statuses()
            text_filter = self.current_search_text()
            category_filter = self.selected_category_filter()
            recommendation_minimum = self.selected_recommendation_minimum()
            sort_key = self.selected_sort_key()
            self.current_limit = int(self.limit_spin.value())

            python_sorted = sort_key in {"category", "recommendation_desc", "recommendation_asc"}
            internal_limit = self.current_limit if category_filter == "__all__" and not python_sorted else max(self.current_limit * 5, 2000)

            candidates = self.fetch_preview_posts_by_statuses(
                statuses=statuses,
                text_filter=text_filter,
                limit=internal_limit,
                offset=self.current_offset,
                sort_key=sort_key,
            )
            enriched = self.enrich_preview_rows_with_categories(candidates)
            filtered = [
                row
                for row in enriched
                if self.category_matches_filter(row, category_filter)
                and self.recommendation_matches_filter(row, recommendation_minimum)
            ]
            filtered = self.sort_preview_rows_in_python(filtered, sort_key)

            posts = filtered[: self.current_limit]
            total = len(filtered)

            self.grid.set_posts(posts)
            self._has_loaded_once = True
            self._filters_dirty = False

            status_text = self.status_filter_description(statuses)
            category_text = self.category_filter.currentText()
            recommendation_filter_text = (
                f"Vorauswahl ≥ {recommendation_minimum:+.1f}"
                if recommendation_minimum is not None
                else "Vorauswahl: alle"
            )
            score_summary = self.preview_score_summary(filtered)

            self.info_label.setText(
                f"Ansicht: {VIEW_LABELS.get(self.selected_view_mode(), self.selected_view_mode())} | "
                f"Angezeigt: {len(posts)} / Treffer im geladenen Bereich: {total} | "
                f"Status: {status_text} | Kategorie: {category_text} | "
                f"{recommendation_filter_text} | "
                f"Sortierung: {self.sort_combo.currentText()} | "
                f"Thumbnail: {self.grid.thumbnail_size}px\n"
                f"{score_summary}"
            )
            if posts:
                self.status_bar.showMessage(f"Lädt Preview-Karten… 0/{len(posts)}")
            else:
                self.hide_preview_loading()
                self.status_bar.showMessage("Preview geladen: keine Treffer", 5000)

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

        # Statusfilter gilt immer, auch bei Tag-/Textsuche.
        # Wer gespeicherte lokale Bilder suchen will, aktiviert den Status "saved"
        # oder die Ansicht "Alle bekannten Posts". Revolutionäres Konzept: Filter filtern.
        if not statuses:
            where_parts.append("1 = 0")
        elif set(statuses) != set(STATUS_ORDER):
            placeholders = ", ".join("?" for _ in statuses)
            where_parts.append(f"p.status IN ({placeholders})")
            parameters.extend(statuses)

        if text_filter:
            positive_terms, negative_terms = parse_preview_search_terms(text_filter)

            for term in positive_terms:
                pattern = f"%{term}%"
                if self.is_path_like_search_term(term):
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
                                  AND pt.tag = ? COLLATE NOCASE
                            )
                        )
                        """
                    )
                    parameters.extend([pattern, pattern, pattern, term])
                else:
                    where_parts.append(
                        """
                        (
                            CAST(p.id AS TEXT) LIKE ?
                            OR EXISTS (
                                SELECT 1
                                FROM post_tags pt
                                WHERE pt.post_id = p.id
                                  AND pt.tag = ? COLLATE NOCASE
                            )
                        )
                        """
                    )
                    parameters.extend([pattern, term])

            for term in negative_terms:
                where_parts.append(
                    """
                    NOT EXISTS (
                        SELECT 1
                        FROM post_tags pt_excl
                        WHERE pt_excl.post_id = p.id
                          AND pt_excl.tag = ? COLLATE NOCASE
                    )
                    """
                )
                parameters.append(term)

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
        sort_key: str = "id_desc",
    ) -> list[Any]:
        where_sql, parameters = self.build_preview_where(statuses, text_filter)
        order_sql = SQL_SORT_ORDER.get(sort_key, SQL_SORT_ORDER["id_desc"])
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
                    p.file_url,
                    p.large_file_url,
                    p.preview_url,
                    p.file_ext,
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
                LEFT JOIN post_reviews pr ON pr.post_id = p.id
                {where_sql}
                GROUP BY p.id
                ORDER BY {order_sql}
                LIMIT ?
                OFFSET ?
                """,
                parameters,
            ).fetchall()
        )

    # -------------------------------------------------------------------------
    # Thumbnail-Reparatur aus Preview
    # -------------------------------------------------------------------------

    def reload_selected_thumbnails(self) -> None:
        post_ids = self.grid.selected_or_current_post_ids()
        self.reload_thumbnails_for_posts(post_ids)

    def reload_thumbnails_for_posts(self, post_ids: list[int]) -> None:
        clean_ids = [int(post_id) for post_id in post_ids if post_id]
        if not clean_ids:
            self.status_bar.showMessage("Thumbnail neu laden: kein Post ausgewählt.", 4000)
            return

        self.reload_thumbnails_button.setEnabled(False)
        self.status_bar.showMessage(f"Lade {len(clean_ids)} Thumbnail(s) neu…")
        QApplication.processEvents()

        api = DanbooruApi(self.config)
        cache = ThumbnailCache(self.config, api.session)
        updated = 0
        failed: list[str] = []

        try:
            for post_id in clean_ids:
                try:
                    post = self.thumbnail_post_payload_from_db(post_id)
                    thumbnail_path = cache.cache_thumbnail(post, force=True)
                    if not thumbnail_path:
                        failed.append(str(post_id))
                        continue

                    self.db.execute(
                        "UPDATE posts SET thumbnail_path = ? WHERE id = ?",
                        (thumbnail_path, post_id),
                    )
                    self.db.commit()
                    self.grid.update_card_thumbnail(post_id, thumbnail_path)
                    updated += 1
                except Exception as exc:  # noqa: BLE001
                    failed.append(f"{post_id}: {exc}")
        finally:
            self.reload_thumbnails_button.setEnabled(True)

        if failed:
            self.status_bar.showMessage(
                f"Thumbnails neu geladen: {updated}, Fehler: {len(failed)}",
                8000,
            )
            QMessageBox.warning(
                self,
                "Thumbnail neu laden",
                "Einige Thumbnails konnten nicht neu geladen werden:\n" + "\n".join(failed[:12]),
            )
        else:
            self.status_bar.showMessage(f"Thumbnails neu geladen: {updated}", 5000)

    def thumbnail_post_payload_from_db(self, post_id: int) -> dict[str, Any]:
        row = self.db.execute(
            """
            SELECT id, file_url, large_file_url, preview_url, file_ext
            FROM posts
            WHERE id = ?
            """,
            (int(post_id),),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Post {post_id} nicht in der DB")

        post = {
            "id": int(row["id"]),
            "file_url": row["file_url"],
            "large_file_url": row["large_file_url"],
            "preview_file_url": row["preview_url"],
            "file_ext": row["file_ext"],
        }

        if not (post["file_url"] or post["large_file_url"] or post["preview_file_url"]):
            # Alte DB-Zeilen können kaputte/fehlende URLs haben. Dann holen wir
            # den Post frisch nach. Manchmal muss man Daten eben nochmal fragen,
            # weil sie sich beim ersten Mal dumm gestellt haben.
            post = api_post = DanbooruApi(self.config).get_post(int(post_id))
            self.db.execute(
                """
                UPDATE posts
                SET file_url = ?, large_file_url = ?, preview_url = ?, file_ext = ?
                WHERE id = ?
                """,
                (
                    api_post.get("file_url"),
                    api_post.get("large_file_url"),
                    api_post.get("preview_file_url"),
                    api_post.get("file_ext"),
                    int(post_id),
                ),
            )
            self.db.commit()

        return post

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
        if status == "deleted":
            self.status_bar.showMessage(f"Post {post_id} wurde aus der DB entfernt")
            self.schedule_reload()
            return

        self.grid.update_card_status(post_id, status)
        self.status_bar.showMessage(f"Post {post_id} → {STATUS_LABELS.get(status, status)}")


    def on_statuses_changed(self, post_ids: list[int], status: str) -> None:
        count = len(post_ids)
        self.status_bar.showMessage(f"{count} Post(s) → {STATUS_LABELS.get(status, status)}")

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
