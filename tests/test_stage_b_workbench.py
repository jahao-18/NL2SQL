from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.core.business_domains import DEMO_USERS, auth_context, token_for
from app.core.config import STATIC_DIR
from app.core.workbench import build_workbench
from app.main import app


ROLE_USERS = {
    "admin": "admin",
    "academic_office": "jwc",
    "college_manager": "college",
    "teacher": "tea_li",
    "counselor": "counselor_chen",
    "student": "stu_zhang",
}


def _headers(username: str) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username)}


def _workbench(username: str) -> dict:
    with TestClient(app) as client:
        response = client.get("/api/workbench", headers=_headers(username))
    assert response.status_code == 200
    return response.json()


def test_workbench_requires_login():
    with TestClient(app) as client:
        response = client.get("/api/workbench")
    assert response.status_code == 401


def test_legacy_schoolwide_dashboard_is_admin_only():
    with TestClient(app) as client:
        denied = client.get("/api/teaching/dashboard", headers=_headers("stu_zhang"))
        allowed = client.get("/api/teaching/dashboard", headers=_headers("admin"))
    assert denied.status_code == 403
    assert allowed.status_code == 200


@pytest.mark.parametrize(("role", "username"), ROLE_USERS.items())
def test_six_roles_have_distinct_actionable_workbenches(role: str, username: str):
    data = _workbench(username)
    assert data["role"] == role
    assert data["title"]
    assert data["summary"]
    assert data["sections"]
    assert data["quick_actions"]
    assert all(section["items"] for section in data["sections"])
    assert all(action.get("target") for action in data["quick_actions"])


def test_role_home_titles_and_sections_are_not_the_old_shared_dashboard():
    payloads = [_workbench(username) for username in ROLE_USERS.values()]
    assert len({item["title"] for item in payloads}) == 6
    assert len({tuple(section["type"] for section in item["sections"]) for item in payloads}) == 6
    assert all(item["title"] != "教学数据总览" for item in payloads)


def test_every_demo_account_has_deterministic_home_data():
    for username, user in DEMO_USERS.items():
        data = build_workbench(auth_context(user))
        assert data["sections"], username
        assert all(section["items"] for section in data["sections"]), username
        assert data["quick_actions"], username


def test_student_workbench_only_contains_own_course_assignments_and_grades():
    data = _workbench("stu_zhang")
    assignment_ids = {
        int(item["id"])
        for section in data["sections"]
        if section["type"] in {"pending_assignments", "published_grades"}
        for item in section["items"]
    }
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        allowed = {
            row[0]
            for row in conn.execute("""
                SELECT a.id FROM assignment a
                JOIN enrollment e ON e.teaching_class_id = a.teaching_class_id
                WHERE e.student_id = 900001
            """)
        }
    assert assignment_ids <= allowed


def test_teacher_and_college_workbench_items_stay_inside_server_side_scope():
    teacher = _workbench("tea_li")
    teacher_class_ids = {
        int(item["id"])
        for section in teacher["sections"] if section["type"] == "teaching_classes"
        for item in section["items"]
    }
    college = _workbench("college")
    college_class_ids = {
        int(item["id"])
        for section in college["sections"] if section["type"] in {"college_teaching_issues", "college_course_operations"}
        for item in section["items"]
    }
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        assert teacher_class_ids
        assert not conn.execute(
            f"SELECT 1 FROM teaching_class WHERE id IN ({','.join('?' for _ in teacher_class_ids)}) AND teacher_id <> 900001 LIMIT 1",
            tuple(teacher_class_ids),
        ).fetchone()
        assert college_class_ids
        assert not conn.execute(
            f"""SELECT 1 FROM teaching_class tc JOIN course c ON c.id = tc.course_id
                WHERE tc.id IN ({','.join('?' for _ in college_class_ids)}) AND c.college_id <> 1 LIMIT 1""",
            tuple(college_class_ids),
        ).fetchone()


def test_counselor_workbench_only_contains_assigned_students():
    data = _workbench("counselor_chen")
    case_ids = {
        int(item["id"])
        for section in data["sections"] if section["type"] == "support_followups"
        for item in section["items"]
    }
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        assert case_ids
        assert not conn.execute(
            f"""SELECT 1 FROM support_case sc JOIN student s ON s.id = sc.student_id
                LEFT JOIN counselor_class_group ccg
                  ON ccg.class_group_id = s.class_id AND ccg.counselor_id = 900001
                WHERE sc.id IN ({','.join('?' for _ in case_ids)})
                  AND (sc.counselor_id <> 900001 OR ccg.class_group_id IS NULL) LIMIT 1""",
            tuple(case_ids),
        ).fetchone()


def test_frontend_uses_dynamic_section_container_and_suppresses_empty_sections():
    html = Path(STATIC_DIR / "index.html").read_text(encoding="utf-8")
    js = Path(STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert 'id="workbench-sections"' in html
    assert 'class="dashboard-grid hidden"' in html
    assert "api.workbench()" in js
    assert "if (!items.length) return;" in js
    assert "data-section-type" not in html
