from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.core.business_domains import token_for
from app.core.teaching_migrations import _ensure_role_binding
from app.main import app


SECURITY_USER_ID = 981001
SECURITY_STAFF_ID = 981001
DEFAULT_HASH = "pbkdf2_sha256$260000$Dj8GCQTWQUI-ZwaZ$tHkbJQ+5WRN/VByU9Ryl4+YVC2dh1KFHBpjeTeq7H7A="


@pytest.fixture(autouse=True)
def security_staff_account():
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        seeded_admins = conn.execute(
            """
            SELECT pa.id, urb.id, au.id, au.session_version
            FROM position_assignment pa
            JOIN organization_position_slot ops ON ops.id = pa.position_slot_id
            JOIN user_role_binding urb ON urb.position_assignment_id = pa.id AND urb.role_code = 'admin'
            JOIN app_user au ON au.id = pa.user_id
            WHERE ops.position_code = 'platform_admin' AND au.username IN ('SYS001', 'SYS002')
            """
        ).fetchall()
        conn.execute(
            """
            INSERT INTO staff
            (id, staff_no, name, college_id, department_code, employment_status, staff_type, created_at, updated_at)
            VALUES (?, 'SEC001', '安全测试员', 1, 'PLATFORM', 'active', 'staff',
                    '2026-07-16T00:00:00+00:00', '2026-07-16T00:00:00+00:00')
            """,
            (SECURITY_STAFF_ID,),
        )
        conn.execute(
            """
            INSERT INTO app_user
            (id, username, display_name, role, password_hash, active, status, created_at, updated_at, session_version)
            VALUES (?, 'SEC001', '安全测试员', 'staff', ?, 1, 'active',
                    '2026-07-16T00:00:00+00:00', '2026-07-16T00:00:00+00:00', 0)
            """,
            (SECURITY_USER_ID, DEFAULT_HASH),
        )
        conn.execute(
            """
            INSERT INTO person_identity(user_id, person_type, entity_id, status, verified_at)
            VALUES (?, 'staff', ?, 'verified', '2026-07-16T00:00:00+00:00')
            """,
            (SECURITY_USER_ID, SECURITY_STAFF_ID),
        )
        _ensure_role_binding(conn, SECURITY_USER_ID, "staff", "identity", [], None, "security test")
        conn.commit()
    yield
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        assignment_ids = [row[0] for row in conn.execute(
            "SELECT id FROM position_assignment WHERE user_id = ?", (SECURITY_USER_ID,)
        )]
        binding_ids = [row[0] for row in conn.execute(
            "SELECT id FROM user_role_binding WHERE user_id = ?", (SECURITY_USER_ID,)
        )]
        if assignment_ids:
            marks = ",".join("?" for _ in assignment_ids)
            conn.execute(f"DELETE FROM audit_log WHERE resource_type = 'position_assignment' AND resource_id IN ({marks})", assignment_ids)
        if binding_ids:
            marks = ",".join("?" for _ in binding_ids)
            conn.execute(f"DELETE FROM role_scope_binding WHERE role_binding_id IN ({marks})", binding_ids)
        conn.execute("DELETE FROM user_role_binding WHERE user_id = ?", (SECURITY_USER_ID,))
        conn.execute("DELETE FROM position_assignment WHERE user_id = ?", (SECURITY_USER_ID,))
        conn.execute("DELETE FROM user_role WHERE user_id = ?", (SECURITY_USER_ID,))
        conn.execute("DELETE FROM person_identity WHERE user_id = ?", (SECURITY_USER_ID,))
        conn.execute("DELETE FROM app_user WHERE id = ?", (SECURITY_USER_ID,))
        conn.execute("DELETE FROM staff WHERE id = ?", (SECURITY_STAFF_ID,))
        for assignment_id, binding_id, user_id, session_version in seeded_admins:
            conn.execute(
                """
                UPDATE position_assignment SET status = 'active', valid_until = NULL,
                    ended_by_user_id = NULL, ended_at = NULL, end_reason = NULL
                WHERE id = ?
                """,
                (assignment_id,),
            )
            conn.execute(
                """
                UPDATE user_role_binding SET status = 'active', valid_until = NULL,
                    revoked_by_user_id = NULL, revoked_at = NULL, revoke_reason = NULL
                WHERE id = ?
                """,
                (binding_id,),
            )
            conn.execute("UPDATE app_user SET session_version = ? WHERE id = ?", (session_version, user_id))
        conn.commit()


def _login(client: TestClient, username: str = "admin") -> tuple[str, dict]:
    payload = client.post("/api/auth/login", json={"username": username, "password": "123456"}).json()
    return payload["token"], payload


def _headers(token: str) -> dict[str, str]:
    return {"X-Demo-Token": token}


def _platform_slot(client: TestClient, token: str) -> dict:
    units = client.get("/api/organization/units", headers=_headers(token)).json()["items"]
    platform = next(item for item in units if item["unit_type"] == "platform")
    slots = client.get(
        f"/api/organization/position-slots?organization_unit_id={platform['id']}", headers=_headers(token)
    ).json()["items"]
    return next(item for item in slots if item["position_code"] == "platform_admin")


def _appoint_security_admin(client: TestClient, token: str, password: str | None = "123456") -> dict:
    slot = _platform_slot(client, token)
    response = client.post(
        "/api/organization/position-assignments",
        headers=_headers(token),
        json={
            "position_slot_id": slot["id"],
            "user_id": SECURITY_USER_ID,
            "assignment_type": "deputy",
            "scope_ids": [],
            "valid_from": "2026-07-16",
            "valid_until": None,
            "reason": "Platform security duty",
            "reauth_password": password,
        },
    )
    return {"response": response, "slot": slot}


def test_platform_admin_operations_require_password_reauthentication():
    with TestClient(app) as client:
        token, _ = _login(client)
        missing = _appoint_security_admin(client, token, None)["response"]
        assert missing.status_code == 403
        wrong = _appoint_security_admin(client, token, "wrong-password")["response"]
        assert wrong.status_code == 403
        slot = _platform_slot(client, token)
        self_grant = client.post(
            "/api/organization/position-assignments",
            headers=_headers(token),
            json={
                "position_slot_id": slot["id"],
                "user_id": 910001,
                "assignment_type": "primary",
                "scope_ids": [],
                "valid_from": "2026-07-16",
                "reason": "Unsafe self grant",
                "reauth_password": "123456",
            },
        )
        assert self_grant.status_code == 403
        assert client.get("/api/auth/session", headers=_headers(token)).status_code == 200
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        failures = conn.execute(
            "SELECT count(*) FROM audit_log WHERE resource_type = 'platform_admin_security' AND action = 'reauth_failed'"
        ).fetchone()[0]
    assert failures >= 2


def test_formal_platform_admin_minimum_is_protected_and_old_session_is_revoked():
    with TestClient(app) as client:
        token, _ = _login(client)
        slot = _platform_slot(client, token)
        sys2 = next(item for item in slot["assignments"] if item["staff_no"] == "SYS002")
        sys2_token, _ = _login(client, "SYS002")
        impact = client.get(
            f"/api/organization/position-assignments/{sys2['id']}/impact", headers=_headers(token)
        )
        assert impact.status_code == 200
        assert impact.json()["item"]["can_end"] is False
        assert impact.json()["item"]["remaining_formal_admins"] == 1
        protected = client.post(
            f"/api/organization/position-assignments/{sys2['id']}/end",
            headers=_headers(token),
            json={"reason": "Unsafe removal", "reauth_password": "123456"},
        )
        assert protected.status_code == 400
        assert "2" in protected.json()["detail"]
        unsafe_expiry = client.patch(
            f"/api/organization/position-assignments/{sys2['id']}",
            headers=_headers(token),
            json={"valid_until": "2028-07-16", "reason": "Unsafe expiry", "reauth_password": "123456"},
        )
        assert unsafe_expiry.status_code == 400

        created = _appoint_security_admin(client, token)["response"]
        assert created.status_code == 200
        safe_impact = client.get(
            f"/api/organization/position-assignments/{sys2['id']}/impact", headers=_headers(token)
        ).json()["item"]
        assert safe_impact["can_end"] is True
        assert safe_impact["remaining_formal_admins"] == 2
        ended = client.post(
            f"/api/organization/position-assignments/{sys2['id']}/end",
            headers=_headers(token),
            json={"reason": "Scheduled rotation", "reauth_password": "123456"},
        )
        assert ended.status_code == 200
        assert client.get("/api/auth/session", headers=_headers(sys2_token)).status_code == 401


def test_platform_admin_transfer_is_atomic_and_reauthenticated():
    with TestClient(app) as client:
        token, _ = _login(client)
        slot = _platform_slot(client, token)
        sys2 = next(item for item in slot["assignments"] if item["staff_no"] == "SYS002")
        sys2_token, _ = _login(client, "SYS002")
        denied = client.post(
            f"/api/organization/position-assignments/{sys2['id']}/transfer",
            headers=_headers(token),
            json={
                "successor_user_id": SECURITY_USER_ID,
                "assignment_type": "deputy",
                "valid_from": "2026-07-16",
                "reason": "Security handover",
                "reauth_password": "wrong-password",
            },
        )
        assert denied.status_code == 403
        assert client.get("/api/auth/session", headers=_headers(sys2_token)).status_code == 200

        transferred = client.post(
            f"/api/organization/position-assignments/{sys2['id']}/transfer",
            headers=_headers(token),
            json={
                "successor_user_id": SECURITY_USER_ID,
                "assignment_type": "deputy",
                "valid_from": "2026-07-16",
                "reason": "Security handover",
                "reauth_password": "123456",
            },
        )
        assert transferred.status_code == 200
        item = transferred.json()["item"]
        assert item["role_code"] == "admin"
        assert client.get("/api/auth/session", headers=_headers(sys2_token)).status_code == 401
        successor_token = token_for("SEC001", item["role_binding_id"])
        assert client.get("/api/organization/units", headers=_headers(successor_token)).status_code == 200
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        old_status = conn.execute("SELECT status FROM position_assignment WHERE id = ?", (sys2["id"],)).fetchone()[0]
        active_formal = conn.execute(
            """
            SELECT count(*) FROM position_assignment pa JOIN organization_position_slot ops ON ops.id = pa.position_slot_id
            WHERE ops.position_code = 'platform_admin' AND pa.status = 'active'
            """
        ).fetchone()[0]
    assert old_status == "ended"
    assert active_formal == 2


def test_due_temporary_position_expires_and_revokes_token():
    with TestClient(app) as client:
        manager_token, _ = _login(client, "college")
        units = client.get("/api/organization/units", headers=_headers(manager_token)).json()["items"]
        college_unit = next(item for item in units if item["source_college_id"] == 1)
        slots = client.get(
            f"/api/organization/position-slots?organization_unit_id={college_unit['id']}",
            headers=_headers(manager_token),
        ).json()["items"]
        reviewer_slot = next(item for item in slots if item["position_code"] == "identity_reviewer")
        created = client.post(
            "/api/organization/position-assignments",
            headers=_headers(manager_token),
            json={
                "position_slot_id": reviewer_slot["id"],
                "user_id": SECURITY_USER_ID,
                "assignment_type": "temporary",
                "scope_ids": [],
                "valid_from": "2026-07-16",
                "valid_until": "2028-07-16",
                "reason": "Temporary review cover",
            },
        )
        assert created.status_code == 200
        item = created.json()["item"]
        temporary_token = token_for("SEC001", item["role_binding_id"])
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            conn.execute("UPDATE position_assignment SET valid_until = '2000-01-01' WHERE id = ?", (item["id"],))
            conn.execute("UPDATE user_role_binding SET valid_until = '2000-01-01' WHERE id = ?", (item["role_binding_id"],))
            conn.commit()
        assert client.get("/api/auth/session", headers=_headers(temporary_token)).status_code == 401
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        assignment_status = conn.execute("SELECT status FROM position_assignment WHERE id = ?", (item["id"],)).fetchone()[0]
        binding_status = conn.execute("SELECT status FROM user_role_binding WHERE id = ?", (item["role_binding_id"],)).fetchone()[0]
        audit = conn.execute(
            "SELECT action FROM audit_log WHERE resource_type = 'position_assignment' AND resource_id = ? ORDER BY id DESC LIMIT 1",
            (item["id"],),
        ).fetchone()[0]
    assert (assignment_status, binding_status, audit) == ("expired", "expired", "expired")


def test_temporary_and_acting_assignments_require_expiry():
    with TestClient(app) as client:
        manager_token, _ = _login(client, "college")
        units = client.get("/api/organization/units", headers=_headers(manager_token)).json()["items"]
        unit = next(item for item in units if item["source_college_id"] == 1)
        slots = client.get(
            f"/api/organization/position-slots?organization_unit_id={unit['id']}", headers=_headers(manager_token)
        ).json()["items"]
        reviewer_slot = next(item for item in slots if item["position_code"] == "identity_reviewer")
        response = client.post(
            "/api/organization/position-assignments",
            headers=_headers(manager_token),
            json={
                "position_slot_id": reviewer_slot["id"],
                "user_id": SECURITY_USER_ID,
                "assignment_type": "acting",
                "scope_ids": [],
                "valid_from": "2026-07-16",
                "valid_until": None,
                "reason": "Acting cover",
            },
        )
    assert response.status_code == 400


def test_admin_lifecycle_frontend_is_wired():
    root = teaching_migrations.ROOT_DIR
    html = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    api_js = (root / "app" / "static" / "api.js").read_text(encoding="utf-8")
    assert 'id="organization-reauth-password"' in html
    assert 'id="organization-transfer-modal"' in html
    assert 'id="organization-transfer-successor"' in html
    assert "data-transfer-assignment-id" in js
    assert "reauth_password" in js
    assert "submitOrganizationTransfer" in js
    assert "positionAssignmentImpact" in js
    assert "/transfer`" in api_js
