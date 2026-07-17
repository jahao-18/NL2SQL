from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.core.business_domains import token_for
from app.core.teaching_migrations import _ensure_role_binding
from app.main import app


TEST_USERS = ((980101, 980101, "ORGTEST001", "组织测试甲", 1), (980102, 980102, "ORGTEST002", "组织测试乙", 2))
DEFAULT_HASH = "pbkdf2_sha256$260000$Dj8GCQTWQUI-ZwaZ$tHkbJQ+5WRN/VByU9Ryl4+YVC2dh1KFHBpjeTeq7H7A="


@pytest.fixture(autouse=True)
def organization_test_staff():
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        for staff_id, user_id, staff_no, name, college_id in TEST_USERS:
            conn.execute(
                """
                INSERT OR REPLACE INTO staff
                (id, staff_no, name, college_id, department_code, employment_status, staff_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'TEST', 'active', 'staff', '2026-07-16T00:00:00+00:00', '2026-07-16T00:00:00+00:00')
                """,
                (staff_id, staff_no, name, college_id),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO app_user
                (id, username, display_name, role, password_hash, college_id, active, status,
                 created_at, updated_at, session_version)
                VALUES (?, ?, ?, 'staff', ?, ?, 1, 'active',
                        '2026-07-16T00:00:00+00:00', '2026-07-16T00:00:00+00:00', 0)
                """,
                (user_id, staff_no, name, DEFAULT_HASH, college_id),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO person_identity
                (user_id, person_type, entity_id, status, verified_at)
                VALUES (?, 'staff', ?, 'verified', '2026-07-16T00:00:00+00:00')
                """,
                (user_id, staff_id),
            )
            _ensure_role_binding(conn, user_id, "staff", "identity", [], None, "组织测试身份")
        conn.commit()
    yield
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        user_ids = [row[1] for row in TEST_USERS]
        staff_ids = [row[0] for row in TEST_USERS]
        marks = ",".join("?" for _ in user_ids)
        assignment_ids = [row[0] for row in conn.execute(f"SELECT id FROM position_assignment WHERE user_id IN ({marks})", user_ids)]
        if assignment_ids:
            assignment_marks = ",".join("?" for _ in assignment_ids)
            conn.execute(f"DELETE FROM audit_log WHERE resource_type = 'position_assignment' AND resource_id IN ({assignment_marks})", assignment_ids)
        binding_ids = [row[0] for row in conn.execute(f"SELECT id FROM user_role_binding WHERE user_id IN ({marks})", user_ids)]
        if binding_ids:
            binding_marks = ",".join("?" for _ in binding_ids)
            conn.execute(f"DELETE FROM role_scope_binding WHERE role_binding_id IN ({binding_marks})", binding_ids)
        conn.execute(f"DELETE FROM user_role_binding WHERE user_id IN ({marks})", user_ids)
        conn.execute(f"DELETE FROM position_assignment WHERE user_id IN ({marks})", user_ids)
        counselor_ids = [row[0] for row in conn.execute("SELECT id FROM counselor WHERE counselor_no IN ('ORGTEST001','ORGTEST002')")]
        if counselor_ids:
            counselor_marks = ",".join("?" for _ in counselor_ids)
            conn.execute(f"DELETE FROM counselor_class_group WHERE counselor_id IN ({counselor_marks})", counselor_ids)
            conn.execute(f"DELETE FROM counselor WHERE id IN ({counselor_marks})", counselor_ids)
        conn.execute(f"DELETE FROM user_role WHERE user_id IN ({marks})", user_ids)
        conn.execute(f"DELETE FROM person_identity WHERE user_id IN ({marks})", user_ids)
        conn.execute(f"DELETE FROM app_user WHERE id IN ({marks})", user_ids)
        staff_marks = ",".join("?" for _ in staff_ids)
        conn.execute(f"DELETE FROM staff WHERE id IN ({staff_marks})", staff_ids)
        conn.commit()


def _headers(username: str, role_binding_id: int | None = None) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username, role_binding_id)}


def _slot_id(client: TestClient, username: str, college_id: int, position_code: str) -> int:
    units = client.get("/api/organization/units", headers=_headers(username)).json()["items"]
    unit_id = next(item["id"] for item in units if item.get("source_college_id") == college_id)
    slots = client.get(
        f"/api/organization/position-slots?organization_unit_id={unit_id}", headers=_headers(username)
    ).json()["items"]
    return next(item["id"] for item in slots if item["position_code"] == position_code)


def organization_unit_id(client: TestClient, college_id: int) -> int:
    units = client.get("/api/organization/units", headers=_headers("college")).json()["items"]
    return next(item["id"] for item in units if item.get("source_college_id") == college_id)


def test_six_colleges_have_independent_named_position_coverage():
    with TestClient(app) as client:
        response = client.get("/api/organization/units", headers=_headers("admin"))
    assert response.status_code == 200
    colleges = [item for item in response.json()["items"] if item["unit_type"] == "college"]
    assert len(colleges) == 6
    assert all(item["primary_managers"] >= 1 for item in colleges)
    assert all(item["identity_reviewers"] >= 1 for item in colleges)


def test_college_manager_directory_and_queues_are_limited_to_own_college():
    with TestClient(app) as client:
        units = client.get("/api/organization/units", headers=_headers("college")).json()["items"]
        assert {item["source_college_id"] for item in units} == {1}
        staff = client.get("/api/organization/staff?college_id=2", headers=_headers("college")).json()["items"]
        assert staff and {item["college_id"] for item in staff} == {1}
        classes = client.get("/api/organization/class-groups?college_id=2", headers=_headers("college")).json()["items"]
        assert classes and {item["college_id"] for item in classes} == {1}
        queues = client.get("/api/organization/review-queues", headers=_headers("college")).json()["items"]
        assert queues
        assert all(item["organization_unit_id"] == 110001 for item in queues)


def test_college_manager_can_appoint_and_end_identity_reviewer_in_own_college():
    with TestClient(app) as client:
        slot_id = _slot_id(client, "college", 1, "identity_reviewer")
        created = client.post(
            "/api/organization/position-assignments",
            headers=_headers("college"),
            json={
                "position_slot_id": slot_id,
                "user_id": 980101,
                "assignment_type": "reviewer",
                "scope_ids": [],
                "valid_from": "2026-07-16",
                "valid_until": "2027-07-15",
                "reason": "学院身份审核工作安排",
            },
        )
        assert created.status_code == 200
        item = created.json()["item"]
        assert item["role_code"] == "identity_reviewer"
        reviewer_headers = _headers("ORGTEST001", item["role_binding_id"])
        assert client.get("/api/auth/applications", headers=reviewer_headers).status_code == 200

        ended = client.post(
            f"/api/organization/position-assignments/{item['id']}/end",
            headers=_headers("college"),
            json={"reason": "岗位轮换"},
        )
        assert ended.status_code == 200
        assert ended.json()["ended"] is True
        assert client.get("/api/auth/applications", headers=reviewer_headers).status_code == 401


def test_college_manager_cannot_appoint_other_college_or_cross_college_classes():
    with TestClient(app) as client:
        college_two_slot = _slot_id(client, "jwc", 2, "identity_reviewer")
        denied_slot = client.post(
            "/api/organization/position-assignments",
            headers=_headers("college"),
            json={
                "position_slot_id": college_two_slot,
                "user_id": 980102,
                "assignment_type": "reviewer",
                "scope_ids": [],
                "valid_from": "2026-07-16",
                "reason": "越权任命",
            },
        )
        assert denied_slot.status_code == 403

        counselor_slot = _slot_id(client, "college", 1, "counselor")
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            other_class_id = conn.execute(
                """
                SELECT cg.id FROM class_group cg JOIN major m ON m.id = cg.major_id
                WHERE m.college_id = 2 LIMIT 1
                """
            ).fetchone()[0]
        denied_class = client.post(
            "/api/organization/position-assignments",
            headers=_headers("college"),
            json={
                "position_slot_id": counselor_slot,
                "user_id": 980101,
                "assignment_type": "primary",
                "scope_ids": [other_class_id],
                "valid_from": "2026-07-16",
                "reason": "越权行政班",
            },
        )
        assert denied_class.status_code == 403


def test_college_manager_can_adjust_counselor_scope_and_renew_assignment():
    with TestClient(app) as client:
        counselor_slot = _slot_id(client, "college", 1, "counselor")
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            class_ids = [
                int(row[0])
                for row in conn.execute(
                    """
                    SELECT cg.id FROM class_group cg JOIN major m ON m.id = cg.major_id
                    WHERE m.college_id = 1 ORDER BY cg.id LIMIT 2
                    """
                ).fetchall()
            ]
        assert len(class_ids) == 2
        created = client.post(
            "/api/organization/position-assignments",
            headers=_headers("college"),
            json={
                "position_slot_id": counselor_slot,
                "user_id": 980101,
                "assignment_type": "primary",
                "scope_ids": class_ids,
                "valid_from": "2026-07-16",
                "valid_until": "2026-12-31",
                "reason": "Initial class assignment",
            },
        )
        assert created.status_code == 200
        assignment = created.json()["item"]
        stale_headers = _headers("ORGTEST001", assignment["role_binding_id"])

        updated = client.patch(
            f"/api/organization/position-assignments/{assignment['id']}",
            headers=_headers("college"),
            json={
                "scope_ids": [class_ids[1]],
                "valid_until": "2027-12-31",
                "reason": "Renew and adjust class scope",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["scopes"] == [{"scope_type": "class_group", "scope_id": class_ids[1]}]
        assert client.get("/api/auth/session", headers=stale_headers).status_code == 401

        slots = client.get(
            f"/api/organization/position-slots?organization_unit_id={organization_unit_id(client, 1)}",
            headers=_headers("college"),
        ).json()["items"]
        slot = next(item for item in slots if item["id"] == counselor_slot)
        saved = next(item for item in slot["assignments"] if item["id"] == assignment["id"])
        assert saved["scope_ids"] == [class_ids[1]]
        assert saved["valid_until"] == "2027-12-31"


def test_student_and_teacher_cannot_access_organization_management():
    with TestClient(app) as client:
        for username in ("stu_zhang", "tea_li"):
            assert client.get("/api/organization/units", headers=_headers(username)).status_code == 403
            assert client.get("/api/organization/staff", headers=_headers(username)).status_code == 403
