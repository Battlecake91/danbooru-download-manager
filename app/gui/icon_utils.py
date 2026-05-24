from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

from PySide6.QtGui import QIcon

from app.core.paths import resource_path, resolve_runtime_path


DANBOORU_ICON_URL = "https://upload.wikimedia.org/wikipedia/commons/b/b5/Danbooru_icon.png"


def ensure_app_icon(config: dict[str, Any]) -> QIcon:
    """Return the configured Danbooru app icon.

    Prefer a configured local file, then bundled assets, then a cached download.
    In frozen builds bundled assets live below PyInstaller's resource directory,
    while writable cache files live next to the executable. Naturally those are
    different places, because simplicity was apparently busy that day.
    """
    configured_icon = config.get("app_icon_file")
    if configured_icon:
        configured_path = resolve_runtime_path(str(configured_icon))
        if configured_path.exists():
            return QIcon(str(configured_path))

    for candidate in (
        resource_path("app/assets/danbooru_icon.png"),
        resource_path("assets/danbooru_icon.png"),
        resource_path("assets/app_icon.png"),
        resource_path("assets/app_icon.ico"),
    ):
        if candidate.exists():
            return QIcon(str(candidate))

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
