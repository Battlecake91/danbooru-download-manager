from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.category_engine import CategoryEngine, CategoryMatch
from app.core.database import Database
from app.core.filename_builder import FilenameBuilder, FilenamePreviewDetails
from app.services.download_service import DownloadService


class AlreadySavedError(RuntimeError):
    def __init__(self, post_id: int, final_path: str | None) -> None:
        self.post_id = post_id
        self.final_path = final_path
        message = f"Post {post_id} ist bereits gespeichert."
        if final_path:
            message += f"\nPfad: {final_path}"
        super().__init__(message)


@dataclass(frozen=True)
class SaveResult:
    post_id: int
    category: CategoryMatch
    source_path: Path
    final_path: Path
    category_source: str


class FinalSaveService:
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        self.config = config
        self.db = db
        self.category_engine = CategoryEngine(config, db)
        self.filename_builder = FilenameBuilder(config, db)
        self.download_service = DownloadService(config, db)

    def list_categories(self) -> list[CategoryMatch]:
        return self.category_engine.list_categories()

    def suggest_category(self, post_id: int) -> CategoryMatch:
        return self.category_engine.suggest_category_for_post(post_id)

    def category_by_name(self, name: str) -> CategoryMatch | None:
        return self.category_engine.category_by_name(name)

    def final_path_preview(self, post_id: int, category: CategoryMatch | None = None) -> Path | None:
        preview = self.final_path_preview_details(post_id, category)
        return preview[0] if preview is not None else None

    def final_path_preview_details(
        self,
        post_id: int,
        category: CategoryMatch | None = None,
    ) -> tuple[Path, FilenamePreviewDetails] | None:
        row = self.db.get_post_detail(post_id)
        if row is not None and row["final_file_path"]:
            final_path = Path(str(row["final_file_path"]))
            source_path = final_path if final_path.exists() else Path(str(row["final_file_path"]))
            details = self.filename_builder.build_preview_details(post_id, source_path)
            return final_path, details

        source_path = self.source_path_for_post(post_id, download_if_missing=False)
        if source_path is None:
            # Noch keine Anzeige-/Originaldatei vorhanden. Für die reine Vorschau reicht
            # eine synthetische Quelle mit korrekter Extension aus, damit der Dateiname
            # trotzdem sichtbar ist und nicht erst nach dem Download aus dem Nebel kriecht.
            row = self.db.get_post_detail(post_id)
            ext = str(row["file_ext"] or "bin").strip(".") if row is not None else "bin"
            source_path = Path(f"{post_id}_preview_source.{ext or 'bin'}")

        effective_category = category or self.suggest_category(post_id)
        output_dir = self.category_engine.output_directory_for_category(effective_category)
        details = self.filename_builder.build_preview_details(post_id, source_path)
        return unique_path(output_dir / details.filename), details

    def save_post(self, post_id: int, category: CategoryMatch | None = None) -> SaveResult:
        self.assert_not_already_saved(post_id)

        source_path = self.source_path_for_post(post_id, download_if_missing=True)
        if source_path is None:
            raise RuntimeError(f"Keine Quelldatei für Post {post_id}")

        category = category or self.suggest_category(post_id)
        suggested_category = self.suggest_category(post_id)
        category_source = "manual" if category.name != suggested_category.name else "auto"

        output_dir = self.category_engine.output_directory_for_category(category)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = self.filename_builder.build_filename(post_id, source_path)
        final_path = unique_path(output_dir / filename)

        shutil.copy2(source_path, final_path)

        self.db.execute(
            """
            UPDATE posts
            SET final_file_path = ?,
                final_directory = ?,
                saved_at = CURRENT_TIMESTAMP,
                status = 'saved'
            WHERE id = ?
            """,
            (str(final_path), str(output_dir), post_id),
        )

        if category.id is not None:
            self.db.execute(
                """
                INSERT INTO post_categories (post_id, category_id, source)
                VALUES (?, ?, ?)
                ON CONFLICT(post_id, category_id) DO UPDATE SET source = excluded.source
                """,
                (post_id, category.id, category_source),
            )

        self.db.commit()
        self.db.set_post_status(post_id, "saved", self.config)

        return SaveResult(
            post_id=post_id,
            category=category,
            source_path=source_path,
            final_path=final_path,
            category_source=category_source,
        )

    def assert_not_already_saved(self, post_id: int) -> None:
        row = self.db.get_post_detail(post_id)
        if row is None:
            return

        status = str(row["status"] or "")
        final_path = str(row["final_file_path"]) if row["final_file_path"] else None

        if status == "saved" or final_path:
            raise AlreadySavedError(post_id, final_path)

    def source_path_for_post(self, post_id: int, download_if_missing: bool) -> Path | None:
        row = self.db.get_post_detail(post_id)
        if row is None:
            return None

        final_value = row["final_file_path"]
        if final_value:
            final_path = Path(str(final_value))
            if final_path.exists():
                return final_path

        if not download_if_missing:
            return None

        # Für finales Speichern darf niemals ein Thumbnail, Preview oder
        # Danbooru-large/sample als Quelle dienen. Die Viewer-Datei kann kleiner
        # sein, final wird aber immer aus file_url neu bzw. separat geladen.
        downloaded = self.download_service.ensure_full_original_cached(post_id)
        if downloaded:
            path = Path(downloaded)
            if path.exists():
                return path

        return None


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent

    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
