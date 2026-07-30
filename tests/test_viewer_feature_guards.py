from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_viewer_has_configurable_list_preview_strip() -> None:
    source = read_source("app/gui/image_viewer.py")
    config_source = read_source("app/core/config.py")
    config_tab_source = read_source("app/gui/config_tab.py")

    assert "class RelatedPreviewTile" in source
    assert "self.related_strip_area = QScrollArea()" in source
    assert "def update_related_preview_strip" in source
    assert "def open_related_preview_post" in source
    assert "preview_strip_previous_count" in source
    assert "preview_strip_next_count" in source
    assert "preview_strip_thumbnail_size" in source
    assert "def preview_strip_thumbnail_size" in source
    assert "def preview_strip_area_height" in source
    assert "self.post_ids[index]" in source
    assert "balanced_side_count = max(previous_count, next_count)" in source
    assert "make_preview_strip_placeholder_tile(thumbnail_size)" in source
    assert "def center_preview_strip_on_tile" in source
    assert "QTimer.singleShot(0, lambda tile=active_tile: self.center_preview_strip_on_tile(tile))" in source
    assert "self.update_related_preview_strip(post_id, current_row, related)" in source
    assert '"preview_strip_previous_count": 3' in config_source
    assert '"preview_strip_next_count": 3' in config_source
    assert '"preview_strip_thumbnail_size": 96' in config_source
    assert "self.viewer_strip_previous_spin = QSpinBox()" in config_tab_source
    assert "self.viewer_strip_next_spin = QSpinBox()" in config_tab_source
    assert "self.viewer_strip_thumbnail_size_spin = QSpinBox()" in config_tab_source
    assert '"viewer.preview_strip_previous_count": int(self.viewer_strip_previous_spin.value())' in config_tab_source
    assert '"viewer.preview_strip_next_count": int(self.viewer_strip_next_spin.value())' in config_tab_source
    assert '"viewer.preview_strip_thumbnail_size": int(self.viewer_strip_thumbnail_size_spin.value())' in config_tab_source
