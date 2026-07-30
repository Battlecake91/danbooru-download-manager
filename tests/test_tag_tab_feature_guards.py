from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_tag_tab_shows_rejected_percent_and_keeps_columns_named() -> None:
    source = read_source("app/gui/tag_tab.py")

    assert "COL_REJECTED_PERCENT = 6" in source
    assert "COL_ALIAS = 7" in source
    assert "COL_MANUAL_SCORE = 13" in source
    assert 'self.t("tags.table.rejected_percent", "Rejected %")' in source
    assert "calculate_rejected_percent(" in source
    assert '"" if rejected_percent is None else f"{rejected_percent:.1f}%"' in source
    assert "scoring_excluded=scoring_excluded" in source
    assert "column in {self.COL_ALIAS, self.COL_MANUAL_SCORE}" in source
    assert "COL_FETCH_EXCLUDE: \"fetch_excluded\"" in source
    assert "COL_CATEGORY_IGNORED: \"ignore_category_influence\"" in source
