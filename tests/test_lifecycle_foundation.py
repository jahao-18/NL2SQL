from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.core.business_domains import login, token_for
from app.main import app


def _headers(username: str, role_binding_id: int | None = None) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username, role_binding_id)}


def _person_id(username: str) -> int:
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        return int(conn.execute(
            """
            SELECT pi.id FROM person_identity pi JOIN app_user au ON au.id = pi.user_id
            WHERE au.username = ?
            """,
            (username,),
        ).fetchone()[0])


def test_lifecycle_schema_affiliation_and_hidden_self_service_are_seeded():
    teaching_migrations.ensure_mvp_schema()
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {
            "person_affiliation", "identity_lifecycle_event", "account_closure_request",
            "responsibility_handover", "account_status_history",
        } <= tables
        row = conn.execute(
            """
            SELECT pa.affiliation_type, pa.status, urb.role_code, urb.selectable,
                   rsb.scope_type, rsb.scope_id
            FROM app_user au JOIN person_identity pi ON pi.user_id = au.id
            JOIN person_affiliation pa ON pa.person_identity_id = pi.id
            JOIN user_role_binding urb ON urb.user_id = au.id AND urb.role_code = 'self_service'
            JOIN role_scope_binding rsb ON rsb.role_binding_id = urb.id
            WHERE au.username = 'stu_zhang'
            """
        ).fetchone()
    assert row == ("student", "active", "self_service", 0, "person_identity", _person_id("stu_zhang"))

    ctx = login("stu_zhang", "123456")
    assert ctx.role == "student"
    assert "self_service" not in {item["role"] for item in ctx.available_roles}


def test_self_service_becomes_safe_fallback_when_business_role_is_suspended():
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        binding_id = int(conn.execute(
            """
            SELECT urb.id FROM user_role_binding urb JOIN app_user au ON au.id = urb.user_id
            WHERE au.username = 'stu_zhang' AND urb.role_code = 'student' AND urb.status = 'active'
            """
        ).fetchone()[0])
        conn.execute("UPDATE user_role_binding SET status = 'suspended' WHERE id = ?", (binding_id,))
        conn.commit()
    try:
        ctx = login("stu_zhang", "123456")
        assert ctx.role == "self_service"
        assert ctx.allowed_tables == frozenset()
        assert ctx.features == frozenset({"personal_center"})
        assert ctx.row_scope == {"person_identity_id": _person_id("stu_zhang")}
    finally:
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            conn.execute("UPDATE user_role_binding SET status = 'active' WHERE id = ?", (binding_id,))
            conn.commit()


def test_lifecycle_detail_and_impact_are_read_only_and_explain_dependencies():
    person_id = _person_id("T1001")
    token = token_for("admin")
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        before = "\n".join(conn.iterdump())

    with TestClient(app) as client:
        detail = client.get(
            f"/api/lifecycle/people/{person_id}", headers={"X-Demo-Token": token}
        )
        assert detail.status_code == 200
        body = detail.json()
        assert body["read_only"] is True
        assert body["item"]["person"]["identifier"] == "T1001"
        assert body["item"]["affiliations"][0]["affiliation_type"] == "staff"
        assert {item["role_code"] for item in body["item"]["roles"]} >= {
            "college_manager", "identity_reviewer", "teacher", "self_service"
        }

        impact = client.get(
            f"/api/lifecycle/people/{person_id}/impact?event_type=staff_transfer",
            headers={"X-Demo-Token": token},
        )
        assert impact.status_code == 200
        item = impact.json()["item"]
        assert item["read_only"] is True
        assert item["execution_available"] is False
        assert item["session"]["revoke_all_sessions"] is True
        assert item["active_positions"]
        assert any(blocker["code"] == "active_positions" for blocker in item["blockers"])
        assert item["handover_required"] is True

    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        after = "\n".join(conn.iterdump())
    assert after == before


def test_lifecycle_scope_is_enforced_for_self_counselor_and_college():
    own_student = _person_id("stu_zhang")
    other_student = _person_id("stu_zhao")
    staff_other_college = _person_id("T2001")
    with TestClient(app) as client:
        own = client.get("/api/lifecycle/me", headers=_headers("stu_zhang"))
        assert own.status_code == 200
        assert own.json()["item"]["person"]["person_identity_id"] == own_student

        denied_student = client.get(
            f"/api/lifecycle/people/{other_student}", headers=_headers("stu_zhang")
        )
        assert denied_student.status_code == 403

        counselor_own = client.get(
            f"/api/lifecycle/people/{own_student}", headers=_headers("counselor_chen")
        )
        assert counselor_own.status_code == 200
        counselor_other = client.get(
            f"/api/lifecycle/people/{other_student}", headers=_headers("counselor_chen")
        )
        assert counselor_other.status_code == 403

        college_denied = client.get(
            f"/api/lifecycle/people/{staff_other_college}", headers=_headers("college")
        )
        assert college_denied.status_code == 403


def test_lifecycle_event_type_and_identity_type_are_validated():
    student_id = _person_id("stu_zhang")
    with TestClient(app) as client:
        invalid = client.get(
            f"/api/lifecycle/people/{student_id}/impact?event_type=delete_everything",
            headers=_headers("admin"),
        )
        assert invalid.status_code == 400
        wrong_identity = client.get(
            f"/api/lifecycle/people/{student_id}/impact?event_type=staff_termination",
            headers=_headers("admin"),
        )
        assert wrong_identity.status_code == 400
        own_closure = client.get(
            "/api/lifecycle/me/impact?event_type=account_closure", headers=_headers("stu_zhang")
        )
        assert own_closure.status_code == 200
        assert own_closure.json()["item"]["execution_available"] is False
