from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_fetch_tab_exposes_fetch_exclude_management() -> None:
    source = read_source("app/gui/fetch_tab.py")
    service_source = read_source("app/services/post_import_service.py")

    assert "class FetchExcludeDialog" in source
    assert "self.fetch_exclude_group = QGroupBox" in source
    assert "self.fetch_exclude_enabled_checkbox = QCheckBox" in source
    assert "self.fetch_exclude_count_limits_checkbox = QCheckBox" in source
    assert "self.fetch_exclude_dialog_button = QPushButton()" in source
    assert "def open_fetch_exclude_dialog" in source
    assert "dialog = FetchExcludeDialog(self.config, self.db, self)" in source
    assert "def refresh_fetch_exclude_button" in source
    assert "self.list_widget = QListWidget()" in source
    assert "self.db.fetch_excluded_tag_set()" in source
    assert "def add_tags_from_input" in source
    assert "self.db.add_fetch_excluded_tag(tag, \"fetch-tab\")" in source
    assert "def remove_selected_tags" in source
    assert "self.db.remove_fetch_excluded_tag(tag)" in source
    assert '"fetch_exclude_enabled": self.fetch_exclude_enabled_checkbox.isChecked()' in source
    assert '"fetch_excluded_posts_count_toward_limits": self.fetch_exclude_count_limits_checkbox.isChecked()' in source
    assert "fetch_excluded_tags = self.db.fetch_excluded_tag_set() if bool(self.config.get(\"fetch_exclude_enabled\", True)) else set()" in service_source
    assert "fetch_excluded_posts_count_toward_limits = bool(self.config.get(\"fetch_excluded_posts_count_toward_limits\", True))" in service_source
    assert "if not fetch_excluded_posts_count_toward_limits:" in service_source
