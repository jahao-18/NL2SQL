from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.business_domains import (
    AuthenticationError,
    AuthorizationError,
    auth_context,
    require_admin,
    token_for,
    user_from_token,
)
from app.api import routes as api_routes
from app.core.config import ROOT_DIR, settings
from app.core.data_sources import _normalized_sqlite_url, load_sources
from app.core.schema import SchemaInfo
from app.core.business_domains import filter_schema_info
from app.core.schema_profile import _version_yaml_path
from app.core.validator import SQLValidationError, validate_and_fix
from app.main import app


def test_signed_demo_token_rejects_missing_and_forged_values():
    with pytest.raises(AuthenticationError):
        user_from_token(None)
    with pytest.raises(AuthenticationError):
        user_from_token("admin")
    with pytest.raises(AuthenticationError):
        user_from_token("YWRtaW4.invalid")
    assert user_from_token(token_for("student")).username == "student"


def test_admin_guard_rejects_non_admin_role():
    assert require_admin(token_for("admin")).is_admin
    with pytest.raises(AuthorizationError):
        require_admin(token_for("teacher"))


def test_auth_api_requires_login_and_accepts_login_token():
    with TestClient(app) as client:
        assert client.get("/api/auth/session").status_code == 401
        login = client.post("/api/auth/login", json={"username": "student", "password": "123456"})
        assert login.status_code == 200
        token = login.json()["token"]
        session = client.get("/api/auth/session", headers={"X-Demo-Token": token})
        assert session.status_code == 200
        assert session.json()["user"]["username"] == "student"


def test_profile_write_requires_admin():
    with TestClient(app) as client:
        response = client.put(
            "/api/profile?source=teaching",
            headers={"X-Demo-Token": token_for("student")},
            json={"profile": {}},
        )
        assert response.status_code == 403


def test_version_id_blocks_path_traversal():
    with pytest.raises(ValueError, match="非法版本号"):
        _version_yaml_path("teaching", r"..\..\teaching")


@pytest.mark.parametrize(
    ("sql", "scope"),
    [
        ("SELECT COUNT(*) FROM enrollment", {"student_id": 1}),
        ("SELECT COUNT(*) FROM teaching_class", {"teacher_id": 37}),
        ("SELECT COUNT(*) FROM student", {"college_id": 1}),
    ],
)
def test_row_scope_rejects_queries_without_required_predicate(sql, scope):
    allowed = {
        "enrollment": ["id", "student_id"],
        "teaching_class": ["id", "teacher_id"],
        "student": ["id", "college_id"],
    }
    with pytest.raises(SQLValidationError, match="必须限定"):
        validate_and_fix(sql, allowed, row_scope=scope)


@pytest.mark.parametrize(
    ("sql", "scope"),
    [
        ("SELECT COUNT(*) FROM enrollment e WHERE e.student_id = 1", {"student_id": 1}),
        ("SELECT COUNT(*) FROM teaching_class tc WHERE tc.teacher_id = 37", {"teacher_id": 37}),
        ("SELECT COUNT(*) FROM student s WHERE s.college_id = 1", {"college_id": 1}),
    ],
)
def test_row_scope_accepts_matching_predicate(sql, scope):
    allowed = {
        "enrollment": ["id", "student_id"],
        "teaching_class": ["id", "teacher_id"],
        "student": ["id", "college_id"],
    }
    fixed, _ = validate_and_fix(sql, allowed, row_scope=scope)
    assert fixed.endswith(f"LIMIT {settings.max_rows}")


def test_relative_sqlite_url_is_rooted_at_project_directory():
    normalized = _normalized_sqlite_url("sqlite:///data/teaching.db")
    assert (ROOT_DIR / "data" / "teaching.db").resolve().as_posix() in normalized


def test_default_runtime_registry_only_connects_teaching_database():
    assert list(load_sources()) == ["teaching"]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) FROM enrollment e WHERE e.student_id = 1 OR 1 = 1",
        "SELECT 'e.student_id = 1' AS fake_scope, COUNT(*) FROM enrollment e",
        "SELECT COUNT(*) FROM enrollment e WHERE 1 = 1 -- e.student_id = 1",
        "SELECT (SELECT COUNT(*) FROM enrollment) FROM enrollment e WHERE e.student_id = 1",
        "SELECT COUNT(*) FROM enrollment e WHERE e.student_id = 1 UNION SELECT COUNT(*) FROM enrollment",
        "SELECT COUNT(*) FROM enrollment e WHERE NOT (e.student_id = 1)",
        "SELECT COUNT(*) FROM enrollment e WHERE (e.student_id = 1) = 0",
        "SELECT COUNT(*) FROM enrollment e WHERE CASE WHEN e.student_id = 1 THEN 1 ELSE 1 END = 1",
    ],
)
def test_row_scope_rejects_boolean_comment_literal_subquery_and_union_bypasses(sql: str):
    with pytest.raises(SQLValidationError):
        validate_and_fix(sql, {"enrollment": ["id", "student_id"]}, row_scope={"student_id": 1})


def test_every_nested_query_block_must_repeat_its_row_scope():
    sql = (
        "SELECT (SELECT COUNT(*) FROM enrollment inner_e WHERE inner_e.student_id = 1) AS own_count "
        "FROM enrollment outer_e WHERE outer_e.student_id = 1"
    )
    fixed, _ = validate_and_fix(sql, {"enrollment": ["id", "student_id"]}, row_scope={"student_id": 1})
    assert fixed.endswith(f"LIMIT {settings.max_rows}")


def test_teacher_college_and_counselor_scope_rules_cover_previously_unprotected_tables():
    allowed = {
        "score": ["id", "enrollment_id"],
        "enrollment": ["id", "teaching_class_id"],
        "teaching_class": ["id", "teacher_id"],
    }
    with pytest.raises(SQLValidationError, match="teacher_id"):
        validate_and_fix(
            "SELECT AVG(s.id) FROM score s JOIN enrollment e ON e.id=s.enrollment_id JOIN teaching_class tc ON tc.id=e.teaching_class_id",
            allowed,
            row_scope={"teacher_id": 37},
        )
    fixed, _ = validate_and_fix(
        "SELECT AVG(s.id) FROM score s JOIN enrollment e ON e.id=s.enrollment_id JOIN teaching_class tc ON tc.id=e.teaching_class_id WHERE tc.teacher_id=37",
        allowed,
        row_scope={"teacher_id": 37},
    )
    assert "teacher_id=37" in fixed

    with pytest.raises(SQLValidationError, match="college_id"):
        validate_and_fix(
            "SELECT COUNT(*) FROM academic_teaching_operations_summary",
            {"academic_teaching_operations_summary": ["college_id"]},
            row_scope={"college_id": 1},
        )

    counselor_tables = {
        "student": ["id", "class_id"],
        "counselor_class_group": ["counselor_id", "class_group_id"],
    }
    with pytest.raises(SQLValidationError, match="counselor_id"):
        validate_and_fix("SELECT COUNT(*) FROM student", counselor_tables, row_scope={"counselor_id": 900001, "college_id": 1})
    scoped, _ = validate_and_fix(
        "SELECT COUNT(*) FROM student s JOIN counselor_class_group ccg ON ccg.class_group_id=s.class_id WHERE ccg.counselor_id=900001",
        counselor_tables,
        row_scope={"counselor_id": 900001, "college_id": 1},
    )
    assert "ccg.counselor_id=900001" in scoped


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT load_extension('evil')",
        "SELECT readfile('/etc/passwd')",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT SLEEP(10)",
        "SELECT 'x' INTO OUTFILE '/tmp/result'",
    ],
)
def test_dangerous_read_functions_and_file_output_are_rejected(sql: str):
    with pytest.raises(SQLValidationError, match="禁用"):
        validate_and_fix(sql, {})


def test_non_admin_ask_is_locked_to_teaching_source_and_no_ask_role_is_denied(monkeypatch: pytest.MonkeyPatch):
    with TestClient(app) as client:
        sources = client.get("/api/sources", headers={"X-Demo-Token": token_for("stu_zhang")})
        assert sources.status_code == 200
        assert [item["name"] for item in sources.json()["sources"]] == ["teaching"]
        denied = client.post(
            "/api/ask",
            headers={"X-Demo-Token": token_for("stu_zhang")},
            json={"question": "查询数据", "source": "student_club"},
        )
        assert denied.status_code == 403

    staff = auth_context({"id": 999999, "username": "staff-test", "display_name": "职工", "role": "staff", "scope": {}})
    monkeypatch.setattr(api_routes, "user_from_token", lambda _token: staff)
    with TestClient(app) as client:
        assert client.get("/api/sources", headers={"X-Demo-Token": "test"}).status_code == 403
        assert client.post("/api/ask", headers={"X-Demo-Token": "test"}, json={"question": "查询数据"}).status_code == 403


def test_ask_request_limits_history_and_glossary_item_size():
    headers = {"X-Demo-Token": token_for("stu_zhang")}
    with TestClient(app) as client:
        too_many_turns = client.post(
            "/api/ask",
            headers=headers,
            json={"question": "查询我的课程", "history": [{"question": "q", "sql": "SELECT 1"}] * 21},
        )
        assert too_many_turns.status_code == 422
        huge_glossary = client.post(
            "/api/ask",
            headers=headers,
            json={"question": "查询我的课程", "user_glossary": ["x" * 501]},
        )
        assert huge_glossary.status_code == 422


def test_empty_table_permission_filters_to_zero_tables_instead_of_all_tables():
    info = SchemaInfo(
        ddl_text="CREATE TABLE secret (id INTEGER);",
        pure_ddl="CREATE TABLE secret (id INTEGER);",
        tables={"secret": ["id"]},
        columns={"secret": [{"column_name": "id"}]},
    )
    filtered = filter_schema_info(info, set())
    assert filtered.tables == {}
    assert filtered.columns == {}
    assert filtered.pure_ddl == ""


@pytest.mark.parametrize(
    "sql",
    [
        "WITH leaked AS (SELECT s.name AS n FROM student s) SELECT n FROM leaked",
        "SELECT (SELECT s.name FROM student s LIMIT 1) AS leaked_name",
        "SELECT leaked.n FROM (SELECT s.name AS n FROM student s) leaked",
        "SELECT name FROM student",
        'SELECT s."name" FROM student AS s',
        'SELECT "student"."name" FROM "student"',
    ],
)
def test_blocked_columns_cannot_be_hidden_in_cte_or_subquery(sql: str):
    with pytest.raises(SQLValidationError, match="不可用于问数"):
        validate_and_fix(sql, {"student": ["id", "name"]}, {"student.name"})
