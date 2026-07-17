from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.core.authorization import connect
from app.core.business_domains import token_for
from app.core.config import STATIC_DIR
from app.main import app


ROLE_USERS = {
    "student": "stu_zhang",
    "teacher": "tea_li",
    "counselor": "counselor_chen",
    "college_manager": "college",
    "academic_office": "jwc",
    "admin": "admin",
}

REQUIRED_VIEWS = {
    "student": {"dashboard-view", "assignment-workflow-view", "course-space-view", "attendance-view", "course-questions-view", "notifications-view", "support-workbench-view", "profile-view"},
    "teacher": {"dashboard-view", "assignment-workflow-view", "course-space-view", "attendance-view", "course-questions-view", "teaching-operations-view", "notifications-view", "profile-view"},
    "counselor": {"dashboard-view", "support-workbench-view", "identity-approval-view", "profile-view"},
    "college_manager": {"dashboard-view", "teaching-operations-view", "identity-approval-view", "organization-view", "notifications-view", "profile-view"},
    "academic_office": {"dashboard-view", "teaching-operations-view", "identity-approval-view", "organization-view", "notifications-view", "profile-view"},
    "admin": {"dashboard-view", "data-access-view", "kb-list-view", "schema-console-view", "governance-queue-view", "organization-view", "profile-view"},
}


def _headers(username: str) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username)}


@pytest.mark.parametrize(("role", "username"), ROLE_USERS.items())
def test_six_role_navigation_and_session_fields_are_product_scoped(role: str, username: str):
    with TestClient(app) as client:
        response = client.get("/api/auth/session", headers=_headers(username))
    assert response.status_code == 200
    user = response.json()["user"]
    assert user["role"] == role
    assert REQUIRED_VIEWS[role] <= {item["view"] for item in user["navigation"]}
    assert not {"allowed_tables", "row_scope", "denied_columns", "denied_terms"} & set(user)


@pytest.mark.parametrize(
    ("username", "allowed_path", "denied_path"),
    [
        ("stu_zhang", "/api/workbench", "/api/business-domains"),
        ("tea_li", "/api/teaching/operations/tasks", "/api/organization/units"),
        ("counselor_chen", "/api/teaching/support/cases", "/api/teaching/operations/tasks"),
        ("college", "/api/teaching/operations/summary", "/api/teaching/analytics/contexts"),
        ("jwc", "/api/teaching/operations/tasks", "/api/teaching/classes"),
        ("admin", "/api/business-domains", "/api/teaching/operations/tasks"),
    ],
)
def test_six_role_key_api_allow_and_deny_matrix(username: str, allowed_path: str, denied_path: str):
    with TestClient(app) as client:
        assert client.get(allowed_path, headers=_headers(username)).status_code == 200
        assert client.get(denied_path, headers=_headers(username)).status_code == 403


def test_product_regression_uses_a_private_temporary_database():
    shared = Path(__file__).parents[1] / "data" / "teaching.db"
    assert Path(teaching_migrations.DB_PATH).resolve() != shared.resolve()
    assert "teaching-runtime" in str(teaching_migrations.DB_PATH)


def test_notification_resources_expose_safe_business_page_targets():
    ids: list[int] = []
    try:
        with connect() as conn:
            for index, resource_type in enumerate(("course_announcement", "assignment", "course_question", "support_case", "grade_submission"), start=1):
                cursor = conn.execute(
                    "INSERT INTO notification(recipient_username,type,title,body,resource_type,resource_id,created_at) VALUES ('stu_zhang','stage_f',?,?,?,?,'2026-07-17T12:00:00+00:00')",
                    (f"阶段F通知{index}", "用于验证安全跳转", resource_type, 980000 + index),
                )
                ids.append(int(cursor.lastrowid))
            conn.commit()
        with TestClient(app) as client:
            items = client.get("/api/notifications", headers=_headers("stu_zhang")).json()["items"]
        selected = {item["resource_type"]: item["target_view"] for item in items if item["id"] in ids}
        assert selected == {
            "course_announcement": "course-space-view",
            "assignment": "assignment-workflow-view",
            "course_question": "course-questions-view",
            "support_case": "support-workbench-view",
            "grade_submission": "teaching-operations-view",
        }
    finally:
        if ids:
            with connect() as conn:
                conn.execute(f"DELETE FROM notification WHERE id IN ({','.join('?' for _ in ids)})", tuple(ids))
                conn.commit()


def test_frontend_has_empty_error_unauthorized_mobile_and_notification_jump_contracts():
    html = Path(STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = Path(STATIC_DIR / "app.js").read_text(encoding="utf-8")
    style = Path(STATIC_DIR / "style.css").read_text(encoding="utf-8")
    assert "暂无通知" in script and "通知加载失败" in script
    assert 'data-notification-target' in script and "showView(targetButton.dataset.notificationTarget)" in script
    assert 'id="notifications-unread-count"' in html
    assert "is-error" in script and "preferredHomeView" in script
    assert "@media(max-width:680px)" in style
    assert "@media(max-width:560px)" in style
    assert "@media(max-width:520px)" in style


def test_all_product_apis_require_authentication_when_no_session_is_present():
    with TestClient(app) as client:
        for path in ("/api/workbench", "/api/notifications", "/api/teaching/classes", "/api/organization/units"):
            assert client.get(path).status_code == 401
