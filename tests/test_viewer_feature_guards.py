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


def test_web_viewer_carries_desktop_shortcuts_and_final_save() -> None:
    web_source = read_source("app/web/static/app.js")
    api_source = read_source("app/web/app.py")

    assert 'event.key === "ArrowLeft"' in web_source
    assert 'event.key === "ArrowRight"' in web_source
    assert '/^[1-5]$/.test(event.key)' in web_source
    assert 'key === "h"' in web_source
    assert 'key === "n"' in web_source
    assert 'event.key === "Delete"' in web_source
    assert 'key === "o"' in web_source
    assert 'key === "f"' in web_source
    assert 'id="viewer-save"' in web_source
    assert '@app.post("/api/posts/{post_id}/save")' in api_source
    assert "FinalSaveService(request.app.state.config, db)" in api_source


def test_web_viewer_fit_constrains_both_image_dimensions() -> None:
    web_source = read_source("app/web/static/app.js")
    css_source = read_source("app/web/static/app.css")
    html_source = read_source("app/web/static/index.html")

    assert 'class="viewer-stage" id="viewer-stage"' in web_source
    assert '$("#viewer-stage").classList.toggle("native-size", nativeSize)' in web_source
    assert ".viewer-stage img { display: block; width: 100%; height: 100%;" in css_source
    assert ".viewer-stage.native-size { place-items: start; overflow: auto; }" in css_source
    assert 'href="/app.css?v=' in html_source
    assert 'src="/app.js?v=' in html_source


def test_web_viewer_checkboxes_do_not_block_shortcuts() -> None:
    web_source = read_source("app/web/static/app.js")

    assert '["button", "checkbox", "color", "radio", "range", "reset", "submit"]' in web_source
    assert web_source.count("event.target.blur();") >= 3


def test_web_viewer_persists_and_applies_status_auto_advance() -> None:
    web_source = read_source("app/web/static/app.js")
    api_source = read_source("app/web/app.py")

    assert 'id="viewer-next-after-status"' in web_source
    assert 'api("/api/viewer/settings"' in web_source
    assert "state.nextAfterStatusChange && nextId != null" in web_source
    assert 'historyNextId != null ? "forward" : "append"' in web_source
    assert '@app.put("/api/viewer/settings")' in api_source
    assert 'db.set_app_setting("web.viewer_next_after_status_change"' in api_source


def test_web_preview_exposes_desktop_sorting_and_persisted_sizes() -> None:
    html_source = read_source("app/web/static/index.html")
    web_source = read_source("app/web/static/app.js")
    api_source = read_source("app/web/app.py")

    assert 'value="recommendation_desc">Preselection: best first' in html_source
    assert 'value="recommendation_asc">Preselection: worst first' in html_source
    assert 'value="personal_desc"' in html_source
    assert 'value="resolution_desc"' in html_source
    assert 'id="preview-thumbnail-size"' in html_source
    assert 'id="preview-score-summary"' in html_source
    assert 'api("/api/preview/settings"' in web_source
    assert 'Preselection ${signedScore(preselection)}' in web_source
    assert '@app.put("/api/preview/settings")' in api_source
    assert 'db.set_app_setting("web.preview_thumbnail_size"' in api_source


def test_web_preview_supports_shift_selection_and_bulk_status_changes() -> None:
    html_source = read_source("app/web/static/index.html")
    web_source = read_source("app/web/static/app.js")
    api_source = read_source("app/web/app.py")

    assert 'id="preview-selection-toolbar"' in html_source
    assert 'data-preview-select="${post.id}"' in web_source
    assert "function selectPreviewPost" in web_source
    assert "event.shiftKey" in web_source
    assert 'api("/api/posts/status"' in web_source
    assert '@app.patch("/api/posts/status")' in api_source
    assert "db.set_post_statuses(post_ids, payload.status" in api_source


def test_web_fetch_page_shows_persisted_automatic_fetch_status() -> None:
    html_source = read_source("app/web/static/index.html")
    web_source = read_source("app/web/static/app.js")
    runtime_source = read_source("app/web/runtime.py")

    assert 'id="schedule-state"' in html_source
    assert "Last automatic start" in web_source
    assert "Last automatic finish" in web_source
    assert 'db.set_app_setting("web.fetch_last_finished_at"' in runtime_source
    assert 'db.set_app_setting("web.fetch_last_status"' in runtime_source


def test_web_viewer_keeps_recent_filtered_posts_for_correction() -> None:
    web_source = read_source("app/web/static/app.js")

    assert "viewerHistoryLimit: 12" in web_source
    assert "function recordViewerHistory" in web_source
    assert "function viewerStripItems" in web_source
    assert 'historyMode = "append"' in web_source
    assert 'historyPreviousId != null ? "back" : "append"' in web_source
    assert "if (tab === \"preview\") resetViewerHistory();" in web_source
