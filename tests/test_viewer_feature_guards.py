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
    assert "(forceNext || state.nextAfterStatusChange) && nextId != null" in web_source
    assert 'historyNextId != null ? "forward" : "append"' in web_source
    assert '@app.put("/api/viewer/settings")' in api_source
    assert 'db.set_app_setting("web.viewer_next_after_status_change"' in api_source


def test_web_viewer_has_mobile_actions_and_swipe_navigation() -> None:
    web_source = read_source("app/web/static/app.js")
    css_source = read_source("app/web/static/app.css")

    assert 'data.final_file_path ? ""' in web_source
    assert 'class="viewer-mobile-actions"' in web_source
    assert 'data-mobile-status="rejected"' in web_source
    assert 'data-mobile-status="potential"' in web_source
    assert "setViewerStatus(button.dataset.mobileStatus, true)" in web_source
    assert "stage.onpointerdown" in web_source
    assert "Math.abs(deltaX) >= 55" in web_source
    assert '$("#viewer-next").click()' in web_source
    assert '$("#viewer-prev").click()' in web_source
    assert ".viewer-mobile-actions { display: none; }" in css_source
    assert "touch-action: pan-y" in css_source
    assert ".viewer-sidebar .viewer-statuses, .viewer-sidebar .viewer-auto-next { display: none; }" in css_source


def test_web_viewer_supports_wheel_and_pinch_zoom() -> None:
    web_source = read_source("app/web/static/app.js")
    css_source = read_source("app/web/static/app.css")

    assert "function installViewerImageGestures" in web_source
    assert 'stage.addEventListener("wheel"' in web_source
    assert "event.preventDefault()" in web_source
    assert "Math.exp(-event.deltaY * 0.0015)" in web_source
    assert "pointers.size >= 2" in web_source
    assert "pinchStart.scale * distance(values) / pinchStart.distance" in web_source
    assert "scale = clamp" in web_source
    assert "stage.ondblclick = reset" in web_source
    assert ".viewer-stage.zoomed { cursor: grab; touch-action: none; }" in css_source
    assert "will-change: transform" in css_source


def test_web_preview_exposes_desktop_sorting_and_persisted_sizes() -> None:
    html_source = read_source("app/web/static/index.html")
    web_source = read_source("app/web/static/app.js")
    api_source = read_source("app/web/app.py")

    assert 'value="recommendation_desc">Preselection: best first' in html_source
    assert 'value="recommendation_asc">Preselection: worst first' in html_source
    assert 'value="personal_desc"' in html_source
    assert 'value="resolution_desc"' in html_source
    assert 'id="preview-thumbnail-size"' in html_source
    assert 'id="preview-status-all"' in html_source
    assert html_source.count("data-preview-status") == 5
    assert 'id="preview-score-summary"' in html_source
    assert 'api("/api/preview/settings"' in web_source
    assert 'Preselection ${signedScore(preselection)}' in web_source
    assert '@app.put("/api/preview/settings")' in api_source
    assert 'db.set_app_setting("web.preview_thumbnail_size"' in api_source


def test_web_viewer_applies_authoritative_tag_context_updates() -> None:
    web_source = read_source("app/web/static/app.js")
    api_source = read_source("app/web/app.py")

    assert "function applyTagContextMetadata" in web_source
    assert "applyTagContextMetadata(meta.tag, updated)" in web_source
    assert 'api("/api/tags/settings"' in web_source
    assert '@app.patch("/api/tags/settings")' in api_source
    assert "fetch_tag_display_metadata([clean_tag])" in api_source


def test_web_viewer_renders_parent_and_child_posts_side_by_side() -> None:
    web_source = read_source("app/web/static/app.js")
    css_source = read_source("app/web/static/app.css")
    repository_source = read_source("app/web/repository.py")

    assert "function viewerFamilyStrip" in web_source
    assert 'data-related-post="${item.id}"' in web_source
    assert ".viewer-family-strip" in css_source
    assert 'post["related_posts"]' in repository_source


def test_web_preview_supports_shift_selection_and_bulk_status_changes() -> None:
    html_source = read_source("app/web/static/index.html")
    web_source = read_source("app/web/static/app.js")
    api_source = read_source("app/web/app.py")

    assert 'id="preview-selection-toolbar"' in html_source
    assert 'data-viewer="${post.id}"' in web_source
    assert "function selectPreviewPost" in web_source
    assert "event.shiftKey" in web_source
    assert 'document.addEventListener("dblclick"' in web_source
    assert 'api("/api/posts/status"' in web_source
    assert "Array.isArray(detail)" in web_source
    assert "JSON.stringify(detail)" in web_source
    assert '@app.patch("/api/posts/status")' in api_source


def test_web_preview_supports_desktop_action_hotkeys_and_bulk_saving() -> None:
    html_source = read_source("app/web/static/index.html")
    web_source = read_source("app/web/static/app.js")
    api_source = read_source("app/web/app.py")

    assert 'id="preview-bulk-save"' in html_source
    assert 'applyPreviewBulkStatus("potential")' in web_source
    assert 'applyPreviewBulkStatus("new")' in web_source
    assert 'applyPreviewBulkStatus("saved")' in web_source
    assert 'applyPreviewBulkStatus("already_known")' in web_source
    assert "function savePreviewSelection" in web_source
    assert "state.previewActionRunning" in web_source
    assert 'api("/api/posts/save"' in web_source
    assert '@app.post("/api/posts/save")' in api_source
    assert "except AlreadySavedError as exc:" in api_source


def test_web_preview_has_indexed_current_token_tag_completion() -> None:
    html_source = read_source("app/web/static/index.html")
    web_source = read_source("app/web/static/app.js")
    api_source = read_source("app/web/app.py")

    assert 'id="preview-tag-suggestions"' in html_source
    assert "function currentSearchTokenBounds" in web_source
    assert "function insertTagSuggestion" in web_source
    assert 'event.key === "ArrowDown"' in web_source
    assert 'event.key === "ArrowUp"' in web_source
    assert 'api(`/api/tags/suggestions?' in web_source
    assert '@app.get("/api/tags/suggestions")' in api_source
    assert "db.suggest_tags(query.strip(), limit=limit)" in api_source
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
