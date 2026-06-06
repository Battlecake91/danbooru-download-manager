from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.core.category_engine import CategoryEngine, CategoryMatch
from app.core.database import Database
from app.core.filename_builder import FilenameBuilder, FilenamePreviewDetails
from app.services.download_service import DownloadService


class AlreadySavedError(RuntimeError):
    def __init__(self, post_id: int, final_path: str | None) -> None:
        self.post_id = post_id
        self.final_path = final_path
        message = f"Post {post_id} is already saved."
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
        diagnostic: Callable[[str], None] | None = None,
    ) -> tuple[Path, FilenamePreviewDetails] | None:
        def diag(message: str) -> None:
            if diagnostic is not None:
                diagnostic(f"FINAL_PATH {message}")

        diag(f"begin post_id={post_id} category={getattr(category, 'name', None)!r}")
        diag("get_post_detail begin")
        row = self.db.get_post_detail(post_id)
        diag(f"get_post_detail end found={row is not None}")
        if row is not None and row["final_file_path"] and category is None:
            final_path = Path(str(row["final_file_path"]))
            source_path = final_path if final_path.exists() else Path(str(row["final_file_path"]))
            diag(f"saved-path branch final_path={str(final_path)!r} exists={final_path.exists()}")
            diag("filename_builder saved-path begin")
            details = self.filename_builder.build_preview_details(post_id, source_path, diagnostic=diagnostic)
            diag("filename_builder saved-path end")
            return final_path, details

        diag("source_path_for_post begin")
        source_path = self.source_path_for_post(post_id, download_if_missing=False)
        diag(f"source_path_for_post end path={str(source_path) if source_path else None!r}")
        if source_path is None:
            # No display/original file is available yet. For a pure preview, a synthetic
            # source with the correct extension is enough so the filename is still
            # visible and does not crawl out of the fog only after download.
            diag("synthetic source get_post_detail begin")
            row = self.db.get_post_detail(post_id)
            diag("synthetic source get_post_detail end")
            ext = str(row["file_ext"] or "bin").strip(".") if row is not None else "bin"
            source_path = Path(f"{post_id}_preview_source.{ext or 'bin'}")
            diag(f"synthetic source path={str(source_path)!r}")

        diag("effective category begin")
        effective_category = category or self.suggest_category(post_id)
        diag(f"effective category end name={effective_category.name!r}")
        diag("output_directory_for_category begin")
        output_dir = self.category_engine.output_directory_for_category(effective_category)
        diag(f"output_directory_for_category end path={str(output_dir)!r}")
        diag("filename_builder begin")
        details = self.filename_builder.build_preview_details(post_id, source_path, diagnostic=diagnostic)
        diag(f"filename_builder end filename={details.filename!r}")
        desired_path = output_dir / details.filename
        diag(f"unique_path begin desired={str(desired_path)!r}")
        final_path = unique_path(desired_path, diagnostic=diagnostic)
        diag(f"unique_path end result={str(final_path)!r}")
        diag("end")
        return final_path, details

    def save_post(
        self,
        post_id: int,
        category: CategoryMatch | None = None,
        overwrite_existing: bool = False,
    ) -> SaveResult:
        row = self.db.get_post_detail(post_id)
        old_final_path = Path(str(row["final_file_path"])) if row is not None and row["final_file_path"] else None

        if old_final_path is not None and not overwrite_existing:
            raise AlreadySavedError(post_id, str(old_final_path))

        source_path = self.source_path_for_post(post_id, download_if_missing=True, prefer_final=False)
        if source_path is None:
            raise RuntimeError(f"No source file for post {post_id}")

        suggested_category = self.suggest_category(post_id)
        assigned_category_row = self.db.get_assigned_category_for_post(post_id)
        assigned_source = str(assigned_category_row["assignment_source"] or "manual") if assigned_category_row is not None else None

        if category is None and assigned_category_row is not None:
            category = self.category_by_name(str(assigned_category_row["name"]))

        category = category or suggested_category
        category_source = assigned_source or ("manual" if category.name != suggested_category.name else "auto")

        output_dir = self.category_engine.output_directory_for_category(category)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = self.filename_builder.build_filename(post_id, source_path)
        desired_path = output_dir / filename

        if old_final_path is not None and old_final_path.resolve() == desired_path.resolve():
            final_path = old_final_path
        elif overwrite_existing:
            final_path = unique_path(desired_path)
        else:
            final_path = unique_path(desired_path)

        tmp_path = final_path.with_name(final_path.name + ".replace_tmp")
        shutil.copy2(source_path, tmp_path)
        tmp_path.replace(final_path)

        if old_final_path is not None and old_final_path != final_path and old_final_path.exists():
            try:
                old_final_path.unlink()
            except OSError:
                # Do not fail hard. A leftover old image is annoying,
                # but an aborted save operation would be even worse.
                pass

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
            self.db.execute("DELETE FROM post_categories WHERE post_id = ?", (post_id,))
            self.db.execute(
                """
                INSERT INTO post_categories (post_id, category_id, source)
                VALUES (?, ?, ?)
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


    def overwrite_saved_file_with_original(self, post_id: int, force_download: bool = True) -> Path:
        """Replace the existing final file with Danbooru's file_url/original.

        This keeps the current final filename and directory. If the DB points to
        a final path but the file is missing, the directory is recreated and the
        original is written there. Exactly the thing humans call "repair" after
        trusting thumbnails.
        """
        row = self.db.get_post_detail(post_id)
        if row is None:
            raise RuntimeError(f"Post {post_id} is not in the database")

        final_value = row["final_file_path"]
        if not final_value:
            raise RuntimeError("final_file_path is missing, so no overwrite target is known")

        final_path = Path(str(final_value))
        final_path.parent.mkdir(parents=True, exist_ok=True)

        source_value = self.download_service.ensure_full_original_cached(post_id, force=force_download)
        if not source_value:
            raise RuntimeError("Original file could not be downloaded")

        source_path = Path(source_value)
        if not source_path.exists():
            raise RuntimeError(f"Original cache is missing: {source_path}")

        tmp_path = final_path.with_name(final_path.name + ".replace_tmp")
        shutil.copy2(source_path, tmp_path)
        tmp_path.replace(final_path)

        self.db.execute(
            """
            UPDATE posts
            SET final_file_path = ?,
                final_directory = ?,
                saved_at = COALESCE(saved_at, CURRENT_TIMESTAMP),
                status = 'saved'
            WHERE id = ?
            """,
            (str(final_path), str(final_path.parent), post_id),
        )
        self.db.commit()
        self.db.set_post_status(post_id, "saved", self.config)
        return final_path

    def assert_not_already_saved(self, post_id: int) -> None:
        row = self.db.get_post_detail(post_id)
        if row is None:
            return

        status = str(row["status"] or "")
        final_path = str(row["final_file_path"]) if row["final_file_path"] else None

        if status == "saved" or final_path:
            raise AlreadySavedError(post_id, final_path)

    def source_path_for_post(
        self,
        post_id: int,
        download_if_missing: bool,
        prefer_final: bool = True,
    ) -> Path | None:
        row = self.db.get_post_detail(post_id)
        if row is None:
            return None

        final_value = row["final_file_path"]
        if prefer_final and final_value:
            final_path = Path(str(final_value))
            if final_path.exists():
                return final_path

        if not download_if_missing:
            return None

        # Final save must never use a thumbnail, preview, or Danbooru large/sample
        # variant as the source. The viewer file may be smaller, but final save
        # is always downloaded freshly or separately from file_url.
        downloaded = self.download_service.ensure_full_original_cached(post_id)
        if downloaded:
            path = Path(downloaded)
            if path.exists():
                return path

        return None


def unique_path(path: Path, diagnostic: Callable[[str], None] | None = None) -> Path:
    if diagnostic is not None:
        diagnostic(f"UNIQUE_PATH initial exists check path={str(path)!r}")
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent

    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if diagnostic is not None and (counter <= 10 or counter % 100 == 0):
            diagnostic(f"UNIQUE_PATH probe counter={counter} candidate={str(candidate)!r}")
        if not candidate.exists():
            return candidate
        counter += 1
