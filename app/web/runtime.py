from __future__ import annotations

import copy
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import load_config
from app.core.database import Database
from app.services.post_import_service import FetchProgress, PostImportService


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_web_config() -> dict[str, Any]:
    config = load_config()
    data_dir = Path(os.environ.get("DANBOORU_DATA_DIR", "./danbooru_manager_data")).resolve()
    database_file = Path(os.environ.get("DANBOORU_DATABASE_FILE", str(data_dir / "danbooru_manager.db"))).resolve()

    config.update(
        {
            "work_dir": str(data_dir),
            "database_file": str(database_file),
            "thumbnail_dir": str(data_dir / "thumbnails" / "active"),
            "active_thumbnail_dir": str(data_dir / "thumbnails" / "active"),
            "saved_thumbnail_dir": str(data_dir / "thumbnails" / "saved"),
            "rejected_thumbnail_dir": str(data_dir / "thumbnails" / "rejected"),
            "original_cache_dir": str(data_dir / "originals" / "cache"),
            "default_output_dir": os.environ.get("DANBOORU_OUTPUT_DIR", "./danbooru_saved"),
        }
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    database_file.parent.mkdir(parents=True, exist_ok=True)

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
            "thumbnail_dir": str(data_dir / "thumbnails" / "active"),
            "active_thumbnail_dir": str(data_dir / "thumbnails" / "active"),
            "saved_thumbnail_dir": str(data_dir / "thumbnails" / "saved"),
            "rejected_thumbnail_dir": str(data_dir / "thumbnails" / "rejected"),
            "original_cache_dir": str(data_dir / "originals" / "cache"),
            "default_output_dir": os.environ.get("DANBOORU_OUTPUT_DIR", "./danbooru_saved"),
        }
    )
    return config


def open_database(config: dict[str, Any]) -> Database:
    db = Database(Path(str(config["database_file"])))
    db.connect()
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
        result["saved_search_extra_tags"] = str(
            rating_clause or payload.get("saved_search_extra_tags") or ""
        ).strip()
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

    def start(self, overrides: dict[str, Any] | None = None, *, scheduled: bool = False) -> bool:
        with self._lock:
            if self._state.running:
                return False
            self._cancel_event.clear()
            self._state = FetchState(
                running=True,
                scheduled=scheduled,
                phase="starting",
                message="Scheduled fetch is starting" if scheduled else "Fetch is starting",
                started_at=utc_now_iso(),
            )
            run_config = copy.deepcopy(self.config)
            run_config.update(overrides or {})
            self._thread = threading.Thread(
                target=self._run,
                args=(run_config,),
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

    def _run(self, run_config: dict[str, Any]) -> None:
        db = open_database(run_config)
        try:
            service = PostImportService(
                run_config,
                db,
                progress_callback=self._on_progress,
                cancel_requested=self._cancel_event.is_set,
            )
            result = service.fetch_and_store()
            with self._lock:
                self._state.result = asdict(result)
                self._state.phase = "cancelled" if result.cancelled else "done"
                self._state.message = "Fetch cancelled" if result.cancelled else "Fetch completed"
        except Exception as exc:
            with self._lock:
                self._state.phase = "failed"
                self._state.message = "Fetch failed"
                self._state.error = f"{type(exc).__name__}: {exc}"
        finally:
            db.close()
            with self._lock:
                self._state.running = False
                self._state.cancelling = False
                self._state.finished_at = utc_now_iso()


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
            "batch_size": max(50, min(200, int(values.get("web.preview_batch_size", 75) or 75))),
            "last_started_at": values.get("web.fetch_last_started_at"),
        }

    def update(self, *, enabled: bool, interval_hours: float, batch_size: int | None = None) -> dict[str, Any]:
        db = open_database(self.config)
        try:
            db.set_app_setting("web.auto_fetch_enabled", str(bool(enabled)).lower())
            db.set_app_setting("web.fetch_interval_hours", str(max(0.25, float(interval_hours))))
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
            if self.controller.start(scheduled=True):
                db = open_database(self.config)
                try:
                    db.set_app_setting("web.fetch_last_started_at", utc_now_iso())
                finally:
                    db.close()
