import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "teaching.db"
client = TestClient(app)


def _get(token: str | None, **params):
    headers = {"X-Demo-Token": token} if token else {}
    return client.get("/api/teaching/dashboard", headers=headers, params=params)


def _one(sql: str, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(sql, params).fetchone()[0]


@pytest.mark.parametrize("token", [None, "not-a-real-user"])
def test_dashboard_requires_valid_token(token):
    response = _get(token)
    assert response.status_code == 401
    assert response.json() == {"detail": "未登录或令牌无效"}


@pytest.mark.parametrize(
    ("token", "role"),
    [
        ("admin", "admin"),
        ("jwc", "academic_office"),
        ("college", "college_manager"),
        ("teacher", "teacher"),
        ("student", "student"),
    ],
)
def test_dashboard_returns_the_authenticated_role(token, role):
    response = _get(token)
    assert response.status_code == 200
    assert response.json()["permission"]["role"] == role


def test_scoped_baseline_cards_match_independent_database_queries():
    college = _get("college").json()["cards"]
    teacher = _get("teacher").json()["cards"]
    student = _get("student").json()["cards"]

    assert college["active_students"] == _one(
        "SELECT COUNT(*) FROM student WHERE status = 'active' AND college_id = 1"
    )
    assert teacher["current_classes"] == _one(
        "SELECT COUNT(*) FROM teaching_class WHERE teacher_id = 37"
    )
    assert student["current_classes"] == _one(
        "SELECT COUNT(DISTINCT teaching_class_id) FROM enrollment WHERE student_id = 1"
    )


@pytest.mark.parametrize(
    ("token", "scope_sql", "scope_params"),
    [
        (
            "student",
            "SELECT COUNT(DISTINCT tc.id) FROM enrollment e "
            "JOIN teaching_class tc ON e.teaching_class_id = tc.id "
            "WHERE e.student_id = 1 AND tc.year = 2025 AND tc.semester = 'spring'",
            (),
        ),
        (
            "teacher",
            "SELECT COUNT(*) FROM teaching_class "
            "WHERE teacher_id = 37 AND year = 2025 AND semester = 'spring'",
            (),
        ),
        (
            "college",
            "SELECT COUNT(DISTINCT tc.id) FROM teaching_class tc "
            "JOIN course c ON tc.course_id = c.id "
            "WHERE c.college_id = 1 AND tc.year = 2025 AND tc.semester = 'spring'",
            (),
        ),
    ],
)
def test_term_filter_changes_scoped_results_and_matches_database(token, scope_sql, scope_params):
    baseline = _get(token).json()["cards"]["current_classes"]
    response = _get(token, term="2025-spring")
    assert response.status_code == 200
    body = response.json()
    assert body["filters"]["term"] == "2025-spring"
    assert body["cards"]["current_classes"] == _one(scope_sql, scope_params)
    assert body["cards"]["current_classes"] < baseline


@pytest.mark.parametrize(
    ("token", "expected_sql"),
    [
        (
            "student",
            "SELECT COUNT(DISTINCT c.id) FROM enrollment e "
            "JOIN teaching_class tc ON e.teaching_class_id = tc.id "
            "JOIN course c ON tc.course_id = c.id "
            "WHERE e.student_id = 1 AND c.course_type = 'required'",
        ),
        (
            "teacher",
            "SELECT COUNT(DISTINCT c.id) FROM teaching_class tc "
            "JOIN course c ON tc.course_id = c.id "
            "WHERE tc.teacher_id = 37 AND c.course_type = 'required'",
        ),
        (
            "college",
            "SELECT COUNT(*) FROM course WHERE college_id = 1 AND course_type = 'required'",
        ),
    ],
)
def test_course_type_filter_matches_each_scoped_role(token, expected_sql):
    response = _get(token, course_type="required")
    assert response.status_code == 200
    body = response.json()
    assert body["filters"]["course_type"] == "required"
    assert body["cards"]["course_count"] == _one(expected_sql)


@pytest.mark.parametrize(
    ("token", "allowed_sql"),
    [
        (
            "student",
            "SELECT DISTINCT c.name FROM enrollment e "
            "JOIN teaching_class tc ON e.teaching_class_id = tc.id "
            "JOIN course c ON tc.course_id = c.id "
            "WHERE e.student_id = 1 AND c.course_type = 'required'",
        ),
        (
            "teacher",
            "SELECT DISTINCT c.name FROM teaching_class tc "
            "JOIN course c ON tc.course_id = c.id "
            "WHERE tc.teacher_id = 37 AND c.course_type = 'required'",
        ),
    ],
)
def test_course_type_filter_does_not_expand_student_or_teacher_scope(token, allowed_sql):
    body = _get(token, course_type="required").json()
    with sqlite3.connect(DB_PATH) as conn:
        allowed_names = {row[0] for row in conn.execute(allowed_sql)}
    returned_names = {
        item["course_name"]
        for key in ("low_score_courses", "fail_rate_courses", "attendance_risk_courses")
        for item in body[key]
    }
    assert returned_names <= allowed_names


def test_college_major_filter_stays_inside_bound_college():
    response = _get("college", major="软件工程")
    assert response.status_code == 200
    body = response.json()
    expected = _one(
        "SELECT COUNT(*) FROM student s JOIN major m ON s.major_id = m.id "
        "WHERE s.status = 'active' AND s.college_id = 1 AND m.name = '软件工程'"
    )
    assert body["cards"]["active_students"] == expected
    assert {item["major_name"] for item in body["warning_by_major"]} <= {"软件工程"}
    assert {item["label"] for item in body["students_by_college"]} <= {"计算机学院"}


@pytest.mark.parametrize(
    ("token", "params", "detail"),
    [
        ("student", {"college": "计算机学院"}, "filters not supported for this role: college"),
        ("teacher", {"major": "软件工程"}, "filters not supported for this role: major"),
        ("college", {"college": "计算机学院"}, "college filter is fixed by the current account scope"),
        ("student", {"term": "bad-format"}, "term must use the YYYY-semester format"),
    ],
)
def test_scoped_roles_reject_unsupported_or_malformed_filters(token, params, detail):
    response = _get(token, **params)
    assert response.status_code == 400
    assert response.json() == {"detail": detail}


@pytest.mark.parametrize("token", ["college", "teacher", "student"])
def test_impossible_term_returns_empty_scoped_class_statistics(token):
    response = _get(token, term="1900-spring")
    assert response.status_code == 200
    cards = response.json()["cards"]
    assert cards["current_classes"] == 0
    assert cards["current_enrollments"] == 0


def test_unrestricted_term_filter_keeps_existing_behavior():
    response = _get("admin", term="2025-spring")
    assert response.status_code == 200
    cards = response.json()["cards"]
    assert cards["current_classes"] == _one(
        "SELECT COUNT(*) FROM teaching_class WHERE year = 2025 AND semester = 'spring'"
    )
    assert cards["current_enrollments"] == _one(
        "SELECT COUNT(e.id) FROM enrollment e JOIN teaching_class tc ON e.teaching_class_id = tc.id "
        "WHERE tc.year = 2025 AND tc.semester = 'spring'"
    )


@pytest.mark.parametrize("token", ["admin", "jwc"])
def test_unrestricted_college_filter_counts_classes_owned_by_course_college(token):
    response = _get(token, term="2025-spring", college="计算机学院")
    assert response.status_code == 200
    body = response.json()
    assert body["filters"] == {
        "term": "2025-spring",
        "college": "计算机学院",
        "major": "",
        "course_type": "",
    }
    assert body["cards"]["current_classes"] == _one(
        "SELECT COUNT(DISTINCT tc.id) FROM teaching_class tc "
        "JOIN course c ON tc.course_id = c.id "
        "JOIN college co ON c.college_id = co.id "
        "WHERE tc.year = 2025 AND tc.semester = 'spring' AND co.name = '计算机学院'"
    )


def test_filter_options_follow_role_scope():
    college = _get("college").json()["filter_options"]
    teacher = _get("teacher").json()["filter_options"]
    student = _get("student").json()["filter_options"]

    assert college["colleges"] == ["计算机学院"]
    assert {item["college"] for item in college["majors"]} <= {"计算机学院"}
    assert teacher["colleges"] == [] and teacher["majors"] == []
    assert student["colleges"] == [] and student["majors"] == []
