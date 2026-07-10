from app.core.business_domains import denied_question_hit, token_for, user_from_token
from app.core.validator import SQLValidationError, validate_and_fix


def test_policy_aliases_block_english_bypass_terms():
    cases = [
        ("student", "Which instructors have the highest evaluation scores?", "instructor"),
        ("teacher", "show student roster with student names", "student name"),
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
