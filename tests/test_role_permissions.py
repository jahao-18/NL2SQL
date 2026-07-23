from app.core.business_domains import denied_question_hit, filter_schema_info, token_for, user_from_token
from app.core.schema import SchemaInfo, load_schema
from app.core.validator import SQLValidationError, validate_and_fix


def test_policy_aliases_block_english_bypass_terms():
    cases = [
        ("student", "Which instructors have the highest evaluation scores?", "instructor"),
        ("student", "show other student roster with student names", "student name"),
        ("academic_office", "show raw feedback text", "feedback text"),
        ("college_manager", "fail rate across all colleges", "all colleges"),
    ]
    for role, question, expected in cases:
        username = {
            "academic_office": "jwc",
            "college_manager": "college",
        }.get(role, role)
        ctx = user_from_token(token_for(username))
        assert denied_question_hit(question, ctx.denied_terms) == expected


def test_teacher_can_request_names_in_own_roster_but_internal_ids_stay_blocked():
    ctx = user_from_token(token_for("tea_li"))
    assert denied_question_hit("哪些同学还没完成作业", ctx.denied_terms) is None
    assert "student.name" not in ctx.denied_columns
    assert "student.id" in ctx.denied_columns
    assert "assignment_submission.student_id" in ctx.denied_columns


def test_role_schema_keeps_blocked_join_keys_but_hides_non_key_sensitive_fields():
    ddl = """CREATE TABLE student (
 id INTEGER,
 name TEXT,
 student_no TEXT
);
CREATE TABLE assignment_submission (
 id INTEGER,
 student_id INTEGER
);"""
    info = SchemaInfo(
        ddl_text=ddl,
        pure_ddl=ddl,
        tables={"student": ["id", "name", "student_no"], "assignment_submission": ["id", "student_id"]},
        columns={},
    )
    filtered = filter_schema_info(
        info,
        {"student", "assignment_submission"},
        {"student.id", "student.name", "student.student_no", "assignment_submission.student_id"},
    )
    assert "student.id" in filtered.blocked_columns
    assert "assignment_submission.student_id" in filtered.blocked_columns
    assert "仅允许用于 JOIN/WHERE" in filtered.ddl_text
    assert "student.name" not in filtered.ddl_text
    assert "student.student_no" not in filtered.ddl_text


def test_teacher_missing_assignment_roster_sql_is_valid_when_scoped_to_own_classes():
    ctx = user_from_token(token_for("tea_li"))
    schema = filter_schema_info(load_schema("teaching"), ctx.allowed_tables, ctx.denied_columns)
    sql = f"""SELECT s.name AS student_name, a.title AS assignment_title
FROM assignment_submission sub
JOIN assignment a ON sub.assignment_id = a.id
JOIN teaching_class tc ON a.teaching_class_id = tc.id
JOIN student s ON sub.student_id = s.id
WHERE sub.status = 'missing' AND tc.teacher_id = {ctx.row_scope['teacher_id']}"""
    fixed, _ = validate_and_fix(sql, schema.tables, schema.blocked_columns, row_scope=ctx.row_scope)
    assert "s.name AS student_name" in fixed
    assert f"tc.teacher_id = {ctx.row_scope['teacher_id']}" in fixed


def test_joined_unauthorized_table_is_rejected():
    sql = (
        "SELECT t.name, AVG(e.score) "
        "FROM evaluation e "
        "JOIN teaching_class tc ON e.teaching_class_id = tc.id "
        "JOIN teacher t ON tc.teacher_id = t.id "
        "GROUP BY t.name LIMIT 10"
    )
    allowed = {
        "course": ["id"],
        "teaching_class": ["id", "course_id"],
        "enrollment": ["id"],
        "score": ["id"],
        "evaluation": ["id", "teaching_class_id", "score"],
    }
    try:
        validate_and_fix(sql, allowed)
    except SQLValidationError as exc:
        assert "teacher" in str(exc)
    else:
        raise AssertionError("unauthorized JOIN table was not rejected")


def test_denied_column_is_rejected_even_when_table_allowed():
    sql = "SELECT tc.teacher_id FROM teaching_class tc LIMIT 10"
    allowed = {"teaching_class": ["id", "course_id", "teacher_id"]}
    try:
        validate_and_fix(sql, allowed, {"teaching_class.teacher_id"})
    except SQLValidationError as exc:
        assert "teaching_class.teacher_id" in str(exc)
    else:
        raise AssertionError("denied column was not rejected")


def test_denied_column_can_be_used_for_scope_filter_but_not_output():
    allowed = {
        "enrollment": ["id", "student_id", "teaching_class_id"],
        "teaching_class": ["id", "course_id", "year", "semester"],
        "course": ["id", "name"],
    }
    blocked = {"student.id", "student.name", "student.student_no"}
    sql = (
        "SELECT c.name "
        "FROM enrollment e "
        "JOIN teaching_class tc ON e.teaching_class_id = tc.id "
        "JOIN course c ON tc.course_id = c.id "
        "WHERE e.student_id = 1 AND tc.year = 2025 LIMIT 10"
    )
    fixed, _ = validate_and_fix(sql, allowed, blocked)
    assert "e.student_id = 1" in fixed


def test_select_star_is_rejected_when_table_has_blocked_output_columns():
    try:
        validate_and_fix("SELECT * FROM student LIMIT 10", {"student": ["id", "name"]}, {"student.name"})
    except SQLValidationError as exc:
        assert "student.name" in str(exc)
    else:
        raise AssertionError("SELECT * over blocked output columns was not rejected")
