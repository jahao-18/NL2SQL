from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.core.business_domains import token_for
from app.core.config import STATIC_DIR
from app.main import app


STUDENT_ID = 980001
STUDENT_ID_2 = 980002
TEACHER_ID = 980001


@pytest.fixture(autouse=True)
def registration_identities():
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO student
            (id, student_no, name, gender, college_id, major_id, class_id, enrollment_year, status)
            VALUES (?, 'REG2026001', '注册测试学生', 'female', 1, 1, 900001, 2026, 'active')
            """,
            (STUDENT_ID,),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO student
            (id, student_no, name, gender, college_id, major_id, class_id, enrollment_year, status)
            VALUES (?, 'REG2026002', '注册测试学生二', 'male', 1, 1, 900001, 2026, 'active')
            """,
            (STUDENT_ID_2,),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO teacher
            (id, teacher_no, name, gender, college_id, title, hire_date)
            VALUES (?, 'REGT2026001', '注册测试教师', 'male', 1, '讲师', '2026-07-01')
            """,
            (TEACHER_ID,),
        )
        conn.commit()
    yield
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        user_ids = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT user_id FROM identity_application WHERE submitted_identifier IN ('REG2026001', 'REG2026002', 'REGT2026001')"
            )
        ]
        if user_ids:
            marks = ",".join("?" for _ in user_ids)
            application_ids = [row[0] for row in conn.execute(f"SELECT id FROM identity_application WHERE user_id IN ({marks})", user_ids)]
            if application_ids:
                app_marks = ",".join("?" for _ in application_ids)
                conn.execute(f"DELETE FROM audit_log WHERE resource_type = 'identity_application' AND resource_id IN ({app_marks})", application_ids)
                conn.execute(f"DELETE FROM review_task WHERE resource_type = 'identity_application' AND resource_id IN ({app_marks})", application_ids)
            binding_ids = [row[0] for row in conn.execute(f"SELECT id FROM user_role_binding WHERE user_id IN ({marks})", user_ids)]
            if binding_ids:
                binding_marks = ",".join("?" for _ in binding_ids)
                conn.execute(f"DELETE FROM role_scope_binding WHERE role_binding_id IN ({binding_marks})", binding_ids)
            conn.execute(f"DELETE FROM user_role_binding WHERE user_id IN ({marks})", user_ids)
            conn.execute(f"DELETE FROM person_identity WHERE user_id IN ({marks})", user_ids)
            conn.execute(f"DELETE FROM identity_binding WHERE user_id IN ({marks})", user_ids)
            conn.execute(f"DELETE FROM identity_application WHERE user_id IN ({marks})", user_ids)
            conn.execute(f"DELETE FROM user_role WHERE user_id IN ({marks})", user_ids)
            conn.execute(f"DELETE FROM app_user WHERE id IN ({marks})", user_ids)
        conn.execute("DELETE FROM student WHERE id = ?", (STUDENT_ID,))
        conn.execute("DELETE FROM student WHERE id = ?", (STUDENT_ID_2,))
        conn.execute("DELETE FROM teacher WHERE id = ?", (TEACHER_ID,))
        conn.execute("DELETE FROM staff WHERE teacher_id = ?", (TEACHER_ID,))
        conn.commit()


def _headers(username: str) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username)}


def _register(client: TestClient, *, username: str, identity_type: str, name: str, identifier: str):
    return client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "Register123",
            "display_name": name,
            "identity_type": identity_type,
            "identifier": identifier,
        },
    )


def test_student_registration_routes_to_assigned_counselor_and_blocks_business_until_approved():
    with TestClient(app) as client:
        created = _register(
            client,
            username="regtest_student",
            identity_type="student",
            name="注册测试学生",
            identifier="REG2026001",
        )
        assert created.status_code == 200
        item = created.json()["item"]
        assert item["status"] == "pending"
        assert item["username"] == "REG2026001"
        assert item["assigned_approver_role"] == "counselor"
        assert item["class_name"] == "软件工程2023-1班"

        login = client.post("/api/auth/login", json={"username": "REG2026001", "password": "Register123"})
        assert login.status_code == 200
        token = login.json()["token"]
        pending_headers = {"X-Demo-Token": token}
        assert login.json()["user"]["account_status"] == "pending_approval"
        assert client.get("/api/auth/application", headers=pending_headers).status_code == 200
        assert client.get("/api/workbench", headers=pending_headers).status_code == 403

        counselor_items = client.get("/api/auth/applications", headers=_headers("counselor_chen")).json()["items"]
        assert [row["id"] for row in counselor_items] == [item["id"]]
        denied = client.post(
            f"/api/auth/applications/{item['id']}/review",
            headers=_headers("counselor_lin"),
            json={"decision": "approve", "note": "越权尝试"},
        )
        assert denied.status_code == 403

        approved = client.post(
            f"/api/auth/applications/{item['id']}/review",
            headers=_headers("counselor_chen"),
            json={"decision": "approve", "note": "班级名单核对无误"},
        )
        assert approved.status_code == 200
        assert approved.json()["item"]["status"] == "approved"

        session = client.get("/api/auth/session", headers=pending_headers)
        assert session.status_code == 200
        assert session.json()["user"]["role"] == "student"
        assert session.json()["user"]["account_status"] == "active"
        assert client.get("/api/sources", headers=pending_headers).status_code == 200

    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        row = conn.execute(
            "SELECT student_id, role, status FROM app_user WHERE username = 'REG2026001'"
        ).fetchone()
    assert row == (STUDENT_ID, "student", "active")


def test_teacher_registration_routes_to_college_manager():
    with TestClient(app) as client:
        created = _register(
            client,
            username="regtest_teacher",
            identity_type="teacher",
            name="注册测试教师",
            identifier="REGT2026001",
        )
        assert created.status_code == 200
        item = created.json()["item"]
        assert item["assigned_approver_role"] == "college_manager"
        college_items = client.get("/api/auth/applications", headers=_headers("college")).json()["items"]
        assert any(row["id"] == item["id"] for row in college_items)

        counselor_denied = client.post(
            f"/api/auth/applications/{item['id']}/review",
            headers=_headers("counselor_chen"),
            json={"decision": "approve"},
        )
        assert counselor_denied.status_code == 403
        approved = client.post(
            f"/api/auth/applications/{item['id']}/review",
            headers=_headers("college"),
            json={"decision": "approve"},
        )
        assert approved.status_code == 200

    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        row = conn.execute(
            "SELECT teacher_id, college_id, role, status FROM app_user WHERE username = 'REGT2026001'"
        ).fetchone()
    assert row == (TEACHER_ID, 1, "teacher", "active")


def test_registration_rejects_identity_mismatch_duplicate_binding_and_privileged_role():
    with TestClient(app) as client:
        mismatch = _register(
            client,
            username="regtest_wrong",
            identity_type="student",
            name="错误姓名",
            identifier="REG2026001",
        )
        assert mismatch.status_code == 400

        invalid_role = _register(
            client,
            username="regtest_admin",
            identity_type="admin",
            name="注册测试学生",
            identifier="REG2026001",
        )
        assert invalid_role.status_code == 422

        first = _register(
            client,
            username="regtest_first",
            identity_type="student",
            name="注册测试学生",
            identifier="REG2026001",
        )
        assert first.status_code == 200
        pending_duplicate = _register(
            client,
            username="regtest_pending_duplicate",
            identity_type="student",
            name="注册测试学生",
            identifier="REG2026001",
        )
        assert pending_duplicate.status_code == 400
        assert "已注册" in pending_duplicate.json()["detail"]
        approved = client.post(
            f"/api/auth/applications/{first.json()['item']['id']}/review",
            headers=_headers("counselor_chen"),
            json={"decision": "approve"},
        )
        assert approved.status_code == 200
        duplicate = _register(
            client,
            username="regtest_second",
            identity_type="student",
            name="注册测试学生",
            identifier="REG2026001",
        )
        assert duplicate.status_code == 400
        assert "已注册" in duplicate.json()["detail"]


def test_ordinary_roles_cannot_open_identity_approval_queue():
    with TestClient(app) as client:
        assert client.get("/api/auth/applications", headers=_headers("stu_zhang")).status_code == 403
        assert client.get("/api/auth/applications", headers=_headers("tea_li")).status_code == 403


def test_counselor_can_batch_approve_students_in_own_classes():
    with TestClient(app) as client:
        first = _register(client, username="ignored_one", identity_type="student", name="注册测试学生", identifier="REG2026001")
        second = _register(client, username="ignored_two", identity_type="student", name="注册测试学生二", identifier="REG2026002")
        assert first.status_code == second.status_code == 200
        ids = [first.json()["item"]["id"], second.json()["item"]["id"]]
        result = client.post(
            "/api/auth/applications/batch-review",
            headers=_headers("counselor_chen"),
            json={"application_ids": ids, "decision": "approve", "note": "批量核对班级名单"},
        )
        assert result.status_code == 200
        assert result.json()["processed_count"] == 2
        assert {item["status"] for item in result.json()["items"]} == {"approved"}

        replay = client.post(
            "/api/auth/applications/batch-review",
            headers=_headers("counselor_chen"),
            json={"application_ids": ids, "decision": "approve"},
        )
        assert replay.status_code == 403


def test_approval_navigation_is_scoped_to_organization_reviewers():
    with TestClient(app) as client:
        counselor = client.get("/api/auth/me", headers=_headers("counselor_chen")).json()["item"]
        college = client.get("/api/auth/me", headers=_headers("college")).json()["item"]
        student = client.get("/api/auth/me", headers=_headers("stu_zhang")).json()["item"]
        teacher = client.get("/api/auth/me", headers=_headers("tea_li")).json()["item"]
    assert "identity-approval-view" in {row["view"] for row in counselor["navigation"]}
    assert "identity-approval-view" in {row["view"] for row in college["navigation"]}
    assert "identity-approval-view" not in {row["view"] for row in student["navigation"]}
    assert "identity-approval-view" not in {row["view"] for row in teacher["navigation"]}


def test_registration_frontend_does_not_offer_privileged_roles():
    html = Path(STATIC_DIR / "index.html").read_text(encoding="utf-8")
    js = Path(STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert 'id="register-form"' in html
    assert 'id="register-username"' not in html
    assert '<option value="student">学生</option>' in html
    assert '<option value="teacher">教职工</option>' in html
    register_fragment = html.split('id="register-form"', 1)[1].split("</form>", 1)[0]
    assert 'value="admin"' not in register_fragment
    assert 'value="college_manager"' not in register_fragment
    assert 'id="registration-status-panel"' in html
    assert 'id="identity-approval-view"' in html
    assert "api.register" in js
    assert "api.reviewIdentityApplication" in js
    assert "api.batchReviewIdentityApplications" in js
