from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_help_tab_contains_task_oriented_guides() -> None:
    source = read_source("app/gui/help_tab.py")

    assert "QScrollArea" in source
    assert "_create_quick_start_page" in source
    assert "_create_fetch_page" in source
    assert "_create_preview_page" in source
    assert "_create_tags_page" in source
    assert "_create_builds_page" in source
    assert "Fetch exclude" in source
    assert "Search supports exact tags and exclusions" in source
    assert "Database performance tests" in source


def test_advanced_controls_have_contextual_tooltips() -> None:
    config_source = read_source("app/gui/config_tab.py")
    fetch_source = read_source("app/gui/fetch_tab.py")
    preview_source = read_source("app/gui/preview_window.py")
    category_source = read_source("app/gui/category_tab.py")

    assert "self.database_file_edit.setToolTip" in config_source
    assert "self.filename_pattern_edit.setToolTip" in config_source
    assert "self.llm_tag_export_mode_combo.setToolTip" in config_source
    assert "self.llm_include_legend_checkbox.setToolTip" in config_source
    assert "self.preset_combo.setToolTip" in fetch_source
    assert "self.manual_query_edit.setToolTip" in fetch_source
    assert "box.setToolTip(\"Click cycle: ignore, include this rating, exclude this rating.\")" in fetch_source
    assert "self.search_edit.setToolTip" in preview_source
    assert "checkbox.setToolTip" in preview_source
    assert "self.show_advanced_check.setToolTip" in category_source
    assert "self.new_group_edit.setToolTip" in category_source
