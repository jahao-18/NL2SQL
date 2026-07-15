"""Service-layer authorization for real teaching workflows."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from app.core.business_domains import AuthContext, AuthorizationError
from app.core.teaching_migrations import DB_PATH


@dataclass(frozen=True)
class ResourceScope:
    resource_type: str
    resource_id: int
    data: dict[str, Any]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def forbidden() -> None:
    raise AuthorizationError("无权访问该资源")


def require_student_self(ctx: AuthContext, student_id: int) -> ResourceScope:
    own_student_id = ctx.row_scope.get("student_id")
    if ctx.role != "student" or own_student_id != student_id:
        forbidden()
    return ResourceScope("student", student_id, {"student_id": student_id})


def require_teacher_of_class(ctx: AuthContext, teaching_class_id: int) -> ResourceScope:
    teacher_id = ctx.row_scope.get("teacher_id")
    if ctx.role != "teacher" or not teacher_id:
        forbidden()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT tc.id, tc.teacher_id, c.name AS course_name
            FROM teaching_class tc
            JOIN course c ON c.id = tc.course_id
            WHERE tc.id = ?
            """,
            (teaching_class_id,),
        ).fetchone()
    if not row or row["teacher_id"] != teacher_id:
        forbidden()
    return ResourceScope("teaching_class", teaching_class_id, dict(row))


def require_course_member(ctx: AuthContext, teaching_class_id: int) -> ResourceScope:
    if ctx.role == "teacher":
        return require_teacher_of_class(ctx, teaching_class_id)
    student_id = ctx.row_scope.get("student_id")
    if ctx.role != "student" or not student_id:
        forbidden()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT e.teaching_class_id, e.student_id, c.name AS course_name
            FROM enrollment e
            JOIN teaching_class tc ON tc.id = e.teaching_class_id
            JOIN course c ON c.id = tc.course_id
            WHERE e.teaching_class_id = ? AND e.student_id = ?
            """,
            (teaching_class_id, student_id),
        ).fetchone()
    if not row:
        forbidden()
    return ResourceScope("teaching_class", teaching_class_id, dict(row))


def require_submission_access(ctx: AuthContext, submission_id: int) -> ResourceScope:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT sub.id, sub.student_id, sub.assignment_id, sub.status,
                   a.teaching_class_id, a.title
            FROM assignment_submission sub
            JOIN assignment a ON a.id = sub.assignment_id
            WHERE sub.id = ?
            """,
            (submission_id,),
        ).fetchone()
    if not row:
        forbidden()
    data = dict(row)
    if ctx.role == "student":
        require_student_self(ctx, data["student_id"])
    elif ctx.role == "teacher":
        require_teacher_of_class(ctx, data["teaching_class_id"])
    else:
        forbidden()
    return ResourceScope("assignment_submission", submission_id, data)


def require_counselor_of_student(ctx: AuthContext, student_id: int) -> ResourceScope:
    counselor_id = ctx.row_scope.get("counselor_id")
    if ctx.role != "counselor" or not counselor_id:
        forbidden()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT s.id AS student_id, s.name AS student_name, s.class_id, ccg.counselor_id
            FROM student s
            JOIN counselor_class_group ccg ON ccg.class_group_id = s.class_id
            WHERE s.id = ? AND ccg.counselor_id = ?
            """,
            (student_id, counselor_id),
        ).fetchone()
    if not row:
        forbidden()
    return ResourceScope("student", student_id, dict(row))


def require_support_case_access(ctx: AuthContext, case_id: int) -> ResourceScope:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT sc.*, s.name AS student_name
            FROM support_case sc
            JOIN student s ON s.id = sc.student_id
            WHERE sc.id = ?
            """,
            (case_id,),
        ).fetchone()
    if not row:
        forbidden()
    data = dict(row)
    if ctx.role == "counselor":
        require_counselor_of_student(ctx, data["student_id"])
    elif ctx.role == "student":
        require_student_self(ctx, data["student_id"])
        if not data.get("visible_to_student"):
            forbidden()
        data.pop("closed_reason", None)
        data.pop("counselor_id", None)
    else:
        forbidden()
    return ResourceScope("support_case", case_id, data)


def list_class_submissions(ctx: AuthContext, teaching_class_id: int) -> list[dict[str, Any]]:
    require_teacher_of_class(ctx, teaching_class_id)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT sub.id, sub.assignment_id, sub.student_id, s.name AS student_name,
                   a.title AS assignment_title, sub.submit_time, sub.score, sub.late, sub.status, sub.feedback
            FROM assignment_submission sub
            JOIN assignment a ON a.id = sub.assignment_id
            JOIN student s ON s.id = sub.student_id
            WHERE a.teaching_class_id = ?
            ORDER BY a.id, sub.student_id
            """,
            (teaching_class_id,),
        ).fetchall()
    return [dict(row) for row in rows]
