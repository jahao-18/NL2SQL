from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.business_domains import login, token_for, user_from_token
from app.core.teaching_migrations import ensure_mvp_schema
from app.main import app


def test_mvp_demo_accounts_login_and_bind_real_scopes():
    ensure_mvp_schema()

    student = login("stu_zhang", "123456")
    teacher = login("tea_li", "123456")
    counselor = login("counselor_chen", "123456")

    assert student.row_scope["student_id"] == 900001
    assert teacher.row_scope["teacher_id"] == 900001
    assert counselor.row_scope["counselor_id"] == 900001


def test_expiring_signed_token_still_authenticates_current_demo_user():
    ctx = user_from_token(token_for("stu_zhang"))
    assert ctx.username == "stu_zhang"
    assert ctx.row_scope["student_id"] == 900001


def test_teacher_analysis_scope_no_longer_includes_academic_warning():
    ctx = user_from_token(token_for("tea_li"))
    assert "academic_warning" not in ctx.allowed_tables


def test_student_can_read_own_class_but_not_other_student_submission():
    with TestClient(app) as client:
        token = token_for("stu_zhang")

        own_class = client.get("/api/teaching/classes/900001", headers={"X-Demo-Token": token})
        assert own_class.status_code == 200
        assert own_class.json()["item"]["course_name"] == "数据库系统"

        other_submission = client.get("/api/teaching/submissions/900003", headers={"X-Demo-Token": token})
        assert other_submission.status_code == 403

        other_class = client.get("/api/teaching/classes/900002", headers={"X-Demo-Token": token})
        assert other_class.status_code == 403


def test_teacher_can_read_own_class_submissions_but_not_other_teacher_class():
    with TestClient(app) as client:
        token = token_for("tea_li")

        own = client.get("/api/teaching/classes/900001/submissions", headers={"X-Demo-Token": token})
        assert own.status_code == 200
        assert {item["student_id"] for item in own.json()["items"]} >= {900001, 900002, 900003, 900004}

        other = client.get("/api/teaching/classes/900002/submissions", headers={"X-Demo-Token": token})
        assert other.status_code == 403


def test_counselor_can_read_own_support_case_but_not_other_scope_or_teacher_records():
    with TestClient(app) as client:
        counselor = token_for("counselor_chen")
        other_counselor = token_for("counselor_lin")
        teacher = token_for("tea_li")

        own = client.get("/api/teaching/support/cases/900001", headers={"X-Demo-Token": counselor})
        assert own.status_code == 200
        assert own.json()["item"]["student_id"] == 900002

        outside = client.get("/api/teaching/support/cases/900001", headers={"X-Demo-Token": other_counselor})
        assert outside.status_code == 403

        teacher_access = client.get("/api/teaching/support/cases/900001", headers={"X-Demo-Token": teacher})
        assert teacher_access.status_code == 403
