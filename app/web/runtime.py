from __future__ import annotations

import copy
import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from app.core.archive_paths import active_output_directory
from app.core.config import load_config
from app.core.database import Database
from app.services.existing_file_import_service import ExistingFileImportProgress, ExistingFileImportService
from app.services.post_import_service import FetchProgress, PostImportService


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_web_config() -> dict[str, Any]:
    config = load_config()
    data_dir = Path(os.environ.get("DANBOORU_DATA_DIR", "./danbooru_manager_data")).resolve()
    cache_dir = Path(os.environ.get("DANBOORU_CACHE_ROOT", str(data_dir))).resolve()
    database_file = Path(os.environ.get("DANBOORU_DATABASE_FILE", str(data_dir / "danbooru_manager.db"))).resolve()
    yearly_output_root = os.environ.get("DANBOORU_ARCHIVE_ROOT", "").strip()
    import_root = os.environ.get("DANBOORU_IMPORT_ROOT", "").strip()
    default_output_dir = os.environ.get("DANBOORU_OUTPUT_DIR", "./danbooru_saved")
    if yearly_output_root:
        config["yearly_output_root"] = yearly_output_root
        default_output_dir = str(active_output_directory(config))
    if import_root:
        config["import_root"] = str(Path(import_root).resolve())

    config.update(
        {
            "work_dir": str(data_dir),
            "database_file": str(database_file),
            "thumbnail_dir": str(cache_dir / "thumbnails" / "active"),
            "active_thumbnail_dir": str(cache_dir / "thumbnails" / "active"),
            "saved_thumbnail_dir": str(cache_dir / "thumbnails" / "saved"),
            "rejected_thumbnail_dir": str(cache_dir / "thumbnails" / "rejected"),
            "original_cache_dir": str(cache_dir / "originals" / "cache"),
            "default_output_dir": default_output_dir,
        }
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    database_file.parent.mkdir(parents=True, exist_ok=True)
    Path(default_output_dir).mkdir(parents=True, exist_ok=True)

    db = Database(database_file)
    db.connect()
    try:
        db.initialize_schema()
        db.apply_app_settings_to_config(config)
    finally:
        db.close()

    # Container paths are runtime infrastructure and must not be replaced by
    # absolute paths persisted by a desktop installation on another OS.
    config.update(
        {
            "work_dir": str(data_dir),
            "database_file": str(database_file),
            "thumbnail_dir": str(cache_dir / "thumbnails" / "active"),
            "active_thumbnail_dir": str(cache_dir / "thumbnails" / "active"),
            "saved_thumbnail_dir": str(cache_dir / "thumbnails" / "saved"),
            "rejected_thumbnail_dir": str(cache_dir / "thumbnails" / "rejected"),
            "original_cache_dir": str(cache_dir / "originals" / "cache"),
            "default_output_dir": default_output_dir,
        }
    )
    if yearly_output_root:
        config["yearly_output_root"] = yearly_output_root

    for path_key in (
        "active_thumbnail_dir",
        "saved_thumbnail_dir",
        "rejected_thumbnail_dir",
        "original_cache_dir",
    ):
        Path(str(config[path_key])).mkdir(parents=True, exist_ok=True)

    db = Database(database_file)
    db.connect()
    try:
        _rebase_existing_cache_paths(db, config)
    finally:
        db.close()
    return config


@dataclass
class ImportState:
    running: bool = False
    phase: str = "idle"
    message: str = ""
    progress: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None


class ImportController:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._state = ImportState()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(asdict(self._state))

    def source_folder(self, relative_path: str) -> Path:
        root_value = self.config.get("import_root")
        if not root_value:
            raise ValueError("Server import directory is not configured")
        root = Path(str(root_value)).resolve()
        requested = Path(str(relative_path or ".").strip() or ".")
        if requested.is_absolute():
            raise ValueError("Use a path relative to the mounted import directory")
        folder = (root / requested).resolve()
        try:
            folder.relative_to(root)
        except ValueError as exc:
            raise ValueError("Import path must stay inside the mounted import directory") from exc
        if not folder.is_dir():
            raise ValueError("Import directory does not exist")
        return folder

    def start_scan(self, relative_path: str, recursive: bool) -> bool:
        folder = self.source_folder(relative_path)
        with self._lock:
            if self._state.running:
                return False
            self._state = ImportState(running=True, phase="scan", message="Scanning import directory")
            self._thread = threading.Thread(
                target=self._scan,
                args=(folder, recursive),
                name="web-import-scan",
                daemon=True,
            )
            self._thread.start()
            return True

    def start_import(self, category_id: int, candidate_paths: list[str], fetch_thumbnails: bool) -> bool:
        with self._lock:
            if self._state.running:
                return False
            allowed = {
                str(item.get("path")): item
                for item in self._state.candidates
                if item.get("importable") and item.get("path")
            }
            selected = [path for path in dict.fromkeys(candidate_paths) if path in allowed]
            if not selected:
                raise ValueError("Select at least one importable candidate")
            root = Path(str(self.config.get("import_root"))).resolve()
            for value in selected:
                Path(value).resolve().relative_to(root)
            self._state.running = True
            self._state.phase = "import"
            self._state.message = "Copying selected files into the Manager archive"
            self._state.result = None
            self._state.error = None
            self._thread = threading.Thread(
                target=self._import,
                args=(category_id, selected, fetch_thumbnails),
                name="web-import-copy",
                daemon=True,
            )
            self._thread.start()
            return True

    def _progress(self, progress: ExistingFileImportProgress) -> None:
        with self._lock:
            self._state.progress = asdict(progress)
            self._state.message = progress.message

    def _scan(self, folder: Path, recursive: bool) -> None:
        db = open_database(self.config)
        try:
            result = ExistingFileImportService(self.config, db, progress_callback=self._progress).scan_folder(
                folder, recursive=recursive
            )
            with self._lock:
                self._state.candidates = [asdict(item) for item in result.candidates]
                self._state.result = {"scanned_files": len(result.candidates)}
                self._state.phase = "review"
                self._state.message = f"Scan complete: {len(result.candidates)} files"
        except Exception as exc:
            with self._lock:
                self._state.phase = "failed"
                self._state.error = f"{type(exc).__name__}: {exc}"
                self._state.message = "Import scan failed"
        finally:
            db.close()
            with self._lock:
                self._state.running = False

    def _import(self, category_id: int, selected: list[str], fetch_thumbnails: bool) -> None:
        db = open_database(self.config)
        try:
            root = Path(str(self.config["import_root"]))
            result = ExistingFileImportService(self.config, db, progress_callback=self._progress).import_folder(
                root,
                category_id,
                recursive=True,
                update_existing=True,
                fetch_thumbnails=fetch_thumbnails,
                copy_to_archive=True,
                candidate_paths=selected,
            )
            with self._lock:
                self._state.result = asdict(result)
                self._state.phase = "done"
                self._state.message = "Import complete"
        except Exception as exc:
            with self._lock:
                self._state.phase = "failed"
                self._state.error = f"{type(exc).__name__}: {exc}"
                self._state.message = "Import failed"
        finally:
            db.close()
            with self._lock:
                self._state.running = False


def _rebase_existing_cache_paths(db: Database, config: dict[str, Any]) -> None:
    roots = {
        "active": Path(str(config["active_thumbnail_dir"])),
        "saved": Path(str(config["saved_thumbnail_dir"])),
        "rejected": Path(str(config["rejected_thumbnail_dir"])),
    }
    original_root = Path(str(config["original_cache_dir"]))
    rows = db.execute(
        """
        SELECT id, status, thumbnail_path, rejected_thumbnail_path, original_cache_path
        FROM posts
        WHERE thumbnail_path IS NOT NULL
           OR rejected_thumbnail_path IS NOT NULL
           OR original_cache_path IS NOT NULL
        """
    ).fetchall()
    updates: list[tuple[str | None, str | None, str | None, int]] = []

    for row in rows:
        thumbnail_value = _rebased_cache_file(row["thumbnail_path"], roots, str(row["status"] or ""))
        rejected_value = _rebased_cache_file(row["rejected_thumbnail_path"], roots, "rejected")
        original_value = _rebased_cache_file(row["original_cache_path"], {"original": original_root}, "original")
        current = (
            str(row["thumbnail_path"]) if row["thumbnail_path"] else None,
            str(row["rejected_thumbnail_path"]) if row["rejected_thumbnail_path"] else None,
            str(row["original_cache_path"]) if row["original_cache_path"] else None,
        )
        rebased = (thumbnail_value, rejected_value, original_value)
        if rebased != current:
            updates.append((*rebased, int(row["id"])))

    if updates:
        db.executemany(
            """
            UPDATE posts
            SET thumbnail_path = ?, rejected_thumbnail_path = ?, original_cache_path = ?
            WHERE id = ?
            """,
            updates,
        )
        db.commit()


def _rebased_cache_file(value: Any, roots: dict[str, Path], preferred: str) -> str | None:
    if not value:
        return None
    current = Path(str(value)).expanduser()

    ordered_roots = [roots[preferred]] if preferred in roots else []
    ordered_roots.extend(root for key, root in roots.items() if key != preferred)
    for root in ordered_roots:
        try:
            if current.is_file() and current.resolve().is_relative_to(root.resolve()):
                return str(current)
        except OSError:
            continue
    raw_value = str(value)
    portable_names = {
        current.name,
        PureWindowsPath(raw_value).name,
        PurePosixPath(raw_value).name,
    }
    for root in ordered_roots:
        for name in portable_names:
            if not name:
                continue
            candidate = root / name
            if candidate.is_file():
                return str(candidate)
    if current.is_file():
        return str(current)
    return str(current)


def open_database(config: dict[str, Any]) -> Database:
    db = Database(Path(str(config["database_file"])))
    # FastAPI may create, use and finalize a sync dependency on different
    # worker threads. Each request still owns its connection exclusively.
    db.connect(check_same_thread=False)
    return db


def _csv_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    normalized = str(value or "").replace(";", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def _rating_clause(states: Any) -> str:
    if not isinstance(states, dict):
        return ""
    includes = [str(code) for code, state in states.items() if str(state) == "include"]
    excludes = [str(code) for code, state in states.items() if str(state) == "exclude"]
    parts: list[str] = []
    if len(includes) == 1:
        parts.append(f"rating:{includes[0]}")
    elif includes:
        parts.append("( " + " or ".join(f"rating:{code}" for code in includes) + " )")
    parts.extend(f"-rating:{code}" for code in excludes)
    return " ".join(parts)


def fetch_overrides_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate a shared desktop/web fetch preset into service config values."""
    result: dict[str, Any] = {}
    for key in (
        "max_posts_per_query",
        "min_unknown_posts_per_query",
        "max_consecutive_known_posts",
        "max_total_posts",
    ):
        if payload.get(key) not in {None, ""}:
            minimum = 0 if key in {"min_unknown_posts_per_query", "max_consecutive_known_posts"} else 1
            result[key] = max(minimum, int(payload[key]))
    for key in ("fetch_exclude_enabled", "fetch_excluded_posts_count_toward_limits"):
        if key in payload:
            result[key] = bool(payload[key])
    if isinstance(payload.get("resolution_filters"), dict):
        result["resolution_filters"] = dict(payload["resolution_filters"])

    rating_clause = _rating_clause(payload.get("rating_states"))
    source_mode = str(payload.get("source_mode") or "tags")
    if source_mode == "saved_searches":
        result["use_saved_searches"] = True
        result["search_tags"] = ""
        result["saved_search_labels"] = _csv_values(payload.get("saved_search_labels"))
        result["saved_search_queries"] = _csv_values(payload.get("saved_search_queries"))
        result["saved_search_extra_tags"] = " ".join(
            part
            for part in (str(payload.get("saved_search_extra_tags") or "").strip(), rating_clause)
            if part
        )
    else:
        query = str(payload.get("manual_query") or payload.get("search_tags") or "order:id_desc").strip()
        result["use_saved_searches"] = False
        result["search_tags"] = " ".join(part for part in (query, rating_clause) if part).strip()
        result["saved_search_labels"] = []
        result["saved_search_queries"] = []
        result["saved_search_extra_tags"] = ""
    return result


@dataclass
class FetchState:
    running: bool = False
    cancelling: bool = False
    scheduled: bool = False
    phase: str = "idle"
    message: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    progress: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None


class FetchController:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._state = FetchState()
        self._lock = threading.RLock()
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(asdict(self._state))

    def start(
        self,
        overrides: dict[str, Any] | None = None,
        *,
        scheduled: bool = False,
        preset_name: str | None = None,
    ) -> bool:
        with self._lock:
            if self._state.running:
                return False
            self._cancel_event.clear()
            started_at = utc_now_iso()
            self._state = FetchState(
                running=True,
                scheduled=scheduled,
                phase="starting",
                message="Scheduled fetch is starting" if scheduled else "Fetch is starting",
                started_at=started_at,
            )
            run_config = copy.deepcopy(self.config)
            run_config.update(overrides or {})
            if scheduled:
                db = open_database(run_config)
                try:
                    db.set_app_setting("web.fetch_last_started_at", started_at)
                    db.set_app_setting("web.fetch_last_status", "running")
                finally:
                    db.close()
            self._thread = threading.Thread(
                target=self._run,
                args=(run_config, scheduled, preset_name),
                name="web-fetch",
                daemon=True,
            )
            self._thread.start()
            return True

    def cancel(self) -> bool:
        with self._lock:
            if not self._state.running:
                return False
            self._state.cancelling = True
            self._state.message = "Cancelling after the current operation"
            self._cancel_event.set()
            return True

    def _on_progress(self, progress: FetchProgress) -> None:
        payload = asdict(progress)
        with self._lock:
            self._state.phase = str(payload.get("phase") or "running")
            self._state.message = str(payload.get("message") or "")
            self._state.progress = payload

    def _run(
        self,
        run_config: dict[str, Any],
        scheduled: bool = False,
        preset_name: str | None = None,
    ) -> None:
        db = open_database(run_config)
        outcome = "failed"
        result_payload: dict[str, Any] | None = None
        try:
            service = PostImportService(
                run_config,
                db,
                progress_callback=self._on_progress,
                cancel_requested=self._cancel_event.is_set,
            )
            result = service.fetch_and_store()
            result_payload = asdict(result)
            with self._lock:
                self._state.result = result_payload
                self._state.phase = "cancelled" if result.cancelled else "done"
                self._state.message = "Fetch cancelled" if result.cancelled else "Fetch completed"
                outcome = "cancelled" if result.cancelled else "completed"
        except Exception as exc:
            with self._lock:
                self._state.phase = "failed"
                self._state.message = "Fetch failed"
                self._state.error = f"{type(exc).__name__}: {exc}"
        finally:
            finished_at = utc_now_iso()
            try:
                if scheduled:
                    db.set_app_setting("web.fetch_last_finished_at", finished_at)
                    db.set_app_setting("web.fetch_last_status", outcome)
                self._store_history(
                    db,
                    {
                        "started_at": self._state.started_at,
                        "finished_at": finished_at,
                        "scheduled": scheduled,
                        "preset_name": preset_name,
                        "status": outcome,
                        "error": self._state.error,
                        "result": result_payload,
                    },
                )
            finally:
                db.close()
            with self._lock:
                self._state.running = False
                self._state.cancelling = False
                self._state.finished_at = finished_at

    @staticmethod
    def _store_history(db: Database, entry: dict[str, Any]) -> None:
        values = db.app_settings_as_values()
        history = values.get("web.fetch_history", [])
        if not isinstance(history, list):
            history = []
        db.set_app_setting(
            "web.fetch_history",
            json.dumps([entry, *history][:30], ensure_ascii=False),
        )


class FetchScheduler:
    def __init__(self, config: dict[str, Any], controller: FetchController) -> None:
        self.config = config
        self.controller = controller
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="web-fetch-scheduler", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5)

    def settings(self) -> dict[str, Any]:
        db = open_database(self.config)
        try:
            values = db.app_settings_as_values()
        finally:
            db.close()
        return {
            "enabled": bool(values.get("web.auto_fetch_enabled", False)),
            "interval_hours": max(0.25, float(values.get("web.fetch_interval_hours", 6) or 6)),
            "preset_name": str(values.get("web.fetch_preset_name") or ""),
            "batch_size": max(50, min(200, int(values.get("web.preview_batch_size", 75) or 75))),
            "last_started_at": values.get("web.fetch_last_started_at"),
            "last_finished_at": values.get("web.fetch_last_finished_at"),
            "last_status": values.get("web.fetch_last_status"),
        }

    def update(
        self,
        *,
        enabled: bool,
        interval_hours: float,
        preset_name: str | None = None,
        batch_size: int | None = None,
    ) -> dict[str, Any]:
        db = open_database(self.config)
        try:
            clean_preset_name = str(preset_name or "").strip()
            if enabled and (not clean_preset_name or db.get_fetch_preset(clean_preset_name) is None):
                raise ValueError("Select an existing fetch preset before enabling automatic fetch")
            db.set_app_setting("web.auto_fetch_enabled", str(bool(enabled)).lower())
            db.set_app_setting("web.fetch_interval_hours", str(max(0.25, float(interval_hours))))
            db.set_app_setting("web.fetch_preset_name", clean_preset_name)
            if batch_size is not None:
                db.set_app_setting("web.preview_batch_size", str(max(50, min(200, int(batch_size)))))
        finally:
            db.close()
        return self.settings()

    def _loop(self) -> None:
        while not self._stop_event.wait(15):
            settings = self.settings()
            if not settings["enabled"] or self.controller.snapshot()["running"]:
                continue
            last_started = settings.get("last_started_at")
            try:
                last_timestamp = datetime.fromisoformat(str(last_started)).timestamp() if last_started else 0.0
            except ValueError:
                last_timestamp = 0.0
            if time.time() - last_timestamp < float(settings["interval_hours"]) * 3600:
                continue
            self._start_scheduled_fetch(str(settings.get("preset_name") or "").strip())

    def _start_scheduled_fetch(self, preset_name: str) -> bool:
        db = open_database(self.config)
        try:
            preset = db.get_fetch_preset(preset_name) if preset_name else None
            if preset is None:
                now = utc_now_iso()
                db.set_app_setting("web.fetch_last_started_at", now)
                db.set_app_setting("web.fetch_last_finished_at", now)
                db.set_app_setting("web.fetch_last_status", "preset missing")
                return False
        finally:
            db.close()
        return self.controller.start(
            fetch_overrides_from_payload(preset),
            scheduled=True,
            preset_name=preset_name,
        )
