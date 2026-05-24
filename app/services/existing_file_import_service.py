from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.core.category_engine import CategoryEngine, CategoryMatch
from app.core.database import Database
from app.core.filename_builder import FilenameBuilder
from app.danbooru.api import DanbooruApi
from app.services.post_import_service import PostImportService

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".avif",
}

MD5_RE = re.compile(r"(?<![0-9a-fA-F])([0-9a-fA-F]{32})(?![0-9a-fA-F])")


@dataclass
class ExistingFileImportProgress:
    phase: str = "running"
    current: int = 0
    total: int = 0
    path: str = ""
    target_path: str = ""
    md5_hash: str = ""
    post_id: int | None = None
    imported: int = 0
    updated: int = 0
    renamed: int = 0
    skipped_rename: int = 0
    skipped_no_md5: int = 0
    not_found: int = 0
    errors: int = 0
    message: str = ""


@dataclass
class ExistingFileImportResult:
    scanned_files: int = 0
    imported_posts: int = 0
    updated_posts: int = 0
    renamed_files: int = 0
    skipped_rename: int = 0
    skipped_no_md5: int = 0
    not_found: int = 0
    errors: int = 0
    category_name: str = ""


class ExistingFileImportService:
    def __init__(
        self,
        config: dict[str, Any],
        db: Database,
        progress_callback: Callable[[ExistingFileImportProgress], None] | None = None,
    ) -> None:
        self.config = config
        self.db = db
        self.api = DanbooruApi(config)
        self.post_import_service = PostImportService(config, db)
        self.category_engine = CategoryEngine(config, db)
        self.filename_builder = FilenameBuilder(config, db)
        self.progress_callback = progress_callback

    def emit_progress(self, progress: ExistingFileImportProgress) -> None:
        if self.progress_callback is not None:
            self.progress_callback(progress)

    def import_folder(
        self,
        folder: str | Path,
        category_id: int,
        *,
        recursive: bool = True,
        rename_after_import: bool = False,
    ) -> ExistingFileImportResult:
        root = Path(folder).expanduser()
        if not root.exists() or not root.is_dir():
            raise RuntimeError(f"Import-Ordner nicht gefunden: {root}")

        category = self.category_match_for_id(category_id)
        result = ExistingFileImportResult(
            scanned_files=len(self.find_import_files(root, recursive=recursive)),
            category_name=category.name,
        )
        files = self.find_import_files(root, recursive=recursive)
        result.scanned_files = len(files)

        self.emit_progress(
            ExistingFileImportProgress(
                phase="start",
                total=len(files),
                message=f"Import gestartet: {len(files)} Dateien, Kategorie {result.category_name}",
            )
        )

        for index, path in enumerate(files, start=1):
            md5_hash = extract_md5_from_filename(path.name)
            base_progress = ExistingFileImportProgress(
                phase="file",
                current=index,
                total=len(files),
                path=str(path),
                md5_hash=md5_hash or "",
                imported=result.imported_posts,
                updated=result.updated_posts,
                renamed=result.renamed_files,
                skipped_rename=result.skipped_rename,
                skipped_no_md5=result.skipped_no_md5,
                not_found=result.not_found,
                errors=result.errors,
            )

            if not md5_hash:
                result.skipped_no_md5 += 1
                base_progress.phase = "skip"
                base_progress.skipped_no_md5 = result.skipped_no_md5
                base_progress.message = f"Übersprungen, kein MD5 im Dateinamen: {path.name}"
                self.emit_progress(base_progress)
                continue

            try:
                post = self.api.get_post_by_md5(md5_hash)
                if post is None:
                    result.not_found += 1
                    base_progress.phase = "not_found"
                    base_progress.not_found = result.not_found
                    base_progress.message = f"Kein Danbooru-Post für MD5 {md5_hash}: {path.name}"
                    self.emit_progress(base_progress)
                    continue

                post_id = int(post["id"])
                existing = self.db.execute("SELECT id FROM posts WHERE id = ?", (post_id,)).fetchone()
                self.post_import_service.store_post(post)
                self.db.import_existing_saved_file(
                    post_id=post_id,
                    category_id=int(category_id),
                    file_path=str(path),
                    source="existing-file-import",
                )

                current_path = path
                rename_message = ""
                if rename_after_import:
                    try:
                        rename_result = self.rename_saved_post_file(post_id, category=category)
                        if rename_result.renamed:
                            result.renamed_files += 1
                            current_path = rename_result.final_path
                            rename_message = f"; umbenannt: {rename_result.final_path.name}"
                        else:
                            result.skipped_rename += 1
                            rename_message = "; Name bereits aktuell"
                    except Exception as exc:
                        result.errors += 1
                        rename_message = f"; Umbenennen fehlgeschlagen: {exc}"

                if existing is None:
                    result.imported_posts += 1
                    phase = "imported"
                    action = "importiert"
                else:
                    result.updated_posts += 1
                    phase = "updated"
                    action = "aktualisiert"

                self.emit_progress(
                    ExistingFileImportProgress(
                        phase=phase,
                        current=index,
                        total=len(files),
                        path=str(current_path),
                        target_path=str(current_path),
                        md5_hash=md5_hash,
                        post_id=post_id,
                        imported=result.imported_posts,
                        updated=result.updated_posts,
                        renamed=result.renamed_files,
                        skipped_rename=result.skipped_rename,
                        skipped_no_md5=result.skipped_no_md5,
                        not_found=result.not_found,
                        errors=result.errors,
                        message=f"Post {post_id} {action}: {path.name}{rename_message}",
                    )
                )
            except Exception as exc:
                result.errors += 1
                self.emit_progress(
                    ExistingFileImportProgress(
                        phase="error",
                        current=index,
                        total=len(files),
                        path=str(path),
                        md5_hash=md5_hash,
                        imported=result.imported_posts,
                        updated=result.updated_posts,
                        renamed=result.renamed_files,
                        skipped_rename=result.skipped_rename,
                        skipped_no_md5=result.skipped_no_md5,
                        not_found=result.not_found,
                        errors=result.errors,
                        message=f"Fehler bei {path.name}: {exc}",
                    )
                )

        self.emit_progress(
            ExistingFileImportProgress(
                phase="done",
                current=len(files),
                total=len(files),
                imported=result.imported_posts,
                updated=result.updated_posts,
                renamed=result.renamed_files,
                skipped_rename=result.skipped_rename,
                skipped_no_md5=result.skipped_no_md5,
                not_found=result.not_found,
                errors=result.errors,
                message="Import abgeschlossen.",
            )
        )
        return result

    def rename_saved_files_for_category(self, category_id: int) -> ExistingFileImportResult:
        category = self.category_match_for_id(category_id)
        rows = self.db.fetch_saved_file_posts_for_category(category_id)
        result = ExistingFileImportResult(scanned_files=len(rows), category_name=category.name)

        self.emit_progress(
            ExistingFileImportProgress(
                phase="start",
                total=len(rows),
                message=f"Umbenennen gestartet: {len(rows)} gespeicherte Dateien, Kategorie {category.name}",
            )
        )

        for index, row in enumerate(rows, start=1):
            post_id = int(row["id"])
            source_path = Path(str(row["final_file_path"] or ""))
            try:
                rename_result = self.rename_saved_post_file(post_id, category=category)
                if rename_result.renamed:
                    result.renamed_files += 1
                    phase = "renamed"
                    message = f"Post {post_id} umbenannt: {rename_result.source_path.name} -> {rename_result.final_path.name}"
                else:
                    result.skipped_rename += 1
                    phase = "skip_rename"
                    message = f"Post {post_id}: Name bereits aktuell"

                self.emit_progress(
                    ExistingFileImportProgress(
                        phase=phase,
                        current=index,
                        total=len(rows),
                        path=str(rename_result.source_path),
                        target_path=str(rename_result.final_path),
                        post_id=post_id,
                        renamed=result.renamed_files,
                        skipped_rename=result.skipped_rename,
                        errors=result.errors,
                        message=message,
                    )
                )
            except Exception as exc:
                result.errors += 1
                self.emit_progress(
                    ExistingFileImportProgress(
                        phase="error",
                        current=index,
                        total=len(rows),
                        path=str(source_path),
                        post_id=post_id,
                        renamed=result.renamed_files,
                        skipped_rename=result.skipped_rename,
                        errors=result.errors,
                        message=f"Fehler beim Umbenennen von Post {post_id}: {exc}",
                    )
                )

        self.emit_progress(
            ExistingFileImportProgress(
                phase="done",
                current=len(rows),
                total=len(rows),
                renamed=result.renamed_files,
                skipped_rename=result.skipped_rename,
                errors=result.errors,
                message="Umbenennen abgeschlossen.",
            )
        )
        return result

    def category_match_for_id(self, category_id: int) -> CategoryMatch:
        row = self.db.execute(
            "SELECT id, name, folder_name, output_path FROM categories WHERE id = ?",
            (int(category_id),),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Kategorie nicht gefunden: ID {category_id}")
        return CategoryMatch(
            id=int(row["id"]),
            name=str(row["name"]),
            folder_name=str(row["folder_name"]),
            output_path=row["output_path"],
            matched=False,
            reason="Importer",
        )

    def rename_saved_post_file(self, post_id: int, *, category: CategoryMatch | None = None) -> RenameExistingFileResult:
        row = self.db.get_post_detail(post_id)
        if row is None:
            raise RuntimeError(f"Post {post_id} ist nicht in der Datenbank")
        if not row["final_file_path"]:
            raise RuntimeError(f"Post {post_id} hat keinen gespeicherten Dateipfad")

        source_path = Path(str(row["final_file_path"]))
        if not source_path.exists():
            raise RuntimeError(f"Datei fehlt: {source_path}")

        if category is None:
            assigned = self.db.get_assigned_category_for_post(post_id)
            if assigned is None:
                category = self.category_engine.suggest_category_for_post(post_id)
            else:
                category = CategoryMatch(
                    id=int(assigned["id"]),
                    name=str(assigned["name"]),
                    folder_name=str(assigned["folder_name"]),
                    output_path=assigned["output_path"],
                    matched=False,
                    reason="Zugewiesene Kategorie",
                )

        # Wichtig: Der Importer darf bestehende Dateien beim reinen Umbenennen nicht in
        # den Kategorie-Ausgabeordner verschieben. Er soll nur den Dateinamen im
        # bestehenden Ordner an das aktuelle Schema anpassen und den gespeicherten
        # Pfad in der DB aktualisieren. Alles andere wirkt für den Nutzer wie
        # „Datei aus Importordner gelöscht“, auch wenn sie nur woanders gelandet ist.
        new_filename = self.filename_builder.build_filename(post_id, source_path)
        desired_path = source_path.with_name(new_filename)

        try:
            if source_path.resolve() == desired_path.resolve():
                self.db.update_post_final_file_path(post_id, str(source_path))
                return RenameExistingFileResult(post_id, source_path, source_path, renamed=False)
        except OSError:
            pass

        target_path = unique_path(desired_path)
        source_path.rename(target_path)
        self.db.update_post_final_file_path(post_id, str(target_path))
        return RenameExistingFileResult(post_id, source_path, target_path, renamed=True)

    @staticmethod
    def find_import_files(root: Path, *, recursive: bool) -> list[Path]:
        iterator = root.rglob("*") if recursive else root.iterdir()
        files = [path for path in iterator if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS]
        return sorted(files, key=lambda item: str(item).lower())


@dataclass(frozen=True)
class RenameExistingFileResult:
    post_id: int
    source_path: Path
    final_path: Path
    renamed: bool


def extract_md5_from_filename(filename: str) -> str | None:
    match = MD5_RE.search(filename)
    if not match:
        return None
    return match.group(1).lower()


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 2
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1
