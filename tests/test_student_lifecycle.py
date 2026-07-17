from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.core.business_domains import token_for
from app.main import app


USERNAMES = ("stu_zhang", "stu_wang", "stu_zhao")


def _identity_id(username: str) -> int:
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        return int(conn.execute(
            "SELECT pi.id FROM person_identity pi JOIN app_user au ON au.id = pi.user_id WHERE au.username = ?",
            (username,),
        ).fetchone()[0])


def _student_id(username: str) -> int:
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        return int(conn.execute(
            "SELECT pi.entity_id FROM person_identity pi JOIN app_user au ON au.id = pi.user_id WHERE au.username = ?",
            (username,),
        ).fetchone()[0])


@pytest.fixture(autouse=True)
def restore_student_lifecycle_state():
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT pi.id AS person_identity_id, pi.entity_id AS student_id, au.id AS user_id, au.username, "
            "au.status AS account_status, au.session_version, s.status AS student_status "
            "FROM app_user au JOIN person_identity pi ON pi.user_id = au.id JOIN student s ON s.id = pi.entity_id "
            f"WHERE au.username IN ({','.join('?' for _ in USERNAMES)})",
            USERNAMES,
        ).fetchall()
        baseline = {row["username"]: dict(row) for row in rows}
        binding_rows = conn.execute(
            f"SELECT id, user_id, status, valid_until, revoked_by_user_id, revoked_at, revoke_reason "
            f"FROM user_role_binding WHERE user_id IN ({','.join('?' for _ in rows)})",
            [row["user_id"] for row in rows],
        ).fetchall()
        bindings = {int(row["id"]): dict(row) for row in binding_rows}
        affiliation_rows = conn.execute(
            f"SELECT id, person_identity_id, status, valid_until, updated_at FROM person_affiliation "
            f"WHERE person_identity_id IN ({','.join('?' for _ in rows)})",
            [row["person_identity_id"] for row in rows],
        ).fetchall()
        affiliations = {int(row["id"]): dict(row) for row in affiliation_rows}
        event_ids = {int(row[0]) for row in conn.execute(
            f"SELECT id FROM identity_lifecycle_event WHERE target_user_id IN ({','.join('?' for _ in rows)})",
            [row["user_id"] for row in rows],
        ).fetchall()}
    yield
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        user_ids = [item["user_id"] for item in baseline.values()]
        person_ids = [item["person_identity_id"] for item in baseline.values()]
        student_ids = [item["student_id"] for item in baseline.values()]
        current_event_ids = {int(row[0]) for row in conn.execute(
            f"SELECT id FROM identity_lifecycle_event WHERE target_user_id IN ({','.join('?' for _ in user_ids)})",
            user_ids,
        ).fetchall()}
        new_event_ids = current_event_ids - event_ids
        if new_event_ids:
            marks = ",".join("?" for _ in new_event_ids)
            conn.execute(f"DELETE FROM account_status_history WHERE lifecycle_event_id IN ({marks})", list(new_event_ids))
            conn.execute(f"DELETE FROM identity_lifecycle_event WHERE id IN ({marks})", list(new_event_ids))
        conn.execute(
            f"DELETE FROM audit_log WHERE resource_type = 'student_lifecycle' AND resource_id IN ({','.join('?' for _ in student_ids)})",
            student_ids,
        )
        current_binding_ids = [int(row[0]) for row in conn.execute(
            f"SELECT id FROM user_role_binding WHERE user_id IN ({','.join('?' for _ in user_ids)})", user_ids
        ).fetchall()]
        extra_bindings = [binding_id for binding_id in current_binding_ids if binding_id not in bindings]
        if extra_bindings:
            marks = ",".join("?" for _ in extra_bindings)
            conn.execute(f"DELETE FROM role_scope_binding WHERE role_binding_id IN ({marks})", extra_bindings)
            conn.execute(f"DELETE FROM user_role_binding WHERE id IN ({marks})", extra_bindings)
        for row in bindings.values():
            conn.execute(
                """
                UPDATE user_role_binding
                SET status = ?, valid_until = ?, revoked_by_user_id = ?, revoked_at = ?, revoke_reason = ?
                WHERE id = ?
                """,
                (row["status"], row["valid_until"], row["revoked_by_user_id"], row["revoked_at"], row["revoke_reason"], row["id"]),
            )
        current_affiliations = [int(row[0]) for row in conn.execute(
            f"SELECT id FROM person_affiliation WHERE person_identity_id IN ({','.join('?' for _ in person_ids)})", person_ids
        ).fetchall()]
        extra_affiliations = [value for value in current_affiliations if value not in affiliations]
        if extra_affiliations:
            marks = ",".join("?" for _ in extra_affiliations)
            conn.execute(f"DELETE FROM person_affiliation WHERE id IN ({marks})", extra_affiliations)
        for row in affiliations.values():
            conn.execute("UPDATE person_affiliation SET status = ?, valid_until = ?, updated_at = ? WHERE id = ?", (row["status"], row["valid_until"], row["updated_at"], row["id"]))
        for item in baseline.values():
            conn.execute("UPDATE app_user SET status = ?, session_version = ? WHERE id = ?", (item["account_status"], item["session_version"], item["user_id"]))
            conn.execute("UPDATE student SET status = ? WHERE id = ?", (item["student_status"], item["student_id"]))
        conn.commit()


def _headers(username: str) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username)}


def test_leave_then_resume_replaces_student_business_binding_and_revokes_old_sessions():
    person_id = _identity_id("stu_zhang")
    old_token = token_for("stu_zhang")
    with TestClient(app) as client:
        leave = client.post(
            f"/api/lifecycle/students/{person_id}/student_leave",
            headers=_headers("jwc"), json={"reason": "学生已提交休学审批材料"},
        )
        assert leave.status_code == 200
        assert leave.json()["item"]["student_status"] == "leave"
        assert client.get("/api/auth/session", headers={"X-Demo-Token": old_token}).status_code == 401
        self_service = client.post("/api/auth/login", json={"username": "stu_zhang", "password": "123456"})
        assert self_service.status_code == 200
        assert self_service.json()["user"]["role"] == "self_service"

        leave_token = self_service.json()["token"]
        resume = client.post(
            f"/api/lifecycle/students/{person_id}/student_resume",
            headers=_headers("jwc"), json={"reason": "复学审批已通过，按当前学籍恢复"},
        )
        assert resume.status_code == 200
        assert resume.json()["item"]["student_status"] == "active"
        assert client.get("/api/auth/session", headers={"X-Demo-Token": leave_token}).status_code == 401
        restored = client.post("/api/auth/login", json={"username": "stu_zhang", "password": "123456"})
        assert restored.status_code == 200
        assert restored.json()["user"]["role"] == "student"

    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        statuses = [row[0] for row in conn.execute(
            "SELECT status FROM user_role_binding WHERE user_id = (SELECT id FROM app_user WHERE username = 'stu_zhang') AND role_code = 'student' ORDER BY id"
        ).fetchall()]
        affiliations = [row[0] for row in conn.execute(
            "SELECT status FROM person_affiliation WHERE person_identity_id = ? ORDER BY id", (person_id,)
        ).fetchall()]
    assert statuses[-2:] == ["suspended", "active"]
    assert affiliations[-2:] == ["leave", "active"]


def test_graduation_archives_account_and_batch_graduation_is_atomic_and_scoped():
    wang_id = _identity_id("stu_wang")
    zhao_id = _identity_id("stu_zhao")
    wang_token = token_for("stu_wang")
    with TestClient(app) as client:
        listed = client.get("/api/lifecycle/students?status=active", headers=_headers("jwc"))
        assert listed.status_code == 200
        assert {item["person_identity_id"] for item in listed.json()["items"]} >= {wang_id, zhao_id}
        denied = client.post(
            "/api/lifecycle/students/batch-graduation", headers=_headers("admin"),
            json={"person_identity_ids": [wang_id], "reason": "越权测试"},
        )
        assert denied.status_code == 403
        batch = client.post(
            "/api/lifecycle/students/batch-graduation", headers=_headers("jwc"),
            json={"person_identity_ids": [wang_id, zhao_id], "reason": "2026 届毕业审核已完成"},
        )
        assert batch.status_code == 200
        assert batch.json()["count"] == 2
        assert client.get("/api/auth/session", headers={"X-Demo-Token": wang_token}).status_code == 401
        assert client.post("/api/auth/login", json={"username": "stu_wang", "password": "123456"}).status_code == 401

    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        rows = conn.execute(
            "SELECT s.status, au.status FROM student s JOIN person_identity pi ON pi.entity_id = s.id AND pi.person_type = 'student' JOIN app_user au ON au.id = pi.user_id WHERE pi.id IN (?, ?) ORDER BY pi.id",
            (wang_id, zhao_id),
        ).fetchall()
        history_count = conn.execute(
            "SELECT count(*) FROM account_status_history WHERE user_id = (SELECT id FROM app_user WHERE username = 'stu_wang') AND to_status = 'archived'"
        ).fetchone()[0]
    assert rows == [("graduated", "archived"), ("graduated", "archived")]
    assert history_count == 1
