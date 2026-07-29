from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def _text(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_v3_assistant_panel_is_loaded_before_app_and_replaces_visible_legacy_shell():
    html = _text("index.html")
    assert '<link rel="stylesheet" href="/assistant-panel.css?v=zjh-011"' in html
    assert '<div id="v3-assistant-panel" data-assistant-panel data-page="assistant"></div>' in html
    assert 'class="assistant-grid legacy-assistant-shell" hidden aria-hidden="true"' in html
    assert '/api.js?v=zjh-external-1' in html
    assert '/app.js?v=zjh-019' in html
    assert html.index('/api.js?v=zjh-external-1') < html.index('/assistant-panel.js?v=zjh-011')
    assert html.index('/assistant-panel.js?v=zjh-011') < html.index('/app.js?v=zjh-019')


def test_api_client_exposes_unified_assistant_and_action_draft_calls():
    script = _text("api.js")
    assert 'queryAssistant: (payload) => json("POST", "/api/assistant/query", payload, 50000)' in script
    assert "new AbortController()" in script
    assert "智能问数请求超时，请稍后重试。" in script
    assert 'assistantAction: (id) => request(`/api/assistant/action-drafts/${encodeURIComponent(id)}`)' in script
    assert 'confirmAssistantAction: (id) => json("POST", `/api/assistant/action-drafts/${encodeURIComponent(id)}/confirm`, {})' in script


def test_panel_covers_every_v3_3_1_state_and_initial_recommendations():
    script = _text("assistant-panel.js")
    for state in (
        "clarify",
        "success",
        "unsupported",
        "empty",
        "low-confidence",
        "degraded",
        "unauthorized",
        "error",
    ):
        assert state in script
    assert "DEFAULT_QUESTIONS" in script
    assert "appendLoading" in script
    assert "renderActions" in script
    assert "confirmAction" in script
    assert "prefill(question)" in script
    assert 'typeof this.api.queryAssistant !== "function"' in script
    assert "前端资源版本不一致，请刷新页面后重试。" in script
    assert "EMPTY_RESULT" in script
    assert "LOW_CONFIDENCE" in script
    assert "RETRIEVAL_DEGRADED" in script
    assert 'if (result.answer_type === "unsupported") return "unsupported";' in script
    assert 'unsupported: { label: "NOT SUPPORTED"' in script


def test_panel_does_not_read_or_infer_client_permissions_and_uses_safe_dom_text():
    script = _text("assistant-panel.js")
    assert "localStorage" not in script
    assert "currentUser" not in script
    assert "hasFeature" not in script
    assert "allowed_tables" not in script
    assert "denied_columns" not in script
    assert ".innerHTML" not in script
    assert "textContent" in script
    assert 'contextProvider: () => ({ page: autoRoot.dataset.page || "assistant" })' in script


def test_action_confirmation_uses_only_server_draft_id_and_handles_server_result():
    script = _text("assistant-panel.js")
    assert "this.api.confirmAssistantAction(action.draft_id)" in script
    assert 'result.kind === "navigation"' in script
    assert 'result.kind === "client_export"' in script
    assert 'result.kind === "business_draft"' in script
    assert 'new CustomEvent("nl2sql:assistant:navigate"' in script
    app_script = _text("app.js")
    assert 'window.addEventListener("nl2sql:assistant:navigate"' in app_script
    assert 'window.dispatchEvent(new CustomEvent("nl2sql:identity-changed"' in app_script
    assert "openUnifiedAssistant" in app_script


def test_role_pages_open_the_shared_panel_with_only_page_object_context():
    panel = _text("assistant-panel.js")
    app_script = _text("app.js")
    assert "setContext(context)" in panel
    assert "this.contextProvider = () => ({ ...next });" in panel
    assert "assistantContextFor(page)" in app_script
    assert "installRoleAssistantEntrances" in app_script
    for page in ("dashboard", "course_space", "assignment_workflow", "attendance", "course_analytics", "support_workbench", "teaching_operations"):
        assert f'"{page}"' in app_script
        assert f'data-role-assistant-entry="{page}"' in _text("index.html")
    assert _text("index.html").count('data-view-target="assistant-view"') >= 6
    assert 'panel.setContext(context || { page: "assistant" });' in app_script
    assert 'data-assistant-question="本周有哪些待复查事项？"' in _text("index.html")
    assert 'parameters.support_case_id' in app_script
    assert 'parameters.teaching_issue_id' in app_script
    assert 'filters?.issue_status' in app_script


def test_external_knowledge_base_entries_pass_selected_source_to_shared_panel():
    app_script = _text("app.js")
    assert 'function sourceAssistantContext(source)' in app_script
    assert 'if (source) context.source = source;' in app_script
    assert 'openUnifiedAssistant("", sourceAssistantContext(row.name || ""));' in app_script
    assert 'sourceAssistantContext(item.source || "")' in app_script


def test_panel_styles_are_scoped_responsive_and_keep_legacy_shell_hidden():
    css = _text("assistant-panel.css")
    assert css.lstrip().startswith(".v3-assistant-panel{")
    assert ".legacy-assistant-shell[hidden]{display:none!important}" in css
    assert "@media(max-width:760px)" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert ".v3ap-action.is-confirmed" in css
    assert ".v3ap-answer.is-unauthorized" in css
    assert ".v3ap-answer.is-unsupported" in css
