from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


RUNTIME_PATH_KEYS = (
    "work_dir",
    "database_file",
    "thumbnail_dir",
    "active_thumbnail_dir",
    "saved_thumbnail_dir",
    "rejected_thumbnail_dir",
    "original_cache_dir",
    "default_output_dir",
    "history_file",
)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_base_dir() -> Path:
    """Return the directory that owns runtime data.

    In source runs this is the current working directory. In PyInstaller builds it
    is the folder next to the executable, not ``_internal`` and not ``%TEMP%``.
    Windows already invents enough haunted places for files to go.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def resource_base_dir() -> Path:
    """Return the directory where bundled read-only resources are located."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)).resolve()
    return Path(__file__).resolve().parents[2]


def resource_path(relative_path: str | Path) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        return path
    return resource_base_dir() / path


def resolve_runtime_path(path_value: str | Path, *, base: Path | None = None) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (base or app_base_dir()) / path


def normalize_runtime_paths(config: dict[str, Any]) -> None:
    base = app_base_dir()
    for key in RUNTIME_PATH_KEYS:
        value = config.get(key)
        if value in {None, ""}:
            continue
        config[key] = str(resolve_runtime_path(str(value), base=base))


def ensure_runtime_dirs(config: dict[str, Any]) -> None:
    normalize_runtime_paths(config)

    for key in (
        "work_dir",
        "thumbnail_dir",
        "active_thumbnail_dir",
        "saved_thumbnail_dir",
        "rejected_thumbnail_dir",
        "original_cache_dir",
        "default_output_dir",
    ):
        Path(config[key]).mkdir(parents=True, exist_ok=True)

    database_path = Path(config["database_file"])
    database_path.parent.mkdir(parents=True, exist_ok=True)

    history_file = config.get("history_file")
    if history_file:
        Path(str(history_file)).parent.mkdir(parents=True, exist_ok=True)
