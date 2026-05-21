from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

from PySide6.QtGui import QIcon


DANBOORU_ICON_URL = "https://upload.wikimedia.org/wikipedia/commons/b/b5/Danbooru_icon.png"


def ensure_app_icon(config: dict[str, Any]) -> QIcon:
    """Return the configured Danbooru app icon.

    Prefer a configured local file, then a bundled asset, then a cached download from
    the Wikimedia Danbooru icon URL. If the machine is offline, Qt simply gets an
    empty icon instead of exploding theatrically.
    """
    configured_icon = config.get("app_icon_file")
    if configured_icon:
        path = Path(str(configured_icon))
        if path.exists():
            return QIcon(str(path))

    bundled_icon = Path(__file__).resolve().parents[1] / "assets" / "danbooru_icon.png"
    if bundled_icon.exists():
        return QIcon(str(bundled_icon))

    work_dir = Path(str(config.get("work_dir", ".")))
    icon_dir = work_dir / "assets"
    icon_path = icon_dir / "danbooru_icon.png"

    if not icon_path.exists():
        try:
            icon_dir.mkdir(parents=True, exist_ok=True)
            urlretrieve(DANBOORU_ICON_URL, icon_path)
        except Exception:
            return QIcon()

    return QIcon(str(icon_path))
