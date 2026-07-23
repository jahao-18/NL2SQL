from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.core.business_domains import AuthenticationError, login, token_for
from app.core.teaching_migrations import _ensure_lifecycle_identity, _ensure_role_binding
from app.main import app


USER_ID = 982001
STAFF_ID = 982001
USERNAME = "LSEC001"
PASSWORD_HASH = "pbkdf2_sha256$260000$Dj8GCQTWQUI-ZwaZ$tHkbJQ+5WRN/VByU9Ryl4+YVC2dh1KFHBpjeTeq7H7A="


@pytest.fixture(autouse=True)
def security_lifecycle_account():
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO staff
            (id, staff_no, name, college_id, department_code, employment_status, staff_type, created_at, updated_at)
            VALUES (?, 'LSEC001', '生命周期安全测试员', 1, 'PLATFORM', 'active', 'staff',
                    '2026-07-17T00:00:00+00:00', '2026-07-17T00:00:00+00:00')
            """,
            (STAFF_ID,),
        )
        conn.execute(
            """
            INSERT INTO app_user
            (id, username, display_name, role, password_hash, active, status, created_at, updated_at, session_version)
            VALUES (?, ?, '生命周期安全测试员', 'teacher', ?, 1, 'active',
                    '2026-07-17T00:00:00+00:00', '2026-07-17T00:00:00+00:00', 0)
            """,
            (USER_ID, USERNAME, PASSWORD_HASH),
        )
        conn.execute(
            """
            INSERT INTO person_identity(user_id, person_type, entity_id, status, verified_at)
            VALUES (?, 'staff', ?, 'verified', '2026-07-17T00:00:00+00:00')
            """,
            (USER_ID, STAFF_ID),
        )
        _ensure_role_binding(conn, USER_ID, "teacher", "identity", [], None, "lifecycle security test")
        _ensure_lifecycle_identity(conn, USER_ID)
        conn.commit()
    yield
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        event_ids = [row[0] for row in conn.execute(
            "SELECT id FROM identity_lifecycle_event WHERE target_user_id = ?", (USER_ID,)
        )]
        if event_ids:
            marks = ",".join("?" for _ in event_ids)
            conn.execute(f"DELETE FROM account_status_history WHERE lifecycle_event_id IN ({marks})", event_ids)
            conn.execute(f"DELETE FROM identity_lifecycle_event WHERE id IN ({marks})", event_ids)
        conn.execute("DELETE FROM account_status_history WHERE user_id = ?", (USER_ID,))
        conn.execute("DELETE FROM audit_log WHERE resource_type = 'account_security' AND resource_id = ?", (USER_ID,))
        binding_ids = [row[0] for row in conn.execute("SELECT id FROM user_role_binding WHERE user_id = ?", (USER_ID,))]
        if binding_ids:
            marks = ",".join("?" for _ in binding_ids)
            conn.execute(f"DELETE FROM role_scope_binding WHERE role_binding_id IN ({marks})", binding_ids)
        conn.execute("DELETE FROM user_role_binding WHERE user_id = ?", (USER_ID,))
        conn.execute("DELETE FROM person_affiliation WHERE person_identity_id IN (SELECT id FROM person_identity WHERE user_id = ?)", (USER_ID,))
        conn.execute("DELETE FROM person_identity WHERE user_id = ?", (USER_ID,))
        conn.execute("DELETE FROM app_user WHERE id = ?", (USER_ID,))
        conn.execute("DELETE FROM staff WHERE id = ?", (STAFF_ID,))
        conn.commit()


def _person_id() -> int:
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        return int(conn.execute("SELECT id FROM person_identity WHERE user_id = ?", (USER_ID,)).fetchone()[0])


def _admin_headers() -> dict[str, str]:
    return {"X-Demo-Token": token_for("admin")}


def test_security_suspend_revokes_sessions_and_restore_keeps_revoked_binding_revoked():
    person_id = _person_id()
    old_token = token_for(USERNAME)
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        teacher_binding = int(conn.execute(
            "SELECT id FROM user_role_binding WHERE user_id = ? AND role_code = 'teacher'", (USER_ID,)
        ).fetchone()[0])

    with TestClient(app) as client:
        suspended = client.post(
            f"/api/lifecycle/people/{person_id}/security-suspend",
            headers=_admin_headers(),
            json={"reason": "检测到异常登录，需要人工核验", "reauth_password": "123456"},
        )
        assert suspended.status_code == 200
        assert suspended.json()["item"]["account_status"] == "security_suspended"
        assert suspended.json()["item"]["session_version"] == 1
        assert client.get("/api/auth/session", headers={"X-Demo-Token": old_token}).status_code == 401
        assert client.post("/api/auth/login", json={"username": USERNAME, "password": "123456"}).status_code == 401
        with pytest.raises(AuthenticationError):
            token_for(USERNAME)

        # A role that becomes invalid while the account is frozen must not be restored implicitly.
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            conn.execute("UPDATE user_role_binding SET status = 'revoked' WHERE id = ?", (teacher_binding,))
            conn.commit()
        restored = client.post(
            f"/api/lifecycle/people/{person_id}/security-restore",
            headers=_admin_headers(),
            json={"reason": "人工核验已完成", "reauth_password": "123456"},
        )
        assert restored.status_code == 200
        assert restored.json()["item"]["account_status"] == "active"
        assert restored.json()["item"]["session_version"] == 2
        assert client.get("/api/auth/session", headers={"X-Demo-Token": old_token}).status_code == 401

    recovered = login(USERNAME, "123456")
    assert recovered.role == "self_service"
    assert "teacher" not in {item["role"] for item in recovered.available_roles}
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        statuses = conn.execute(
            "SELECT from_status, to_status, session_version FROM account_status_history WHERE user_id = ? ORDER BY id", (USER_ID,)
        ).fetchall()
        events = conn.execute(
            "SELECT event_type, status FROM identity_lifecycle_event WHERE target_user_id = ? ORDER BY id", (USER_ID,)
        ).fetchall()
        actions = {row[0] for row in conn.execute(
            "SELECT action FROM audit_log WHERE resource_type = 'account_security' AND resource_id = ?", (USER_ID,)
        ).fetchall()}
    assert statuses[-2:] == [("active", "security_suspended", 1), ("security_suspended", "active", 2)]
    assert events == [("account_security_suspend", "completed"), ("account_security_restore", "completed")]
    assert {"suspended", "restored"} <= actions


def test_security_suspend_requires_admin_reauth_and_preserves_account_on_failure():
    person_id = _person_id()
    with TestClient(app) as client:
        denied = client.post(
            f"/api/lifecycle/people/{person_id}/security-suspend",
            headers=_admin_headers(),
            json={"reason": "测试错误二验", "reauth_password": "not-the-password"},
        )
        assert denied.status_code == 403
        non_admin = client.post(
            f"/api/lifecycle/people/{person_id}/security-suspend",
            headers={"X-Demo-Token": token_for("T1001")},
            json={"reason": "越权测试", "reauth_password": "123456"},
        )
        assert non_admin.status_code == 403
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        assert conn.execute("SELECT status, session_version FROM app_user WHERE id = ?", (USER_ID,)).fetchone() == ("active", 0)
        assert conn.execute(
            "SELECT count(*) FROM audit_log WHERE resource_type = 'account_security' AND resource_id = ? AND action = 'reauth_failed'", (USER_ID,)
        ).fetchone()[0] == 1


def test_security_suspend_protects_formal_admin_floor_and_active_restore_is_rejected():
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        sys_person = int(conn.execute(
            "SELECT pi.id FROM person_identity pi JOIN app_user au ON au.id = pi.user_id WHERE au.username = 'SYS001'"
        ).fetchone()[0])
    with TestClient(app) as client:
        floor = client.post(
            f"/api/lifecycle/people/{sys_person}/security-suspend",
            headers=_admin_headers(),
            json={"reason": "验证正式管理员保底", "reauth_password": "123456"},
        )
        assert floor.status_code == 403
        restore = client.post(
            f"/api/lifecycle/people/{_person_id()}/security-restore",
            headers=_admin_headers(),
            json={"reason": "账号当前未冻结", "reauth_password": "123456"},
        )
        assert restore.status_code == 400
