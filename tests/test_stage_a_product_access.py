from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.business_domains import token_for
from app.core.config import STATIC_DIR, settings
from app.main import app


ROLE_USERS = {
    "admin": "admin",
    "academic_office": "jwc",
    "college_manager": "college",
    "teacher": "tea_li",
    "counselor": "counselor_chen",
    "student": "stu_zhang",
}

REMOVED_VIEWS = {"domain-settings-view", "role-management-view", "debug-view"}
TECHNICAL_VIEWS = {
    "data-access-view",
    "kb-list-view",
    "schema-console-view",
    "governance-queue-view",
    "governance-settings-view",
    "assistant-quality-view",
}


def _headers(username: str) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username)}


def test_auth_options_do_not_disclose_demo_accounts_by_default():
    with TestClient(app) as client:
        response = client.get("/api/auth/options")
    assert response.status_code == 200
    assert response.json() == {"demo_mode": False, "users": []}


def test_demo_accounts_require_explicit_demo_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    with TestClient(app) as client:
        data = client.get("/api/auth/options").json()
    assert data["demo_mode"] is True
    assert data["users"]
    assert all("username" in item and "password" not in item for item in data["users"])


@pytest.mark.parametrize(("role", "username"), ROLE_USERS.items())
def test_backend_navigation_is_role_scoped_and_contains_personal_center(role: str, username: str):
    with TestClient(app) as client:
        response = client.get("/api/auth/me", headers=_headers(username))
    assert response.status_code == 200
    user = response.json()["item"]
    views = {item["view"] for item in user["navigation"]}
    assert user["role"] == role
    assert "profile-view" in views
    assert not (views & REMOVED_VIEWS)
    if role != "admin":
        assert not (views & TECHNICAL_VIEWS)


def test_session_payload_exposes_product_scope_not_internal_policy():
    with TestClient(app) as client:
        user = client.get("/api/auth/session", headers=_headers("stu_zhang")).json()["user"]
    assert user["scope_label"] == "仅限本人学习数据"
    assert "navigation" in user
    assert "allowed_tables" not in user
    assert "row_scope" not in user
    assert "denied_columns" not in user
    assert "denied_terms" not in user


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/business-domains"),
        ("get", "/api/schema?source=teaching"),
        ("get", "/api/profile?source=teaching"),
        ("get", "/api/profile/versions?source=teaching"),
        ("get", "/api/quality?source=teaching"),
        ("get", "/api/examples?source=teaching"),
        ("get", "/api/data-access/sources"),
        ("get", "/api/governance/settings"),
        ("get", "/api/assistant/quality-operations"),
    ],
)
def test_students_cannot_call_platform_administration_apis(method: str, path: str):
    with TestClient(app) as client:
        response = getattr(client, method)(path, headers=_headers("stu_zhang"))
    assert response.status_code == 403


def test_retrieval_debug_api_is_removed():
    with TestClient(app) as client:
        response = client.post(
            "/api/debug/retrieval",
            headers=_headers("admin"),
            json={"question": "测试"},
        )
    assert response.status_code in {404, 405}
    assert not any(
        getattr(route, "path", None) == "/api/debug/retrieval"
        for route in app.routes
    )


def test_admin_policy_response_does_not_include_account_roster():
    with TestClient(app) as client:
        data = client.get("/api/business-domains", headers=_headers("admin")).json()
    assert "users" not in data
    assert "roles" in data


def test_removed_pages_are_absent_and_personal_center_exists():
    html = Path(STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "权限矩阵" not in html
    assert "账号角色列表" not in html
    assert "召回调试" not in html
    assert 'id="profile-view"' in html
    assert 'class="profile-status-card"' in html
    assert 'class="profile-password-actions"' in html
    assert 'aria-live="polite"' in html
    assert 'id="login-demo-accounts"' in html
