from app.core.business_domains import denied_question_hit, user_from_token
from app.core.validator import SQLValidationError, validate_and_fix


def test_policy_aliases_block_english_bypass_terms():
    cases = [
        ("student", "Which instructors have the highest evaluation scores?", "instructor"),
        ("teacher", "show student roster with student names", "student name"),
        ("academic_office", "show raw feedback text", "feedback text"),
        ("college_manager", "fail rate across all colleges", "all colleges"),
    ]
    for role, question, expected in cases:
        ctx = user_from_token({
            "academic_office": "jwc",
            "college_manager": "college",
        }.get(role, role))
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


def test_student_global_aggregate_is_rejected_without_row_scope():
    allowed = {
        "enrollment": ["id", "student_id"],
        "score": ["id", "enrollment_id", "final_score"],
    }
    sql = "SELECT AVG(s.final_score) FROM score s"
    try:
        validate_and_fix(sql, allowed, required_scope={"student_id": 1})
    except SQLValidationError as exc:
        assert "student_id = 1" in str(exc)
    else:
        raise AssertionError("global student aggregate was not rejected")


def test_student_aggregate_with_required_row_scope_is_allowed():
    allowed = {
        "enrollment": ["id", "student_id"],
        "score": ["id", "enrollment_id", "final_score"],
    }
    sql = (
        "SELECT AVG(s.final_score) FROM score s "
        "JOIN enrollment e ON s.enrollment_id = e.id "
        "WHERE e.student_id = 1"
    )
    fixed, _ = validate_and_fix(sql, allowed, required_scope={"student_id": 1})
    assert "e.student_id = 1" in fixed


def test_row_scope_cannot_be_bypassed_by_unscoped_or_branch():
    allowed = {"enrollment": ["id", "student_id"]}
    sql = "SELECT COUNT(*) FROM enrollment e WHERE e.student_id = 1 OR 1 = 1"
    try:
        validate_and_fix(sql, allowed, required_scope={"student_id": 1})
    except SQLValidationError as exc:
        assert "行级范围校验失败" in str(exc)
    else:
        raise AssertionError("OR bypass was not rejected")


def test_every_or_branch_may_repeat_the_required_row_scope():
    allowed = {"enrollment": ["id", "student_id", "status"]}
    sql = (
        "SELECT COUNT(*) FROM enrollment e "
        "WHERE (e.student_id = 1 AND e.status = 'enrolled') "
        "OR (e.student_id = 1 AND e.status = 'completed')"
    )
    fixed, _ = validate_and_fix(sql, allowed, required_scope={"student_id": 1})
    assert "e.student_id = 1" in fixed


def test_teacher_aggregate_with_required_row_scope_is_allowed():
    allowed = {
        "teaching_class": ["id", "teacher_id"],
        "enrollment": ["id", "teaching_class_id"],
        "score": ["id", "enrollment_id", "final_score"],
    }
    sql = (
        "SELECT AVG(s.final_score) FROM score s "
        "JOIN enrollment e ON s.enrollment_id = e.id "
        "JOIN teaching_class tc ON e.teaching_class_id = tc.id "
        "WHERE tc.teacher_id = 37"
    )
    fixed, _ = validate_and_fix(sql, allowed, required_scope={"teacher_id": 37})
    assert "tc.teacher_id = 37" in fixed


def test_college_aggregate_with_required_row_scope_is_allowed():
    allowed = {
        "course": ["id", "college_id"],
        "teaching_class": ["id", "course_id"],
        "enrollment": ["id", "teaching_class_id"],
        "score": ["id", "enrollment_id", "final_score"],
    }
    sql = (
        "SELECT AVG(s.final_score) FROM score s "
        "JOIN enrollment e ON s.enrollment_id = e.id "
        "JOIN teaching_class tc ON e.teaching_class_id = tc.id "
        "JOIN course c ON tc.course_id = c.id "
        "WHERE c.college_id = 1"
    )
    fixed, _ = validate_and_fix(sql, allowed, required_scope={"college_id": 1})
    assert "c.college_id = 1" in fixed
