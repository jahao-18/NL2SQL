from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from app.core import teaching_migrations
from app.core.assistant_context import (
    AssistantContextAuthorizationError,
    AssistantPageContext,
    resolve_assistant_context,
)
from app.core.business_domains import switch_role, token_for, user_from_token


def _auth(username: str):
    return user_from_token(token_for(username))


def test_teacher_can_use_own_course_and_context_only_narrows_auth():
    auth = _auth("tea_li")
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        class_id = conn.execute(
            "SELECT id FROM teaching_class WHERE teacher_id = ? ORDER BY id LIMIT 1",
            (auth.row_scope["teacher_id"],),
        ).fetchone()[0]
    resolved = resolve_assistant_context(
        auth,
        AssistantPageContext(
            page="course_analytics",
            teaching_class_id=class_id,
            academic_year=2025,
            semester="SPRING",
        ),
    )
    assert resolved.auth_context is auth
    assert resolved.effective_context["teaching_class_id"] == class_id
    assert resolved.effective_context["semester"] == "spring"
    assert resolved.rejected_fields == {}
    assert resolved.auth_context.allowed_tables == auth.allowed_tables


def test_teacher_cannot_forge_another_teachers_course():
    auth = _auth("tea_li")
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        class_id = conn.execute(
            "SELECT id FROM teaching_class WHERE teacher_id <> ? ORDER BY id LIMIT 1",
            (auth.row_scope["teacher_id"],),
        ).fetchone()[0]
    with pytest.raises(AssistantContextAuthorizationError) as raised:
        resolve_assistant_context(
            auth, {"page": "course_space", "teaching_class_id": class_id}
        )
    assert raised.value.rejected_fields == {"teaching_class_id": class_id}


def test_student_cannot_forge_another_student_id():
    auth = _auth("stu_zhang")
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        other_id = conn.execute(
            "SELECT id FROM student WHERE id <> ? ORDER BY id LIMIT 1",
            (auth.row_scope["student_id"],),
        ).fetchone()[0]
    with pytest.raises(AssistantContextAuthorizationError) as raised:
        resolve_assistant_context(
            auth, {"page": "assignment_workflow", "student_id": other_id}
        )
    assert raised.value.rejected_fields == {"student_id": other_id}


def test_counselor_cannot_forge_student_outside_assigned_classes():
    auth = _auth("counselor_chen")
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        student_id = conn.execute(
            """
            SELECT s.id FROM student s
            WHERE NOT EXISTS (
                SELECT 1 FROM counselor_class_group ccg
                WHERE ccg.counselor_id = ? AND ccg.class_group_id = s.class_id
            ) ORDER BY s.id LIMIT 1
            """,
            (auth.row_scope["counselor_id"],),
        ).fetchone()[0]
    with pytest.raises(AssistantContextAuthorizationError) as raised:
        resolve_assistant_context(
            auth, {"page": "support_workbench", "student_id": student_id}
        )
    assert raised.value.rejected_fields == {"student_id": student_id}


def test_college_manager_cannot_forge_another_college():
    auth = _auth("college")
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        other_id = conn.execute(
            "SELECT id FROM college WHERE id <> ? ORDER BY id LIMIT 1",
            (auth.row_scope["college_id"],),
        ).fetchone()[0]
    with pytest.raises(AssistantContextAuthorizationError) as raised:
        resolve_assistant_context(
            auth, {"page": "teaching_operations", "college_id": other_id}
        )
    assert raised.value.rejected_fields == {"college_id": other_id}


def test_role_switch_rejects_old_auth_and_reused_page_context():
    teacher = _auth("tea_li")
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        class_id = conn.execute(
            "SELECT id FROM teaching_class WHERE teacher_id = ? ORDER BY id LIMIT 1",
            (teacher.row_scope["teacher_id"],),
        ).fetchone()[0]
    request = {"page": "course_analytics", "teaching_class_id": class_id}
    resolve_assistant_context(teacher, request)
    counselor_binding = next(
        item for item in teacher.available_roles if item["role"] == "counselor"
    )
    counselor, _ = switch_role(teacher, counselor_binding["id"])

    with pytest.raises(AssistantContextAuthorizationError) as stale:
        resolve_assistant_context(teacher, request)
    assert stale.value.rejected_fields == {"auth": teacher.role_binding_id}
    with pytest.raises(AssistantContextAuthorizationError) as reused:
        resolve_assistant_context(counselor, request)
    assert reused.value.rejected_fields == {"page": "course_analytics"}


def test_irrelevant_fields_are_reported_as_ignored_and_reserved_filters_rejected():
    auth = _auth("stu_zhang")
    resolved = resolve_assistant_context(
        auth, {"page": "profile", "student_id": 999999, "filters": {"tab": "security"}}
    )
    assert resolved.effective_context == {"page": "profile"}
    assert resolved.ignored_fields == {
        "student_id": 999999,
        "filters": {"tab": "security"},
    }
    with pytest.raises(AssistantContextAuthorizationError) as raised:
        resolve_assistant_context(
            auth, {"page": "assistant", "filters": {"allowed_tables": ["app_user"]}}
        )
    assert "filters" in raised.value.rejected_fields


def test_page_context_validates_time_range_and_filter_size():
    with pytest.raises(ValidationError, match="开始时间不能晚于结束时间"):
        AssistantPageContext(
            page="assistant",
            time_range={
                "start": "2026-07-19T00:00:00+08:00",
                "end": "2026-07-18T00:00:00+08:00",
            },
        )
    with pytest.raises(ValidationError, match="4 KB"):
        AssistantPageContext(page="assistant", filters={"query": "x" * 5000})
