from __future__ import annotations

from pathlib import Path
from typing import Any


def ensure_runtime_dirs(config: dict[str, Any]) -> None:
    for key in ("work_dir", "thumbnail_dir", "original_cache_dir"):
        Path(config[key]).mkdir(parents=True, exist_ok=True)

    database_path = Path(config["database_file"])
    database_path.parent.mkdir(parents=True, exist_ok=True)
