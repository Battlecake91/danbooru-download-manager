from __future__ import annotations

import os
import webbrowser
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QGuiApplication, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.core.category_engine import CategoryMatch
from app.core.database import Database
from app.services.download_service import DownloadService
from app.danbooru.api import DanbooruApi
from app.gui.icon_utils import ensure_app_icon
from app.gui.tag_display import TypedTagListWidget, typed_tags_for_post
from app.services.final_save_service import AlreadySavedError, FinalSaveService
from app.services.post_import_service import PostImportService


STATUS_LABELS: dict[str, str] = {
    "new": "Neu",
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


class ImageViewerWindow(QMainWindow):
    status_changed = Signal(int, str)
    query_requested = Signal(str)

    def __init__(
        self,
        config: dict[str, Any],
        db: Database,
        post_ids: list[int],
        initial_post_id: int,
    ) -> None:
        super().__init__()

        self.config = config
        self.db = db
        self.post_ids = post_ids
        self.current_index = max(0, post_ids.index(initial_post_id)) if initial_post_id in post_ids else 0
        self.download_service = DownloadService(config, db)
        self.final_save_service = FinalSaveService(config, db)
        self.api = DanbooruApi(config)
        self.post_import_service = PostImportService(config, db)

        self.current_pixmap: QPixmap | None = None
        self.current_post_id: int | None = None
        self.shortcuts: list[QShortcut] = []
        self.suggested_category_name: str | None = None
        self.last_saved_path: Path | None = None
        self._tag_context_menu: QMenu | None = None
        self._related_context_menu: QMenu | None = None

        viewer_config = config.get("viewer", {}) or {}
        self.auto_advance_after_save = bool(viewer_config.get("auto_advance_after_save", True))
        self.auto_advance_after_reject = bool(viewer_config.get("auto_advance_after_reject", True))

        self.setWindowTitle("Danbooru Manager - Bildbetrachter")
        self.setWindowIcon(ensure_app_icon(config))
        self.setFocusPolicy(Qt.StrongFocus)

        self.toolbar = QToolBar("Viewer")
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.prev_button = QPushButton("← Vorheriges")
        self.prev_button.clicked.connect(self.previous_post)
        self.toolbar.addWidget(self.prev_button)

        self.next_button = QPushButton("Nächstes →")
        self.next_button.clicked.connect(self.next_post)
        self.toolbar.addWidget(self.next_button)

        self.toolbar.addSeparator()

        self.fit_checkbox = QCheckBox("Einpassen")
        self.fit_checkbox.setChecked(bool(viewer_config.get("fit_to_window", True)))
        self.fit_checkbox.stateChanged.connect(self.refresh_image)
        self.toolbar.addWidget(self.fit_checkbox)

        self.toolbar.addSeparator()

        self.final_save_button = QPushButton("Final speichern (F)")
        self.final_save_button.clicked.connect(self.final_save_current_post)
        self.toolbar.addWidget(self.final_save_button)

        self.refetch_button = QPushButton("Post neu holen")
        self.refetch_button.setToolTip("Lädt Post-Metadaten und Viewer-Bild neu von Danbooru.")
        self.refetch_button.clicked.connect(self.refetch_current_post)
        self.toolbar.addWidget(self.refetch_button)

        self.delete_db_button = QPushButton("Aus DB entfernen")
        self.delete_db_button.setToolTip("Entfernt den Post aus der lokalen Datenbank, löscht aber keine Bilddateien.")
        self.delete_db_button.clicked.connect(self.delete_current_post_from_database)
        self.toolbar.addWidget(self.delete_db_button)

        self.open_saved_folder_button = QPushButton("Zielordner öffnen")
        self.open_saved_folder_button.clicked.connect(self.open_saved_folder)
        self.toolbar.addWidget(self.open_saved_folder_button)

        self.open_local_image_button = QPushButton("Lokales Bild öffnen")
        self.open_local_image_button.clicked.connect(self.open_current_local_image)
        self.toolbar.addWidget(self.open_local_image_button)

        self.toolbar.addSeparator()

        self.open_original_button = QPushButton("Originalpost")
        self.open_original_button.clicked.connect(self.open_original_post)
        self.toolbar.addWidget(self.open_original_button)

        self.copy_link_button = QPushButton("Link kopieren")
        self.copy_link_button.clicked.connect(self.copy_original_post_url)
        self.toolbar.addWidget(self.copy_link_button)

        self.splitter = QSplitter(Qt.Horizontal)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFocusPolicy(Qt.NoFocus)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 400)
        self.image_label.setFocusPolicy(Qt.NoFocus)

        self.scroll_area.setWidget(self.image_label)
        self.splitter.addWidget(self.scroll_area)

        self.side_panel = QWidget()
        self.side_layout = QVBoxLayout(self.side_panel)

        self.info_label = QLabel()
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_label.setWordWrap(True)
        self.side_layout.addWidget(self.info_label)

        self.related_warning_label = QLabel()
        self.related_warning_label.setWordWrap(True)
        self.related_warning_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.related_warning_label.setStyleSheet(
            """
            QLabel {
                background: #5a3d00;
                color: #ffd166;
                border: 2px solid #ffb000;
                border-radius: 6px;
                padding: 6px;
                font-weight: bold;
            }
            """
        )
        self.related_warning_label.hide()
        self.side_layout.addWidget(self.related_warning_label)

        self.status_label = QLabel()
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.side_layout.addWidget(self.status_label)

        self.stars_label = QLabel()
        self.side_layout.addWidget(self.stars_label)

        self.related_label = QLabel("Bekannte Parent/Child-Posts:")
        self.side_layout.addWidget(self.related_label)

        self.related_list = QListWidget()
        self.related_list.itemDoubleClicked.connect(self.open_related_item)
        self.related_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.related_list.customContextMenuRequested.connect(self.open_related_context_menu)
        self.related_list.setMaximumHeight(130)
        self.side_layout.addWidget(self.related_list)

        self.category_label = QLabel()
        self.category_label.setWordWrap(True)
        self.category_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.side_layout.addWidget(self.category_label)

        self.category_combo = QComboBox()
        self.category_combo.currentIndexChanged.connect(self.on_category_changed)
        self.side_layout.addWidget(self.category_combo)

        self.final_path_label = QLabel()
        self.final_path_label.setWordWrap(True)
        self.final_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.side_layout.addWidget(self.final_path_label)

        self.filename_preview_label = QLabel()
        self.filename_preview_label.setWordWrap(True)
        self.filename_preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.filename_preview_label.setStyleSheet(
            "QLabel { background: #202020; border: 1px solid #555; border-radius: 6px; padding: 6px; }"
        )
        self.side_layout.addWidget(self.filename_preview_label)

        self.tags_label = QLabel("Tags nach Danbooru-Typ:")
        self.side_layout.addWidget(self.tags_label)

        self.tags_widget = TypedTagListWidget()
        for list_widget in self.tags_widget.lists.values():
            list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
            list_widget.customContextMenuRequested.connect(self.open_tag_context_menu)
            list_widget.itemDoubleClicked.connect(self.copy_single_tag_from_item)
        self.side_layout.addWidget(self.tags_widget, stretch=1)

        self.button_row_1 = QHBoxLayout()
        self.potential_button = QPushButton("H Potential")
        self.potential_button.clicked.connect(lambda: self.set_status("potential"))
        self.button_row_1.addWidget(self.potential_button)

        self.review_button = QPushButton("P Prüfen")
        self.review_button.clicked.connect(lambda: self.set_status("review"))
        self.button_row_1.addWidget(self.review_button)

        self.save_select_button = QPushButton("S Speichern vormerken")
        self.save_select_button.clicked.connect(lambda: self.set_status("selected_save"))
        self.button_row_1.addWidget(self.save_select_button)

        self.side_layout.addLayout(self.button_row_1)

        self.button_row_2 = QHBoxLayout()
        self.reject_button = QPushButton("Entf Ablehnen")
        self.reject_button.clicked.connect(lambda: self.set_status("rejected"))
        self.button_row_2.addWidget(self.reject_button)

        self.auto_reject_button = QPushButton("A Auto raus")
        self.auto_reject_button.clicked.connect(lambda: self.set_status("auto_rejected"))
        self.button_row_2.addWidget(self.auto_reject_button)

        self.new_button = QPushButton("N Neu")
        self.new_button.clicked.connect(lambda: self.set_status("new"))
        self.button_row_2.addWidget(self.new_button)

        self.side_layout.addLayout(self.button_row_2)

        self.hint_label = QLabel(
            "Hotkeys: ←/→ blättern | 1-5 Sterne | H/P/S Status | F final speichern | "
            "Entf ablehnen | A auto raus | N neu | O Originalpost | "
            "Tags markieren + Rechtsklick für Tag-Aktionen | "
            "Parent/Child: Doppelklick lokal öffnen, Rechtsklick für Lokal/Remote"
        )
        self.hint_label.setWordWrap(True)
        self.side_layout.addWidget(self.hint_label)

        self.splitter.addWidget(self.side_panel)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)

        self.setCentralWidget(self.splitter)

        self.install_shortcuts()
        self.load_current_post()

    def install_shortcuts(self) -> None:
        shortcut_map: list[tuple[str, Callable[[], None]]] = [
            ("Left", self.previous_post),
            ("Right", self.next_post),
            ("1", lambda: self.set_stars(1)),
            ("2", lambda: self.set_stars(2)),
            ("3", lambda: self.set_stars(3)),
            ("4", lambda: self.set_stars(4)),
            ("5", lambda: self.set_stars(5)),
            ("H", lambda: self.set_status("potential")),
            ("P", lambda: self.set_status("review")),
            ("S", lambda: self.set_status("selected_save")),
            ("F", self.final_save_current_post),
            ("A", lambda: self.set_status("auto_rejected")),
            ("Delete", lambda: self.set_status("rejected")),
            ("N", lambda: self.set_status("new")),
            ("O", self.open_original_post),
        ]

        for key_sequence, callback in shortcut_map:
            shortcut = QShortcut(QKeySequence(key_sequence), self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        self.refresh_image()

    def focusInEvent(self, event) -> None:  # noqa: ANN001
        super().focusInEvent(event)
        self.update_final_path_preview()

    def current_post_id_value(self) -> int | None:
        if 0 <= self.current_index < len(self.post_ids):
            return self.post_ids[self.current_index]
        return None

    def load_current_post(self) -> None:
        post_id = self.current_post_id_value()
        if post_id is None:
            return

        self.current_post_id = post_id
        self.last_saved_path = None

        row = self.db.get_post_detail(post_id)
        if row is None:
            return

        related = self.db.get_related_posts(post_id)
        related_total_count = len(related)
        related_local_count = sum(1 for related_row in related if self.local_path_for_post(int(related_row["id"])))

        self.setWindowTitle(f"Danbooru Manager - Bildbetrachter - {post_id}")

        self.info_label.setText(
            f"ID: {post_id}\n"
            f"Rating: {row['rating'] or '?'}\n"
            f"Score: {row['score'] if row['score'] is not None else '-'}\n"
            f"Parent: {row['parent_id'] if row['parent_id'] is not None else '-'}\n"
            f"Bekannte Parent/Child-Posts: {related_total_count} | lokal final gespeichert: {related_local_count}\n"
            f"Position: {self.current_index + 1} / {len(self.post_ids)}"
        )

        if related_local_count:
            self.related_warning_label.setText(
                f"⚠ Es existiert bereits mindestens eine lokal final gespeicherte Parent/Child-Version "
                f"({related_local_count}). Vor dem Speichern prüfen, sonst züchtest du Varianten-Duplikate."
            )
            self.related_warning_label.show()
        elif related_total_count:
            self.related_warning_label.setText(
                f"ℹ Es gibt {related_total_count} bekannte Parent/Child-DB-Einträge, "
                f"aber keine davon ist lokal final gespeichert."
            )
            self.related_warning_label.show()
        else:
            self.related_warning_label.hide()

        status = row["status"] or "new"
        has_final_path = bool(row["final_file_path"])
        self.status_label.setText(f"Status: {STATUS_LABELS.get(status, status)}")
        self.final_save_button.setEnabled(True)
        self.open_local_image_button.setEnabled(self.local_path_for_post(post_id) is not None)

        stars = row["stars"]
        self.stars_label.setText(f"Sterne: {stars if stars is not None else '-'}")

        self.update_related_posts(post_id, related)
        self.update_category_controls(post_id)

        self.populate_tag_lists(post_id)

        image_path = self.ensure_image_path(post_id, row)
        if image_path:
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                self.current_pixmap = pixmap
            else:
                self.current_pixmap = None
                self.image_label.setText(f"Bild konnte nicht geladen werden:\n{image_path}")
        else:
            self.current_pixmap = None
            self.image_label.setText("Keine lokale Bilddatei und Download fehlgeschlagen.")

        self.refresh_image()

    def populate_tag_lists(self, post_id: int) -> None:
        self.tags_widget.set_typed_tags(typed_tags_for_post(self.db, post_id))

    def update_related_posts(self, post_id: int, related: list[Any] | None = None) -> None:
        self.related_list.clear()

        if related is None:
            related = self.db.get_related_posts(post_id)

        for row in related:
            relation = str(row["relation"])
            relation_label = "Parent" if relation == "parent" else "Child"
            related_id = int(row["id"])
            local_path = self.local_path_for_post(related_id)

            local_marker = "lokal vorhanden" if local_path else "nur DB/Remote"
            text = (
                f"⚠ {relation_label}: {related_id} | "
                f"Status: {row['status'] or '-'} | "
                f"{local_marker}"
            )

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, related_id)
            item.setData(Qt.UserRole + 1, relation)
            item.setData(Qt.UserRole + 2, str(local_path) if local_path else "")

            font = QFont()
            font.setBold(True)
            item.setFont(font)

            if local_path:
                item.setForeground(QBrush(QColor("#ffd166")))
                item.setBackground(QBrush(QColor("#3a2a00")))
            else:
                item.setForeground(QBrush(QColor("#ffb000")))
                item.setBackground(QBrush(QColor("#242424")))

            self.related_list.addItem(item)

        if not related:
            item = QListWidgetItem("Keine bekannten Parent/Child-Posts")
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.related_list.addItem(item)

    def local_path_for_post(self, post_id: int) -> Path | None:
        row = self.db.get_post_detail(post_id)
        if row is None:
            return None

        final_path = row["final_file_path"]
        if not final_path:
            return None

        path = Path(str(final_path))
        if path.exists():
            return path

        return None

    def build_post_url(self, post_id: int) -> str:
        base_url = str(self.config.get("base_url", "https://danbooru.donmai.us")).rstrip("/")
        return f"{base_url}/posts/{post_id}"

    def open_related_item(self, item: QListWidgetItem) -> None:
        post_id = item.data(Qt.UserRole)
        if not post_id:
            return

        local_path = self.local_path_for_post(int(post_id))
        if local_path is not None:
            self.open_local_path(local_path)
            return

        webbrowser.open(self.build_post_url(int(post_id)))

    def open_related_context_menu(self, position) -> None:  # noqa: ANN001
        item = self.related_list.itemAt(position)
        if item is None or not (item.flags() & Qt.ItemIsEnabled):
            return

        post_id = item.data(Qt.UserRole)
        if not post_id:
            return

        post_id = int(post_id)
        local_path = self.local_path_for_post(post_id)

        menu = QMenu(self)
        self._related_context_menu = menu

        local_action = QAction("Lokal öffnen", menu)
        local_action.setEnabled(local_path is not None)
        local_action.triggered.connect(
            lambda checked=False, p=local_path: self.open_local_path(p) if p is not None else None
        )
        menu.addAction(local_action)

        folder_action = QAction("Lokalen Ordner öffnen", menu)
        folder_action.setEnabled(local_path is not None)
        folder_action.triggered.connect(
            lambda checked=False, p=local_path: self.open_local_folder(p) if p is not None else None
        )
        menu.addAction(folder_action)

        menu.addSeparator()

        remote_action = QAction("Remote Originalpost öffnen", menu)
        remote_action.triggered.connect(lambda checked=False, pid=post_id: webbrowser.open(self.build_post_url(pid)))
        menu.addAction(remote_action)

        copy_remote_action = QAction("Remote-Link kopieren", menu)
        copy_remote_action.triggered.connect(
            lambda checked=False, pid=post_id: QGuiApplication.clipboard().setText(self.build_post_url(pid))
        )
        menu.addAction(copy_remote_action)

        if local_path is not None:
            copy_local_action = QAction("Lokalen Pfad kopieren", menu)
            copy_local_action.triggered.connect(
                lambda checked=False, p=local_path: QGuiApplication.clipboard().setText(str(p))
            )
            menu.addAction(copy_local_action)

        menu.popup(self.related_list.viewport().mapToGlobal(position))

    def open_local_path(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.warning(self, "Lokale Datei fehlt", f"Datei existiert nicht:\n{path}")
            return

        os.startfile(path)

    def open_local_folder(self, path: Path) -> None:
        folder = path.parent if path.is_file() else path
        if not folder.exists():
            QMessageBox.warning(self, "Ordner fehlt", f"Ordner existiert nicht:\n{folder}")
            return

        os.startfile(folder)

    def update_category_controls(self, post_id: int) -> None:
        suggested = self.final_save_service.suggest_category(post_id)
        self.suggested_category_name = suggested.name
        assigned = self.db.get_assigned_category_for_post(post_id)
        assigned_name = str(assigned["name"]) if assigned is not None else None
        assigned_source = str(assigned["assignment_source"] or "manual") if assigned is not None else None

        self.category_combo.blockSignals(True)
        self.category_combo.clear()

        categories = self.final_save_service.list_categories()
        for category in categories:
            label = category.name
            suffixes: list[str] = []
            if category.name == suggested.name:
                suffixes.append("Vorschlag")
            if assigned_name and category.name == assigned_name:
                suffixes.append("gesetzt")
            if suffixes:
                label = f"{category.name}  ← {', '.join(suffixes)}"
            self.category_combo.addItem(label, category.name)

        target_name = assigned_name or suggested.name
        target_index = self.category_combo.findData(target_name)
        if target_index >= 0:
            self.category_combo.setCurrentIndex(target_index)

        self.category_combo.blockSignals(False)

        assigned_text = f"\nGesetzt: {assigned_name} ({assigned_source})" if assigned_name else ""
        self.category_label.setText(
            f"Vorschlag: {suggested.name}\n"
            f"Grund: {suggested.reason}"
            f"{assigned_text}"
        )
        self.update_final_path_preview()

    def selected_category(self) -> CategoryMatch | None:
        name = self.category_combo.currentData()
        if name is None:
            return None
        return self.final_save_service.category_by_name(str(name))

    def on_category_changed(self, *args) -> None:  # noqa: ANN002
        if self.current_post_id is not None:
            category = self.selected_category()
            if category is not None and category.id is not None:
                self.db.assign_post_category(self.current_post_id, category.id, "manual")
                self.category_label.setText(
                    f"Vorschlag: {self.suggested_category_name or '-'}\n"
                    f"Gesetzt: {category.name} (manual)"
                )
                self.status_changed.emit(self.current_post_id, str(self.db.get_post_detail(self.current_post_id)["status"] or "new"))
        self.update_final_path_preview()

    def update_final_path_preview(self) -> None:
        if self.current_post_id is None:
            return

        category = self.selected_category()
        preview = self.final_save_service.final_path_preview_details(self.current_post_id, category)

        if preview:
            final_preview, details = preview
            source = "auto"
            if category is not None and category.name != self.suggested_category_name:
                source = "manual"
            self.final_path_label.setText(f"Zielpfad ({source}): {final_preview}")
            self.filename_preview_label.setText(self.format_filename_preview(details))
        else:
            self.final_path_label.setText("Zielpfad: noch nicht bestimmbar, Datei wird bei F geladen.")
            self.filename_preview_label.setText("Dateiname: noch nicht bestimmbar")

    def format_filename_preview(self, details) -> str:  # noqa: ANN001
        def count_tags(key: str) -> int:
            return len(details.included_tags.get(key, []))

        excluded_total = sum(len(tags) for tags in details.excluded_tags.values())
        general_used = details.included_tags.get("general", [])[: int(self.config.get("filename", {}).get("tags_count", 8))]
        general_text = ", ".join(general_used[:10]) if general_used else "-"
        if len(general_used) > 10:
            general_text += f" … +{len(general_used) - 10}"

        return (
            "Dateiname-Vorschau:\n"
            f"{details.filename}\n"
            f"Pattern: {details.pattern}\n"
            f"Tags im Namen: Artist {count_tags('artist')}, Character {count_tags('character')}, "
            f"Serie {count_tags('copyright')}, General {len(general_used)}, Meta {count_tags('meta')}\n"
            f"General im Namen: {general_text}\n"
            f"Durch Filename-Exclude entfernt: {excluded_total}"
        )

    def ensure_image_path(self, post_id: int, row) -> str | None:  # noqa: ANN001
        for candidate in (
            row["original_cache_path"],
            row["original_path"],
            row["final_file_path"],
            row["thumbnail_path"],
            row["rejected_thumbnail_path"],
        ):
            if candidate and Path(str(candidate)).exists():
                return str(candidate)

        return self.download_service.ensure_original_cached(post_id)

    def refresh_image(self) -> None:
        if self.current_pixmap is None:
            return

        if self.fit_checkbox.isChecked():
            viewport_size = self.scroll_area.viewport().size()
            scaled = self.current_pixmap.scaled(
                viewport_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled)
            self.image_label.resize(scaled.size())
        else:
            self.image_label.setPixmap(self.current_pixmap)
            self.image_label.resize(self.current_pixmap.size())

    def previous_post(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_post()

    def next_post(self) -> None:
        if self.current_index < len(self.post_ids) - 1:
            self.current_index += 1
            self.load_current_post()

    def set_status(self, status: str) -> None:
        if self.current_post_id is None:
            return

        self.db.set_post_status(self.current_post_id, status, self.config)
        self.status_label.setText(f"Status: {STATUS_LABELS.get(status, status)}")
        self.status_changed.emit(self.current_post_id, status)

        if status in {"rejected", "auto_rejected"} and self.auto_advance_after_reject:
            self.next_post()

    def set_stars(self, stars: int) -> None:
        if self.current_post_id is None:
            return

        self.db.set_post_review(self.current_post_id, stars=stars)
        self.stars_label.setText(f"Sterne: {stars}")

    def final_save_current_post(self) -> None:
        if self.current_post_id is None:
            return

        post_id = self.current_post_id
        category = self.selected_category()
        row = self.db.get_post_detail(post_id)
        existing_path = Path(str(row["final_file_path"])) if row is not None and row["final_file_path"] else None
        existing_is_local = existing_path is not None and existing_path.exists()
        overwrite_existing = False

        if existing_path is not None:
            message = (
                "Dieser Post hat bereits einen finalen lokalen Zielpfad.\n\n"
                f"{existing_path}\n\n"
                "Mit Danbooru-file_url neu laden und final überschreiben/neu speichern?"
            )
            if not existing_is_local:
                message = (
                    "Für diesen Post ist ein finaler Zielpfad in der DB eingetragen, "
                    "die Datei fehlt aber lokal.\n\n"
                    f"{existing_path}\n\n"
                    "Original erneut laden und Zielpfad reparieren?"
                )

            answer = QMessageBox.question(self, "Finaldatei ersetzen", message)
            if answer != QMessageBox.StandardButton.Yes:
                return
            overwrite_existing = True

        try:
            result = self.final_save_service.save_post(post_id, category, overwrite_existing=overwrite_existing)
        except AlreadySavedError as exc:
            self.status_label.setText("Status: Gespeichert")
            self.final_path_label.setText(str(exc))
            QMessageBox.information(self, "Bereits gespeichert", str(exc))
            return
        except Exception as exc:
            self.final_path_label.setText(f"Speichern fehlgeschlagen: {exc}")
            QMessageBox.critical(self, "Speichern fehlgeschlagen", str(exc))
            return

        self.last_saved_path = result.final_path

        self.status_label.setText("Status: Gespeichert")
        self.category_label.setText(
            f"Kategorie: {result.category.name}\n"
            f"Quelle: {result.category_source}"
        )
        self.final_path_label.setText(f"Gespeichert: {result.final_path}")
        self.status_changed.emit(post_id, "saved")

        if self.auto_advance_after_save:
            self.next_post()
        else:
            self.load_current_post()

    def refetch_current_post(self) -> None:
        if self.current_post_id is None:
            return

        self.refetch_button.setEnabled(False)
        try:
            post = self.api.get_post(self.current_post_id)
            self.post_import_service.store_post(post)
            self.download_service.ensure_original_cached(self.current_post_id, force=True)
            self.load_current_post()
            QMessageBox.information(self, "Post neu geholt", f"Post {self.current_post_id} wurde von Danbooru aktualisiert.")
        except Exception as exc:
            QMessageBox.critical(self, "Neu holen fehlgeschlagen", str(exc))
        finally:
            self.refetch_button.setEnabled(True)

    def delete_current_post_from_database(self) -> None:
        if self.current_post_id is None:
            return

        post_id = self.current_post_id
        row = self.db.get_post_detail(post_id)
        final_path = str(row["final_file_path"] or "") if row is not None else ""

        answer = QMessageBox.question(
            self,
            "Post aus DB entfernen",
            f"Post {post_id} wirklich aus der lokalen Datenbank entfernen?\n\n"
            "Bilddateien werden NICHT gelöscht. Nur DB-Eintrag, Tags, Review und Kategoriezuordnung verschwinden.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.db.delete_post_record(post_id)
        self.status_changed.emit(post_id, "deleted")

        if post_id in self.post_ids:
            removed_index = self.post_ids.index(post_id)
            self.post_ids.pop(removed_index)
            if self.post_ids:
                self.current_index = min(removed_index, len(self.post_ids) - 1)
                self.load_current_post()
            else:
                self.current_post_id = None
                self.current_pixmap = None
                self.image_label.clear()
                self.info_label.setText("Keine Posts mehr im Viewer.")
                self.final_path_label.setText("")
                self.filename_preview_label.setText("")

        QMessageBox.information(
            self,
            "Aus DB entfernt",
            f"Post {post_id} wurde aus der DB entfernt. Dateien blieben liegen.\n{final_path}",
        )

    def selected_viewer_tags(self) -> list[str]:
        tags: list[str] = []
        seen: set[str] = set()

        for tag in self.tags_widget.selected_tags():
            tag = tag.strip()
            if tag and tag not in seen:
                tags.append(tag)
                seen.add(tag)

        return tags

    def tag_list_for_context_sender(self) -> QListWidget | None:
        sender = self.sender()
        return sender if isinstance(sender, QListWidget) else None

    def tags_for_context_position(self, position, list_widget: QListWidget | None = None) -> list[str]:  # noqa: ANN001
        if list_widget is None:
            list_widget = self.tag_list_for_context_sender()
        if list_widget is None:
            return []

        item = list_widget.itemAt(position)

        if item is not None and not item.isSelected():
            for other_list in self.tags_widget.lists.values():
                other_list.clearSelection()
            item.setSelected(True)
            return [str(item.data(Qt.UserRole) or item.text())]

        selected = self.selected_viewer_tags()
        if selected:
            return selected

        if item is not None:
            return [str(item.data(Qt.UserRole) or item.text())]

        return []

    def open_tag_context_menu(self, position) -> None:  # noqa: ANN001
        list_widget = self.tag_list_for_context_sender()
        tags = self.tags_for_context_position(position, list_widget)
        if not tags or list_widget is None:
            return

        frozen_tags = list(tags)
        menu = QMenu(self)
        self._tag_context_menu = menu

        category_menu = QMenu("Zu Kategorie hinzufügen", menu)
        category_names = self.db.list_category_names()

        if not category_names:
            disabled = QAction("Keine Kategorien vorhanden", menu)
            disabled.setEnabled(False)
            category_menu.addAction(disabled)

        for category_name in category_names:
            include_action = QAction(f"{category_name} / include", menu)
            include_action.triggered.connect(
                lambda checked=False, c=category_name, t=list(frozen_tags): QTimer.singleShot(
                    0,
                    lambda: self.safe_tag_action(lambda: self.add_tags_to_category(t, c, "include")),
                )
            )
            category_menu.addAction(include_action)

            exclude_action = QAction(f"{category_name} / exclude", menu)
            exclude_action.triggered.connect(
                lambda checked=False, c=category_name, t=list(frozen_tags): QTimer.singleShot(
                    0,
                    lambda: self.safe_tag_action(lambda: self.add_tags_to_category(t, c, "exclude")),
                )
            )
            category_menu.addAction(exclude_action)

            category_menu.addSeparator()

        menu.addMenu(category_menu)
        menu.addSeparator()

        exclude_state = self.filename_exclude_state(frozen_tags)

        if exclude_state in {"none", "mixed"}:
            add_exclude_action = QAction("Vom Dateinamen ausschließen", menu)
            add_exclude_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                    0,
                    lambda: self.safe_tag_action(lambda: self.add_tags_to_filename_exclude(t)),
                )
            )
            menu.addAction(add_exclude_action)

        if exclude_state in {"all", "mixed"}:
            remove_exclude_action = QAction("Filename-Ausschluss entfernen", menu)
            remove_exclude_action.triggered.connect(
                lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                    0,
                    lambda: self.safe_tag_action(lambda: self.remove_tags_from_filename_exclude(t)),
                )
            )
            menu.addAction(remove_exclude_action)

        menu.addSeparator()

        alias_action = QAction("Alias bearbeiten", menu)
        alias_action.triggered.connect(
            lambda checked=False, tag=frozen_tags[0]: QTimer.singleShot(
                0,
                lambda: self.safe_tag_action(lambda: self.edit_tag_alias(tag)),
            )
        )
        menu.addAction(alias_action)

        score_action = QAction("Manuellen Score bearbeiten", menu)
        score_action.triggered.connect(
            lambda checked=False, tag=frozen_tags[0]: QTimer.singleShot(
                0,
                lambda: self.safe_tag_action(lambda: self.edit_tag_score(tag)),
            )
        )
        menu.addAction(score_action)

        menu.addSeparator()

        copy_action = QAction("Tag(s) kopieren", menu)
        copy_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                0,
                lambda: self.copy_tags_to_clipboard(t),
            )
        )
        menu.addAction(copy_action)

        query_clipboard_action = QAction("Als Query in Zwischenablage", menu)
        query_clipboard_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                0,
                lambda: self.copy_tags_to_clipboard(t),
            )
        )
        menu.addAction(query_clipboard_action)

        query_preview_action = QAction("Als Query in Preview suchen", menu)
        query_preview_action.triggered.connect(
            lambda checked=False, t=list(frozen_tags): QTimer.singleShot(
                0,
                lambda: self.query_requested.emit(" ".join(t)),
            )
        )
        menu.addAction(query_preview_action)

        menu.popup(list_widget.viewport().mapToGlobal(position))

    def safe_tag_action(self, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as exc:
            QMessageBox.critical(self, "Tag-Aktion fehlgeschlagen", str(exc))

    def add_tags_to_category(self, tags: list[str], category_name: str, rule_type: str) -> None:
        for tag in tags:
            self.db.add_tag_to_category_rule(category_name, tag, rule_type)

        QMessageBox.information(
            self,
            "Kategorie aktualisiert",
            f"{len(tags)} Tag(s) zu {category_name}/{rule_type} hinzugefügt.",
        )

        if self.current_post_id is not None:
            self.update_category_controls(self.current_post_id)

    def filename_exclude_state(self, tags: list[str]) -> str:
        excluded = self.db.filename_excluded_tag_set()
        count = sum(1 for tag in tags if tag in excluded)

        if count == 0:
            return "none"
        if count == len(tags):
            return "all"
        return "mixed"

    def add_tags_to_filename_exclude(self, tags: list[str]) -> None:
        for tag in tags:
            self.db.add_filename_excluded_tag(tag, "viewer-manual")

        QMessageBox.information(
            self,
            "Filename-Exclude",
            f"{len(tags)} Tag(s) vom Dateinamen ausgeschlossen.",
        )
        self.update_final_path_preview()

    def remove_tags_from_filename_exclude(self, tags: list[str]) -> None:
        for tag in tags:
            self.db.remove_filename_excluded_tag(tag)

        QMessageBox.information(
            self,
            "Filename-Exclude",
            f"{len(tags)} Filename-Ausschluss/Ausschlüsse entfernt.",
        )
        self.update_final_path_preview()

    def edit_tag_alias(self, tag: str) -> None:
        current_alias = ""
        rows = self.db.fetch_tag_overview(search_text=tag, limit=100)
        for row in rows:
            if str(row["tag"]) == tag:
                current_alias = str(row["alias_tag"] or "")
                break

        text, ok = QInputDialog.getText(
            self,
            "Alias bearbeiten",
            f"LLM-Alias für Tag '{tag}'\nLeer lassen zum Entfernen:",
            text=current_alias,
        )

        if not ok:
            return

        self.db.set_tag_alias(tag, text.strip())

    def edit_tag_score(self, tag: str) -> None:
        current_value = 0.0
        rows = self.db.fetch_tag_overview(search_text=tag, limit=100)
        for row in rows:
            if str(row["tag"]) == tag and str(row["manual_score"]) not in {"", "None"}:
                try:
                    current_value = float(row["manual_score"])
                except ValueError:
                    current_value = 0.0
                break

        value, ok = QInputDialog.getDouble(
            self,
            "Manueller Score",
            f"Manueller Score für '{tag}' (-10 bis +10):",
            current_value,
            -10.0,
            10.0,
            3,
        )

        if not ok:
            return

        self.db.set_tag_manual_score(tag, value)

    def copy_single_tag_from_item(self, item: QListWidgetItem) -> None:
        tag = str(item.data(Qt.UserRole) or item.text())
        self.copy_tags_to_clipboard([tag])

    def copy_tags_to_clipboard(self, tags: list[str]) -> None:
        QGuiApplication.clipboard().setText(" ".join(tags))

    def build_original_post_url(self) -> str:
        post_id = self.current_post_id_value()
        base_url = str(self.config.get("base_url", "https://danbooru.donmai.us")).rstrip("/")
        return f"{base_url}/posts/{post_id}"

    def open_original_post(self) -> None:
        webbrowser.open(self.build_original_post_url())

    def copy_original_post_url(self) -> None:
        QGuiApplication.clipboard().setText(self.build_original_post_url())

    def open_saved_folder(self) -> None:
        path: Path | None = None

        if self.last_saved_path is not None:
            path = self.last_saved_path.parent
        elif self.current_post_id is not None:
            row = self.db.get_post_detail(self.current_post_id)
            if row and row["final_directory"]:
                path = Path(str(row["final_directory"]))
            elif row and row["final_file_path"]:
                path = Path(str(row["final_file_path"])).parent

        if path is None:
            QMessageBox.information(self, "Kein Zielordner", "Noch kein Zielordner bekannt.")
            return

        if not path.exists():
            QMessageBox.warning(self, "Ordner fehlt", f"Ordner existiert nicht:\n{path}")
            return

        os.startfile(path)

    def open_current_local_image(self) -> None:
        if self.current_post_id is None:
            return

        path = self.local_path_for_post(self.current_post_id)
        if path is None:
            QMessageBox.information(self, "Kein lokales Bild", "Für diesen Post existiert keine lokal final gespeicherte Datei.")
            return

        self.open_local_path(path)
