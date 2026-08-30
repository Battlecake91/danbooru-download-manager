from __future__ import annotations

import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.paths import app_base_dir


ARCHIVE_PATH_MODES = {"absolute", "relative"}
ARCHIVE_ROOT_KEY = "archive.root_path"
LOCAL_SETTINGS_FILENAME = "danbooru_manager_local_settings.db"


def archive_storage_mode(config: dict[str, Any]) -> str:
    archive_config = config.get("archive_paths", {}) or {}
    mode = str(archive_config.get("storage_mode", "absolute")).lower()
    return mode if mode in ARCHIVE_PATH_MODES else "absolute"


def local_settings_database_path(config: dict[str, Any]) -> Path:
    archive_config = config.get("archive_paths", {}) or {}
    configured = archive_config.get("local_settings_file")
    if configured:
        path = Path(str(configured)).expanduser()
        return path if path.is_absolute() else app_base_dir() / path
    return default_local_settings_database_path()


def default_local_settings_database_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / "DanbooruManager" / LOCAL_SETTINGS_FILENAME


class LocalSettingsStore:
    """Tiny per-machine SQLite store for values that must not follow the main DB."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS local_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        return connection

    def get(self, key: str, default: str | None = None) -> str | None:
        connection = self._connect()
        try:
            row = connection.execute("SELECT value FROM local_settings WHERE key = ?", (key,)).fetchone()
        finally:
            connection.close()
        if row is None:
            return default
        return str(row[0]) if row[0] is not None else default

    def set(self, key: str, value: str | None) -> None:
        encoded = None if value is None else json.dumps(str(value), ensure_ascii=False)
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO local_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, encoded),
            )
            connection.commit()
        finally:
            connection.close()


def _decode_local_value(raw_value: str | None) -> str | None:
    if raw_value in {None, ""}:
        return None
    try:
        decoded = json.loads(str(raw_value))
    except Exception:
        return str(raw_value)
    return str(decoded) if decoded not in {None, ""} else None


def archive_root_path(config: dict[str, Any]) -> Path | None:
    archive_config = config.get("archive_paths", {}) or {}
    runtime_root = archive_config.get("root_path")
    if runtime_root:
        return Path(str(runtime_root)).expanduser()

    raw_value = LocalSettingsStore(local_settings_database_path(config)).get(ARCHIVE_ROOT_KEY)
    decoded = _decode_local_value(raw_value)
    if not decoded:
        return None
    root = Path(decoded).expanduser()
    archive_config["root_path"] = str(root)
    config["archive_paths"] = archive_config
    return root


def set_archive_root_path(config: dict[str, Any], root_path: str | Path | None) -> None:
    value = str(Path(str(root_path)).expanduser()) if root_path not in {None, ""} else None
    LocalSettingsStore(local_settings_database_path(config)).set(ARCHIVE_ROOT_KEY, value)
    archive_config = config.setdefault("archive_paths", {})
    if value:
        archive_config["root_path"] = value
    else:
        archive_config.pop("root_path", None)


def resolve_archive_path(config: dict[str, Any], value: str | Path | None) -> Path | None:
    if value in {None, ""}:
        return None
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    root = archive_root_path(config)
    if root is None:
        return path
    return root / path


def archive_db_value_for_path(config: dict[str, Any], value: str | Path | None) -> str | None:
    if value in {None, ""}:
        return None

    path = Path(str(value)).expanduser()
    if archive_storage_mode(config) != "relative":
        return str(path)

    root = archive_root_path(config)
    if root is None:
        return str(path)

    try:
        return str(path.resolve(strict=False).relative_to(root.resolve(strict=False)))
    except ValueError:
        return str(path)


def migrate_archive_paths(
    db: Any,
    config: dict[str, Any],
    *,
    target_mode: str,
    archive_root: Path | None,
    verify_before: bool,
    verify_after: bool,
) -> ArchivePathMigrationReport:
    mode = target_mode.lower()
    if mode not in ARCHIVE_PATH_MODES:
        raise ValueError("target_mode must be absolute or relative")
    if mode == "relative" and archive_root is None:
        raise ValueError("Relative archive path migration needs an archive root")

    previous_mode = archive_storage_mode(config)
    previous_root = archive_root_path(config)
    archive_config = config.setdefault("archive_paths", {})

    if archive_root is not None:
        set_archive_root_path(config, archive_root)

    rows = db.execute(
        """
        SELECT id, final_file_path, final_directory, original_path
        FROM posts
        WHERE final_file_path IS NOT NULL
          AND final_file_path != ''
        ORDER BY id
        """
    ).fetchall()

    missing_before = 0
    missing_after = 0
    converted = 0
    skipped = 0
    errors: list[str] = []

    previous_config = {**config, "archive_paths": dict(archive_config)}
    previous_config["archive_paths"]["storage_mode"] = previous_mode
    if previous_root is not None:
        previous_config["archive_paths"]["root_path"] = str(previous_root)

    target_config = {**config, "archive_paths": dict(archive_config)}
    target_config["archive_paths"]["storage_mode"] = mode
    if archive_root is not None:
        target_config["archive_paths"]["root_path"] = str(archive_root)

    for row in rows:
        post_id = int(row["id"])
        try:
            current_final = resolve_archive_path(previous_config, row["final_file_path"])
            if current_final is None:
                skipped += 1
                continue

            if verify_before and not current_final.exists():
                missing_before += 1
                skipped += 1
                continue

            new_final = archive_db_value_for_path(target_config, current_final)
            new_directory = archive_db_value_for_path(target_config, current_final.parent)

            original_value = row["original_path"]
            new_original = original_value
            if original_value:
                current_original = resolve_archive_path(previous_config, original_value)
                if current_original == current_final:
                    new_original = new_final

            if verify_after:
                resolved_after = resolve_archive_path(target_config, new_final)
                if resolved_after is None or not resolved_after.exists():
                    missing_after += 1
                    skipped += 1
                    continue

            db.execute(
                """
                UPDATE posts
                SET final_file_path = ?,
                    final_directory = ?,
                    original_path = ?
                WHERE id = ?
                """,
                (new_final, new_directory, new_original, post_id),
            )
            converted += 1
        except Exception as exc:
            errors.append(f"{post_id}: {exc}")
            skipped += 1

    archive_config["storage_mode"] = mode
    db.set_app_setting("archive_paths.storage_mode", f'"{mode}"')
    db.commit()

    return ArchivePathMigrationReport(
        total=len(rows),
        converted=converted,
        missing_before=missing_before,
        missing_after=missing_after,
        skipped=skipped,
        errors=errors,
    )


@dataclass(frozen=True)
class ArchivePathMigrationReport:
    total: int
    converted: int
    missing_before: int
    missing_after: int
    skipped: int
    errors: list[str]

    def summary(self) -> str:
        lines = [
            f"Rows scanned: {self.total}",
            f"Rows converted: {self.converted}",
            f"Skipped: {self.skipped}",
            f"Missing before: {self.missing_before}",
            f"Missing after: {self.missing_after}",
        ]
        if self.errors:
            lines.append("Errors:")
            lines.extend(self.errors[:20])
            if len(self.errors) > 20:
                lines.append(f"... and {len(self.errors) - 20} more")
        return "\n".join(lines)
