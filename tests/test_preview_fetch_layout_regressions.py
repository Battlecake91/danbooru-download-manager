from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_fetch_result_label_does_not_force_window_width() -> None:
    source = read_source("app/gui/fetch_tab.py")

    assert "self.fetch_progress_label.setWordWrap(True)" in source
    assert "self.fetch_progress_label.setMinimumWidth(0)" in source
    assert "self.fetch_progress_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)" in source


def test_preview_grid_ignores_stale_wide_size_hints() -> None:
    grid_source = read_source("app/gui/thumbnail_grid.py")
    preview_source = read_source("app/gui/preview_window.py")

    assert "self.setSizeAdjustPolicy(QScrollArea.AdjustIgnored)" in grid_source
    assert "self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)" in grid_source
    assert "self.container.setMinimumWidth(0)" in grid_source
    assert "def sync_container_geometry" in grid_source
    assert "self.container.adjustSize()" not in grid_source
    assert "self.grid.container.adjustSize()" not in preview_source
