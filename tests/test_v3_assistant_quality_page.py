from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def _text(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_admin_quality_page_has_required_aggregate_sections():
    html = _text("index.html")
    assert 'id="assistant-quality-view"' in html
    assert 'data-view-target="assistant-quality-view"' in html
    for element_id in (
        "assistant-quality-summary",
        "assistant-quality-failures",
        "assistant-quality-retrieval",
        "assistant-quality-daily",
        "assistant-quality-frequent",
        "assistant-quality-low-confidence",
        "assistant-quality-negative",
        "assistant-quality-governance",
    ):
        assert f'id="{element_id}"' in html
    assert "不展示原始问题、SQL、结果行或反馈原因" in html


def test_quality_page_uses_admin_feature_and_aggregate_api():
    api = _text("api.js")
    app = _text("app.js")
    assert 'assistantQuality: (days = 30) => request(`/api/assistant/quality-operations?days=${encodeURIComponent(days)}`)' in api
    assert '"assistant-quality-view": "assistant_quality"' in app
    assert 'if (id === "assistant-quality-view") loadAssistantQuality();' in app
    assert 'hasFeature("assistant_quality")' in app


def test_quality_styles_cover_desktop_and_responsive_layouts():
    css = _text("style.css")
    assert ".quality-summary-grid" in css
    assert ".quality-main-grid" in css
    assert ".quality-daily-chart" in css
    assert "@media(max-width:650px)" in css
