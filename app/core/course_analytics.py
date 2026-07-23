"""Course-scoped analytics and a tightly constrained NL2SQL entry point."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.core.assignment_workflow import list_my_classes
from app.core.authorization import connect, require_course_member
from app.core.business_domains import AuthContext, AuthorizationError
from app.service import ask as ask_service


TEACHER_TABLES = {"course_assignment_analytics"}
STUDENT_TABLES = {"student_task_analytics"}
BLOCKED_QUESTION_TERMS = (
    "附件", "正文", "作业内容", "评语", "联系方式", "电话", "联系记录",
    "帮扶记录", "辅导员", "姓名", "学号", "名单",
)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def refresh_analytics() -> str:
    """Rebuild derived, non-sensitive snapshots from the transactional tables."""
    refreshed_at = _now()
    with connect() as conn:
        conn.execute("DELETE FROM course_assignment_analytics")
        conn.execute(
            """
            INSERT INTO course_assignment_analytics (
                assignment_id, teaching_class_id, teacher_id, course_code, course_name,
                year, semester, assignment_title, due_time, max_score, enrolled_count,
                submitted_count, on_time_count, late_count, missing_count,
                pending_grade_count, graded_count, published_grade_count, average_score,
                score_lt_60_count, score_60_69_count, score_70_79_count,
                score_80_89_count, score_90_plus_count,
                completion_rate, late_rate, refreshed_at
            )
            SELECT a.id, a.teaching_class_id, tc.teacher_id, c.course_code, c.name,
                   tc.year, tc.semester, a.title, a.due_time, a.max_score,
                   (SELECT COUNT(*) FROM enrollment e WHERE e.teaching_class_id = a.teaching_class_id),
                   (SELECT COUNT(*) FROM assignment_submission s
                    WHERE s.assignment_id = a.id AND s.submit_time IS NOT NULL),
                   (SELECT COUNT(*) FROM assignment_submission s
                    WHERE s.assignment_id = a.id AND s.submit_time IS NOT NULL AND COALESCE(s.late, 0) = 0),
                   (SELECT COUNT(*) FROM assignment_submission s
                    WHERE s.assignment_id = a.id AND s.submit_time IS NOT NULL AND COALESCE(s.late, 0) = 1),
                   MAX(0, (SELECT COUNT(*) FROM enrollment e WHERE e.teaching_class_id = a.teaching_class_id)
                        - (SELECT COUNT(*) FROM assignment_submission s
                           WHERE s.assignment_id = a.id AND s.submit_time IS NOT NULL)),
                   (SELECT COUNT(*) FROM assignment_submission s
                    WHERE s.assignment_id = a.id AND s.submit_time IS NOT NULL
                      AND s.status NOT IN ('returned', 'missing')
                      AND NOT EXISTS (SELECT 1 FROM grading_record g WHERE g.submission_id = s.id)),
                   (SELECT COUNT(*) FROM assignment_submission s
                    WHERE s.assignment_id = a.id
                      AND (s.score IS NOT NULL OR EXISTS
                           (SELECT 1 FROM grading_record g WHERE g.submission_id = s.id))),
                   (SELECT COUNT(*) FROM assignment_submission s
                    WHERE s.assignment_id = a.id AND EXISTS
                          (SELECT 1 FROM grading_record g
                           WHERE g.submission_id = s.id AND g.published = 1)),
                   (SELECT ROUND(AVG(COALESCE(
                              (SELECT g.score FROM grading_record g
                               WHERE g.submission_id = s.id ORDER BY g.id DESC LIMIT 1), s.score)), 2)
                    FROM assignment_submission s
                    WHERE s.assignment_id = a.id AND (s.score IS NOT NULL OR EXISTS
                          (SELECT 1 FROM grading_record g WHERE g.submission_id = s.id))),
                   (SELECT COUNT(*) FROM assignment_submission s WHERE s.assignment_id = a.id AND COALESCE((SELECT g.score FROM grading_record g WHERE g.submission_id = s.id ORDER BY g.id DESC LIMIT 1), s.score) < 60),
                   (SELECT COUNT(*) FROM assignment_submission s WHERE s.assignment_id = a.id AND COALESCE((SELECT g.score FROM grading_record g WHERE g.submission_id = s.id ORDER BY g.id DESC LIMIT 1), s.score) >= 60 AND COALESCE((SELECT g.score FROM grading_record g WHERE g.submission_id = s.id ORDER BY g.id DESC LIMIT 1), s.score) < 70),
                   (SELECT COUNT(*) FROM assignment_submission s WHERE s.assignment_id = a.id AND COALESCE((SELECT g.score FROM grading_record g WHERE g.submission_id = s.id ORDER BY g.id DESC LIMIT 1), s.score) >= 70 AND COALESCE((SELECT g.score FROM grading_record g WHERE g.submission_id = s.id ORDER BY g.id DESC LIMIT 1), s.score) < 80),
                   (SELECT COUNT(*) FROM assignment_submission s WHERE s.assignment_id = a.id AND COALESCE((SELECT g.score FROM grading_record g WHERE g.submission_id = s.id ORDER BY g.id DESC LIMIT 1), s.score) >= 80 AND COALESCE((SELECT g.score FROM grading_record g WHERE g.submission_id = s.id ORDER BY g.id DESC LIMIT 1), s.score) < 90),
                   (SELECT COUNT(*) FROM assignment_submission s WHERE s.assignment_id = a.id AND COALESCE((SELECT g.score FROM grading_record g WHERE g.submission_id = s.id ORDER BY g.id DESC LIMIT 1), s.score) >= 90),
                   CASE WHEN (SELECT COUNT(*) FROM enrollment e WHERE e.teaching_class_id = a.teaching_class_id) = 0 THEN 0
                        ELSE ROUND(100.0 * (SELECT COUNT(*) FROM assignment_submission s
                                           WHERE s.assignment_id = a.id AND s.submit_time IS NOT NULL)
                                   / (SELECT COUNT(*) FROM enrollment e WHERE e.teaching_class_id = a.teaching_class_id), 2) END,
                   CASE WHEN (SELECT COUNT(*) FROM assignment_submission s
                              WHERE s.assignment_id = a.id AND s.submit_time IS NOT NULL) = 0 THEN 0
                        ELSE ROUND(100.0 * (SELECT COUNT(*) FROM assignment_submission s
                                           WHERE s.assignment_id = a.id AND s.submit_time IS NOT NULL
                                             AND COALESCE(s.late, 0) = 1)
                                   / (SELECT COUNT(*) FROM assignment_submission s
                                      WHERE s.assignment_id = a.id AND s.submit_time IS NOT NULL), 2) END,
                   ?
            FROM assignment a
            JOIN teaching_class tc ON tc.id = a.teaching_class_id
            JOIN course c ON c.id = tc.course_id
            WHERE a.status <> 'draft'
            """,
            (refreshed_at,),
        )
        conn.execute("DELETE FROM student_task_analytics")
        conn.execute(
            """
            INSERT INTO student_task_analytics (
                assignment_id, teaching_class_id, teacher_id, student_id, course_code,
                course_name, assignment_title, due_time, max_score, task_status,
                submitted_at, late, published_score, refreshed_at
            )
            SELECT a.id, a.teaching_class_id, tc.teacher_id, e.student_id, c.course_code,
                   c.name, a.title, a.due_time, a.max_score,
                   CASE
                     WHEN s.id IS NULL OR s.submit_time IS NULL THEN 'missing'
                     WHEN s.status = 'returned' THEN 'returned'
                     WHEN EXISTS (SELECT 1 FROM grading_record g WHERE g.submission_id = s.id AND g.published = 1) THEN 'graded'
                     WHEN EXISTS (SELECT 1 FROM grading_record g WHERE g.submission_id = s.id) THEN 'graded_unpublished'
                     WHEN COALESCE(s.late, 0) = 1 THEN 'late_submitted'
                     ELSE 'submitted'
                   END,
                   s.submit_time, COALESCE(s.late, 0),
                   (SELECT g.score FROM grading_record g
                    WHERE g.submission_id = s.id AND g.published = 1
                    ORDER BY g.id DESC LIMIT 1), ?
            FROM enrollment e
            JOIN teaching_class tc ON tc.id = e.teaching_class_id
            JOIN course c ON c.id = tc.course_id
            JOIN assignment a ON a.teaching_class_id = e.teaching_class_id AND a.status <> 'draft'
            LEFT JOIN assignment_submission s ON s.assignment_id = a.id AND s.student_id = e.student_id
            """,
            (refreshed_at,),
        )
        conn.commit()
    return refreshed_at


def analytics_contexts(ctx: AuthContext) -> list[dict[str, Any]]:
    if ctx.role not in {"teacher", "student"}:
        raise AuthorizationError("课程分析仅面向任课教师和已选课学生")
    return list_my_classes(ctx)


def _scope(ctx: AuthContext, teaching_class_id: int) -> dict[str, Any]:
    resource = require_course_member(ctx, teaching_class_id)
    return {
        "teaching_class_id": teaching_class_id,
        **({"teacher_id": ctx.row_scope["teacher_id"]} if ctx.role == "teacher" else {}),
        **({"student_id": ctx.row_scope["student_id"]} if ctx.role == "student" else {}),
        "course_name": resource.data.get("course_name"),
    }


def course_summary(ctx: AuthContext, teaching_class_id: int) -> dict[str, Any]:
    scope = _scope(ctx, teaching_class_id)
    refreshed_at = refresh_analytics()
    with connect() as conn:
        if ctx.role == "teacher":
            rows = conn.execute(
                "SELECT * FROM course_assignment_analytics WHERE teaching_class_id = ? AND teacher_id = ? ORDER BY due_time",
                (teaching_class_id, scope["teacher_id"]),
            ).fetchall()
            items = [dict(row) for row in rows]
            expected = sum(item["enrolled_count"] for item in items)
            submitted = sum(item["submitted_count"] for item in items)
            late = sum(item["late_count"] for item in items)
            pending = sum(item["pending_grade_count"] for item in items)
            metrics = {
                "completion_rate": round(100 * submitted / expected, 2) if expected else 0,
                "late_rate": round(100 * late / submitted, 2) if submitted else 0,
                "pending_grade_count": pending,
                "assignment_count": len(items),
            }
            scores = [item["average_score"] for item in items if item["average_score"] is not None]
            score_summary = {"average": round(sum(scores) / len(scores), 2) if scores else None, "graded_assignments": len(scores)}
            score_summary["distribution"] = {
                "lt_60": sum(item["score_lt_60_count"] for item in items),
                "60_69": sum(item["score_60_69_count"] for item in items),
                "70_79": sum(item["score_70_79_count"] for item in items),
                "80_89": sum(item["score_80_89_count"] for item in items),
                "90_plus": sum(item["score_90_plus_count"] for item in items),
            }
        else:
            items = [dict(row) for row in conn.execute(
                "SELECT * FROM student_task_analytics WHERE teaching_class_id = ? AND student_id = ? ORDER BY due_time",
                (teaching_class_id, scope["student_id"]),
            ).fetchall()]
            submitted_states = {"submitted", "late_submitted", "graded", "graded_unpublished"}
            pending_states = {"missing", "returned"}
            scores = [item["published_score"] for item in items if item["published_score"] is not None]
            metrics = {
                "completion_rate": round(100 * sum(item["task_status"] in submitted_states for item in items) / len(items), 2) if items else 0,
                "late_rate": round(100 * sum(bool(item["late"]) for item in items) / len(items), 2) if items else 0,
                "pending_task_count": sum(item["task_status"] in pending_states for item in items),
                "assignment_count": len(items),
            }
            score_summary = {"average": round(sum(scores) / len(scores), 2) if scores else None, "published_count": len(scores)}
    return {
        "role": ctx.role,
        "scope": scope,
        "metrics": metrics,
        "score_summary": score_summary,
        "items": items,
        "refreshed_at": refreshed_at,
        "definitions": {
            "completion_rate": "已提交任务数 / 应提交任务数；草稿作业不计入",
            "late_rate": "教师端为迟交提交数 / 已提交数；学生端为迟交任务数 / 本课程任务数",
            "pending": "教师端为已提交但尚无批阅记录；学生端为未交或被退回任务",
            "score": "教师端统计已批阅成绩；学生端仅统计已发布给本人的成绩",
            "source": "课程作业、选课、提交和成绩发布记录的脱敏分析快照",
        },
    }


def _template_sql(ctx: AuthContext, teaching_class_id: int, question: str) -> str | None:
    q = question.replace(" ", "")
    if ctx.role == "teacher":
        where = f"teaching_class_id = {teaching_class_id} AND teacher_id = {ctx.row_scope['teacher_id']}"
        if "未交" in q or "完成" in q:
            return f"SELECT assignment_title, enrolled_count, submitted_count, missing_count, completion_rate FROM course_assignment_analytics WHERE {where} ORDER BY missing_count DESC"
        if "迟交" in q:
            return f"SELECT assignment_title, submitted_count, late_count, late_rate FROM course_assignment_analytics WHERE {where} ORDER BY late_rate DESC"
        if "待批" in q or "批阅" in q:
            return f"SELECT assignment_title, pending_grade_count, graded_count FROM course_assignment_analytics WHERE {where} ORDER BY pending_grade_count DESC"
    else:
        where = f"teaching_class_id = {teaching_class_id} AND student_id = {ctx.row_scope['student_id']}"
        if any(term in q for term in ("剩", "未交", "待完成", "任务")):
            return f"SELECT assignment_title, due_time, task_status, late, published_score FROM student_task_analytics WHERE {where} AND task_status IN ('missing', 'returned') ORDER BY due_time"
        if "成绩" in q or "得分" in q:
            return f"SELECT assignment_title, published_score, max_score FROM student_task_analytics WHERE {where} AND published_score IS NOT NULL ORDER BY due_time"
    return None


def _execute_template(sql: str) -> dict[str, Any]:
    with connect() as conn:
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        return {"sql": sql, "columns": [item[0] for item in cursor.description], "rows": [list(row) for row in rows], "row_count": len(rows), "error": None, "confidence": 100}


def ask_course(ctx: AuthContext, teaching_class_id: int, question: str) -> dict[str, Any]:
    question = question.strip()
    if not question:
        raise ValueError("请输入要分析的问题")
    scope = _scope(ctx, teaching_class_id)
    blocked = next((term for term in BLOCKED_QUESTION_TERMS if term in question), None)
    if blocked:
        raise ValueError(f"课程分析不提供“{blocked}”相关明细，请到对应业务页面按权限查看")
    refresh_analytics()
    template_sql = _template_sql(ctx, teaching_class_id, question)
    mode = "context_template" if template_sql else "nl2sql"
    if template_sql:
        result = _execute_template(template_sql)
    else:
        tables = TEACHER_TABLES if ctx.role == "teacher" else STUDENT_TABLES
        result = ask_service(
            question=f"仅分析 teaching_class_id = {teaching_class_id} 的当前课程。{question}",
            source="teaching",
            allowed_tables=tables,
            denied_columns=set(),
            denied_terms=BLOCKED_QUESTION_TERMS,
            role_label=ctx.role_label,
            row_scope={key: value for key, value in scope.items() if key.endswith("_id")},
            user_glossary=[
                "只能使用给定分析表，所有查询必须显式包含当前 teaching_class_id",
                "教师分析只允许作业级汇总，不返回学生身份或提交内容",
                "学生分析必须显式包含当前 student_id，成绩只使用 published_score",
            ],
        )
    status = "success" if not result.get("error") and not result.get("clarify") else "failed"
    log_id = _log_query(ctx, teaching_class_id, question, result, mode, scope, status)
    return {**result, "query_log_id": log_id, "query_mode": mode, "scope": scope}


def _log_query(ctx: AuthContext, teaching_class_id: int, question: str, result: dict[str, Any], mode: str, scope: dict[str, Any], status: str) -> int:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO analytics_query_log
            (username, role, teaching_class_id, question, generated_sql, status, row_count,
             confidence, query_mode, error, scope_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ctx.username, ctx.role, teaching_class_id, question, result.get("sql"), status,
             int(result.get("row_count") or 0), result.get("confidence"), mode,
             result.get("error") or result.get("clarify"), json.dumps(scope, ensure_ascii=False), _now()),
        )
        conn.commit()
        return int(cursor.lastrowid)


def query_history(ctx: AuthContext, teaching_class_id: int, limit: int = 10) -> list[dict[str, Any]]:
    _scope(ctx, teaching_class_id)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, question, status, row_count, confidence, query_mode, user_feedback, created_at
            FROM analytics_query_log
            WHERE username = ? AND teaching_class_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (ctx.username, teaching_class_id, min(max(limit, 1), 50)),
        ).fetchall()
    return [dict(row) for row in rows]


def save_query_feedback(ctx: AuthContext, log_id: int, feedback: str) -> dict[str, Any]:
    if feedback not in {"helpful", "not_helpful"}:
        raise ValueError("反馈值无效")
    with connect() as conn:
        row = conn.execute(
            "SELECT id, username FROM analytics_query_log WHERE id = ?", (log_id,)
        ).fetchone()
        if not row or row["username"] != ctx.username:
            raise AuthorizationError("无权反馈该查询记录")
        conn.execute("UPDATE analytics_query_log SET user_feedback = ? WHERE id = ?", (feedback, log_id))
        conn.commit()
    return {"id": log_id, "user_feedback": feedback}
