from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.core.business_domains import AuthenticationError, token_for
from app.core.teaching_migrations import _ensure_lifecycle_identity, _ensure_role_binding
from app.main import app


USER_ID, STAFF_ID, USERNAME = 983001, 983001, "LSTAFF001"
PASSWORD_HASH = "pbkdf2_sha256$260000$Dj8GCQTWQUI-ZwaZ$tHkbJQ+5WRN/VByU9Ryl4+YVC2dh1KFHBpjeTeq7H7A="


@pytest.fixture(autouse=True)
def staff_account():
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.execute("INSERT INTO staff(id, staff_no, name, college_id, department_code, employment_status, staff_type, created_at, updated_at) VALUES (?, 'LSTAFF001', '职工生命周期测试员', 1, 'TEST', 'active', 'staff', '2026-07-17T00:00:00+00:00', '2026-07-17T00:00:00+00:00')", (STAFF_ID,))
        conn.execute("INSERT INTO app_user(id, username, display_name, role, password_hash, active, status, created_at, updated_at, session_version) VALUES (?, ?, '职工生命周期测试员', 'teacher', ?, 1, 'active', '2026-07-17T00:00:00+00:00', '2026-07-17T00:00:00+00:00', 0)", (USER_ID, USERNAME, PASSWORD_HASH))
        conn.execute("INSERT INTO person_identity(user_id, person_type, entity_id, status, verified_at) VALUES (?, 'staff', ?, 'verified', '2026-07-17T00:00:00+00:00')", (USER_ID, STAFF_ID))
        _ensure_role_binding(conn, USER_ID, "teacher", "identity", [], None, "staff lifecycle test")
        _ensure_lifecycle_identity(conn, USER_ID); conn.commit()
    yield
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        events = [row[0] for row in conn.execute("SELECT id FROM identity_lifecycle_event WHERE target_user_id = ?", (USER_ID,))]
        if events:
            marks = ",".join("?" for _ in events); conn.execute(f"DELETE FROM account_status_history WHERE lifecycle_event_id IN ({marks})", events); conn.execute(f"DELETE FROM responsibility_handover WHERE lifecycle_event_id IN ({marks})", events); conn.execute(f"DELETE FROM identity_lifecycle_event WHERE id IN ({marks})", events)
        conn.execute("DELETE FROM audit_log WHERE resource_type = 'student_lifecycle' AND resource_id = ?", (STAFF_ID,))
        bindings = [row[0] for row in conn.execute("SELECT id FROM user_role_binding WHERE user_id = ?", (USER_ID,))]
        if bindings:
            marks = ",".join("?" for _ in bindings); conn.execute(f"DELETE FROM role_scope_binding WHERE role_binding_id IN ({marks})", bindings)
        conn.execute("DELETE FROM user_role_binding WHERE user_id = ?", (USER_ID,)); conn.execute("DELETE FROM person_affiliation WHERE person_identity_id IN (SELECT id FROM person_identity WHERE user_id = ?)", (USER_ID,)); conn.execute("DELETE FROM person_identity WHERE user_id = ?", (USER_ID,)); conn.execute("DELETE FROM app_user WHERE id = ?", (USER_ID,)); conn.execute("DELETE FROM staff WHERE id = ?", (STAFF_ID,)); conn.commit()


def _person_id() -> int:
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn: return int(conn.execute("SELECT id FROM person_identity WHERE user_id = ?", (USER_ID,)).fetchone()[0])


def _headers(username: str) -> dict[str, str]: return {"X-Demo-Token": token_for(username)}


def test_staff_termination_needs_two_distinct_admins_and_archives_account():
    person_id, old_token = _person_id(), token_for(USERNAME)
    with TestClient(app) as client:
        request = client.post(f"/api/lifecycle/staff/{person_id}/events/staff_termination/request", headers=_headers("admin"), json={"reason": "人事离职手续已完成", "reauth_password": "123456"})
        assert request.status_code == 200
        event_id = request.json()["item"]["event_id"]
        same = client.post(f"/api/lifecycle/staff/events/{event_id}/confirm", headers=_headers("admin"), json={"reason": "ignored", "reauth_password": "123456"})
        assert same.status_code == 403
        confirmed = client.post(f"/api/lifecycle/staff/events/{event_id}/confirm", headers=_headers("SYS001"), json={"reason": "ignored", "reauth_password": "123456"})
        assert confirmed.status_code == 200
        assert client.get("/api/auth/session", headers={"X-Demo-Token": old_token}).status_code == 401
        assert client.post("/api/auth/login", json={"username": USERNAME, "password": "123456"}).status_code == 401
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        assert conn.execute("SELECT employment_status FROM staff WHERE id = ?", (STAFF_ID,)).fetchone()[0] == "terminated"
        assert conn.execute("SELECT status FROM app_user WHERE id = ?", (USER_ID,)).fetchone()[0] == "archived"
        assert conn.execute("SELECT status FROM identity_lifecycle_event WHERE id = ?", (event_id,)).fetchone()[0] == "completed"
    with pytest.raises(AuthenticationError): token_for(USERNAME)


def test_cross_college_transfer_requires_second_admin_and_does_not_grant_new_role():
    person_id, old_token = _person_id(), token_for(USERNAME)
    with TestClient(app) as client:
        request = client.post(f"/api/lifecycle/staff/{person_id}/transfer/request", headers=_headers("admin"), json={"destination_college_id": 2, "reason": "跨学院调动", "reauth_password": "123456"})
        assert request.status_code == 200
        confirmed = client.post(f"/api/lifecycle/staff/events/{request.json()['item']['event_id']}/confirm", headers=_headers("SYS001"), json={"reason": "ignored", "reauth_password": "123456"})
        assert confirmed.status_code == 200
        assert client.get("/api/auth/session", headers={"X-Demo-Token": old_token}).status_code == 401
        fresh = client.post("/api/auth/login", json={"username": USERNAME, "password": "123456"})
        assert fresh.status_code == 200 and fresh.json()["user"]["role"] == "self_service"
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        assert conn.execute("SELECT college_id, employment_status FROM staff WHERE id = ?", (STAFF_ID,)).fetchone() == (2, "active")
        assert conn.execute("SELECT count(*) FROM user_role_binding WHERE user_id = ? AND role_code = 'teacher' AND status = 'active'", (USER_ID,)).fetchone()[0] == 0
