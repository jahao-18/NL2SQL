from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.main import app


def _headers(token: str) -> dict[str, str]:
    return {"X-Demo-Token": token}


def test_multi_role_login_requires_selection_and_switches_isolated_scope():
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "T1001", "password": "123456"})
        assert login.status_code == 200
        payload = login.json()
        assert payload["role_selection_required"] is True
        roles = payload["user"]["available_roles"]
        assert {item["role"] for item in roles} >= {"college_manager", "teacher"}
        manager_binding = next(item for item in roles if item["role"] == "college_manager")
        teacher_binding = next(item for item in roles if item["role"] == "teacher")
        manager_token = payload["token"]
        assert payload["user"]["role_binding_id"] == manager_binding["id"]
        assert client.get("/api/organization/units", headers=_headers(manager_token)).status_code == 200

        switched = client.post(
            "/api/auth/switch-role",
            headers=_headers(manager_token),
            json={"role_binding_id": teacher_binding["id"]},
        )
        assert switched.status_code == 200
        teacher_payload = switched.json()
        teacher_token = teacher_payload["token"]
        assert teacher_payload["role_selection_required"] is False
        assert teacher_payload["user"]["role"] == "teacher"
        assert teacher_payload["user"]["role_binding_id"] == teacher_binding["id"]
        assert "organization_management" not in teacher_payload["user"]["features"]
        assert client.get("/api/auth/session", headers=_headers(manager_token)).status_code == 401
        assert client.get("/api/organization/units", headers=_headers(teacher_token)).status_code == 403
        assert client.get("/api/teaching/classes", headers=_headers(teacher_token)).status_code == 200

        restored = client.get("/api/auth/session", headers=_headers(teacher_token))
        assert restored.status_code == 200
        assert restored.json()["user"]["role"] == "teacher"
        assert restored.json()["user"]["role_binding_id"] == teacher_binding["id"]

        switched_back = client.post(
            "/api/auth/switch-role",
            headers=_headers(teacher_token),
            json={"role_binding_id": manager_binding["id"]},
        )
        assert switched_back.status_code == 200
        new_manager_token = switched_back.json()["token"]
        assert switched_back.json()["user"]["role"] == "college_manager"
        assert client.get("/api/auth/session", headers=_headers(teacher_token)).status_code == 401
        assert client.get("/api/organization/units", headers=_headers(new_manager_token)).status_code == 200


def test_invalid_role_binding_does_not_revoke_current_session():
    with TestClient(app) as client:
        payload = client.post("/api/auth/login", json={"username": "T1001", "password": "123456"}).json()
        token = payload["token"]
        denied = client.post(
            "/api/auth/switch-role",
            headers=_headers(token),
            json={"role_binding_id": 999999999},
        )
        assert denied.status_code == 403
        assert client.get("/api/auth/session", headers=_headers(token)).status_code == 200


def test_single_role_login_enters_directly_without_role_selection():
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"username": "stu_zhang", "password": "123456"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["role_selection_required"] is False
    assert payload["user"]["role"] == "student"
    assert len(payload["user"]["available_roles"]) == 1


def test_teacher_can_switch_to_counselor_and_get_only_counselor_workspace():
    with TestClient(app) as client:
        payload = client.post("/api/auth/login", json={"username": "tea_li", "password": "123456"}).json()
        roles = payload["user"]["available_roles"]
        assert {item["role"] for item in roles} == {"teacher", "counselor"}
        counselor_binding = next(item for item in roles if item["role"] == "counselor")
        teacher_token = payload["token"]
        assert payload["user"]["role"] == "teacher"
        switched = client.post(
            "/api/auth/switch-role",
            headers=_headers(teacher_token),
            json={"role_binding_id": counselor_binding["id"]},
        )
        assert switched.status_code == 200
        counselor_token = switched.json()["token"]
        assert switched.json()["user"]["role"] == "counselor"
        assert "student_support" in switched.json()["user"]["features"]
        assert "course_analytics" not in switched.json()["user"]["features"]
        assert client.get("/api/auth/session", headers=_headers(teacher_token)).status_code == 401
        assert client.get("/api/teaching/support/cases", headers=_headers(counselor_token)).status_code == 200
        assert client.get("/api/teaching/classes", headers=_headers(counselor_token)).status_code == 403


def test_role_switch_is_audited():
    with TestClient(app) as client:
        payload = client.post("/api/auth/login", json={"username": "T1001", "password": "123456"}).json()
        teacher_binding = next(item for item in payload["user"]["available_roles"] if item["role"] == "teacher")
        response = client.post(
            "/api/auth/switch-role",
            headers=_headers(payload["token"]),
            json={"role_binding_id": teacher_binding["id"]},
        )
        assert response.status_code == 200
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT actor_user, actor_role, action, resource_id
            FROM audit_log WHERE resource_type = 'role_session'
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
    assert row == ("T1001", "college_manager", "switched", teacher_binding["id"])


def test_role_selection_frontend_is_wired():
    html = (teaching_migrations.ROOT_DIR / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (teaching_migrations.ROOT_DIR / "app" / "static" / "app.js").read_text(encoding="utf-8")
    api_js = (teaching_migrations.ROOT_DIR / "app" / "static" / "api.js").read_text(encoding="utf-8")
    assert 'id="role-selection-panel"' in html
    assert 'id="role-selection-list"' in html
    assert "role_selection_required" in js
    assert "showRoleSelection" in js
    assert "data-role-binding-id" in js
    assert 'json("POST", "/api/auth/switch-role"' in api_js
