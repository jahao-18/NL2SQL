from __future__ import annotations

import pytest

from app.core.assignment_workflow import list_my_assignments
from app.core.business_domains import AuthorizationError, login
from app.core.course_analytics import ask_course, course_summary, query_history, save_query_feedback
from app.core.teaching_migrations import ensure_mvp_schema
from app.core.validator import SQLValidationError, validate_and_fix


@pytest.fixture(autouse=True)
def _schema_and_log_cleanup():
    ensure_mvp_schema()
    yield
    from app.core.authorization import connect
    with connect() as conn:
        conn.execute("DELETE FROM analytics_query_log WHERE question LIKE '测试阶段四%'")
        conn.commit()


def test_teacher_summary_is_limited_to_own_teaching_class():
    teacher = login("tea_li", "123456")
    summary = course_summary(teacher, 900001)

    assert summary["role"] == "teacher"
    assert summary["scope"]["teacher_id"] == 900001
    assert summary["items"]
    assert {item["teaching_class_id"] for item in summary["items"]} == {900001}

    with pytest.raises(AuthorizationError):
        course_summary(teacher, 900002)


def test_student_summary_contains_only_self_and_published_scores():
    student = login("stu_zhang", "123456")
    summary = course_summary(student, 900001)

    assert summary["role"] == "student"
    assert summary["scope"]["student_id"] == 900001
    assert summary["items"]
    assert {item["student_id"] for item in summary["items"]} == {900001}
    assert all("feedback" not in item and "file_name" not in item for item in summary["items"])


def test_context_template_query_is_scoped_and_logged():
    teacher = login("tea_li", "123456")
    result = ask_course(teacher, 900001, "测试阶段四：本班各作业未交情况")

    assert result["query_mode"] == "context_template"
    assert "teaching_class_id = 900001" in result["sql"]
    assert "teacher_id = 900001" in result["sql"]
    history = query_history(teacher, 900001)
    assert history[0]["question"].startswith("测试阶段四")
    assert history[0]["status"] == "success"
    save_query_feedback(teacher, result["query_log_id"], "helpful")
    assert query_history(teacher, 900001)[0]["user_feedback"] == "helpful"


def test_analytics_validator_requires_class_and_identity_scope():
    tables = {"student_task_analytics": ["teaching_class_id", "student_id", "assignment_title"]}
    with pytest.raises(SQLValidationError):
        validate_and_fix(
            "SELECT assignment_title FROM student_task_analytics WHERE student_id = 900001",
            tables,
            row_scope={"student_id": 900001, "teaching_class_id": 900001},
        )
    sql, _ = validate_and_fix(
        "SELECT assignment_title FROM student_task_analytics WHERE student_id = 900001 AND teaching_class_id = 900001",
        tables,
        row_scope={"student_id": 900001, "teaching_class_id": 900001},
    )
    assert "LIMIT" in sql


def test_nl2sql_failure_does_not_break_assignment_workflow(monkeypatch):
    student = login("stu_zhang", "123456")
    monkeypatch.setattr(
        "app.core.course_analytics.ask_service",
        lambda **_: {"sql": None, "rows": [], "columns": [], "row_count": 0, "error": "测试问数服务不可用"},
    )

    result = ask_course(student, 900001, "测试阶段四：按截止日期分析个人进度")
    assignments = list_my_assignments(student)

    assert result["error"] == "测试问数服务不可用"
    assert assignments
