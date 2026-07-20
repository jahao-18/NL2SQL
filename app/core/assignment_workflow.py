"""Assignment workflow services for stage 2 MVP."""
from __future__ import annotations

import base64
import binascii
import secrets
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

from app.core.authorization import connect, forbidden, require_submission_access, require_teacher_of_class
from app.core.business_domains import AuthContext, AuthorizationError
from app.core.teaching_migrations import DB_PATH


SUBMISSION_DIR = DB_PATH.parent / "submissions"
ALLOWED_FILE_SUFFIXES = {".pdf", ".doc", ".docx", ".zip", ".png", ".jpg", ".jpeg", ".txt"}
MAX_FILE_BYTES = 5 * 1024 * 1024


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("截止时间格式不正确") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _normalized_time(value: str) -> str:
    return _parse_time(value).isoformat()


def _audit(conn, ctx: AuthContext, resource_type: str, resource_id: int, action: str, before: str | None, after: str | None) -> None:
    conn.execute(
        """
        INSERT INTO audit_log(actor_user, actor_role, resource_type, resource_id, action, before_state, after_state, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ctx.username, ctx.role, resource_type, resource_id, action, before, after, now_iso()),
    )


def _notify(conn, username: str, kind: str, title: str, body: str, resource_type: str, resource_id: int) -> None:
    conn.execute(
        """
        INSERT INTO notification(recipient_username, type, title, body, resource_type, resource_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (username, kind, title, body, resource_type, resource_id, now_iso()),
    )


def list_my_assignments(ctx: AuthContext) -> list[dict[str, Any]]:
    if ctx.role != "student" or not ctx.row_scope.get("student_id"):
        forbidden()
    student_id = ctx.row_scope["student_id"]
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.teaching_class_id, c.name AS course_name, c.course_code, a.title,
                   a.instructions, a.status AS assignment_status,
                   a.publish_time, a.due_time, a.max_score, a.allow_late,
                   sub.id AS submission_id, sub.status AS submission_status, sub.submit_time,
                   sv.version_no AS latest_version_no, sv.content AS latest_content,
                   CASE WHEN sv.file_key IS NOT NULL THEN sv.file_name ELSE NULL END AS latest_file_name,
                   CASE WHEN sv.file_key IS NOT NULL THEN sv.file_size ELSE NULL END AS latest_file_size,
                   (SELECT COUNT(*) FROM submission_version WHERE submission_id = sub.id) AS version_count,
                   CASE WHEN gr.published = 1 THEN gr.score ELSE NULL END AS score,
                   CASE WHEN gr.published = 1 THEN gr.feedback ELSE NULL END AS feedback
            FROM enrollment e
            JOIN teaching_class tc ON tc.id = e.teaching_class_id
            JOIN course c ON c.id = tc.course_id
            JOIN assignment a ON a.teaching_class_id = tc.id
            LEFT JOIN assignment_submission sub ON sub.assignment_id = a.id AND sub.student_id = e.student_id
            LEFT JOIN submission_version sv ON sv.id = (
              SELECT MAX(id) FROM submission_version WHERE submission_id = sub.id
            )
            LEFT JOIN grading_record gr ON gr.submission_id = sub.id
              AND gr.id = (SELECT MAX(id) FROM grading_record WHERE submission_id = sub.id)
            WHERE e.student_id = ? AND a.status IN ('published', 'closed')
            ORDER BY CASE COALESCE(sub.status, 'missing')
                WHEN 'returned' THEN 1 WHEN 'missing' THEN 2 WHEN 'late_submitted' THEN 3
                WHEN 'submitted' THEN 3 WHEN 'resubmitted' THEN 3 WHEN 'graded_unpublished' THEN 4 ELSE 5 END,
                a.due_time ASC, a.id ASC
            """,
            (student_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_my_classes(ctx: AuthContext) -> list[dict[str, Any]]:
    with connect() as conn:
        if ctx.role == "teacher" and ctx.row_scope.get("teacher_id"):
            rows = conn.execute(
                """
                SELECT tc.id, c.name AS course_name, c.course_code, tc.year, tc.semester, tc.classroom,
                       COUNT(DISTINCT e.student_id) AS student_count,
                       COUNT(DISTINCT a.id) AS assignment_count
                FROM teaching_class tc
                JOIN course c ON c.id = tc.course_id
                LEFT JOIN enrollment e ON e.teaching_class_id = tc.id
                LEFT JOIN assignment a ON a.teaching_class_id = tc.id
                WHERE tc.teacher_id = ?
                GROUP BY tc.id
                ORDER BY tc.year DESC, tc.semester DESC, c.name
                """,
                (ctx.row_scope["teacher_id"],),
            ).fetchall()
        elif ctx.role == "student" and ctx.row_scope.get("student_id"):
            rows = conn.execute(
                """
                SELECT tc.id, c.name AS course_name, c.course_code, tc.year, tc.semester, tc.classroom,
                       t.name AS teacher_name,
                       (SELECT COUNT(*) FROM assignment a WHERE a.teaching_class_id = tc.id AND a.status != 'draft') AS assignment_count
                FROM enrollment e
                JOIN teaching_class tc ON tc.id = e.teaching_class_id
                JOIN course c ON c.id = tc.course_id
                JOIN teacher t ON t.id = tc.teacher_id
                WHERE e.student_id = ?
                ORDER BY tc.year DESC, tc.semester DESC, c.name
                """,
                (ctx.row_scope["student_id"],),
            ).fetchall()
        else:
            forbidden()
    return [dict(row) for row in rows]


def teacher_missing_assignment_roster(
    ctx: AuthContext, teaching_class_id: int | None = None
) -> list[dict[str, Any]]:
    """Return a teacher's own missing-submission roster without model-generated SQL."""
    if ctx.role != "teacher" or not ctx.row_scope.get("teacher_id"):
        forbidden()
    clauses = ["tc.teacher_id = ?", "a.status IN ('published', 'closed')"]
    params: list[Any] = [ctx.row_scope["teacher_id"]]
    if teaching_class_id:
        clauses.append("tc.id = ?")
        params.append(teaching_class_id)
    clauses.append("(sub.id IS NULL OR sub.submit_time IS NULL OR sub.status IN ('missing', 'not_submitted'))")
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT stu.name AS student_name, c.name AS course_name,
                       a.title AS assignment_title, a.due_time
                FROM assignment a
                JOIN teaching_class tc ON tc.id = a.teaching_class_id
                JOIN course c ON c.id = tc.course_id
                JOIN enrollment e ON e.teaching_class_id = tc.id
                JOIN student stu ON stu.id = e.student_id
                LEFT JOIN assignment_submission sub
                  ON sub.assignment_id = a.id AND sub.student_id = e.student_id
                WHERE {' AND '.join(clauses)}
                ORDER BY c.name, a.due_time, stu.name
                LIMIT 200""",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def list_class_assignments(ctx: AuthContext, teaching_class_id: int) -> list[dict[str, Any]]:
    require_teacher_of_class(ctx, teaching_class_id)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.title, a.instructions, a.status, a.publish_time, a.due_time,
                   a.max_score, a.allow_late,
                   COUNT(DISTINCT e.student_id) AS student_count,
                   COUNT(DISTINCT CASE WHEN sub.submit_time IS NOT NULL THEN sub.student_id END) AS submitted_count,
                   COUNT(DISTINCT CASE WHEN sub.status IN ('submitted', 'late_submitted', 'resubmitted') THEN sub.student_id END) AS pending_grade_count,
                   COUNT(DISTINCT CASE WHEN sub.status = 'graded_unpublished' THEN sub.student_id END) AS unpublished_count,
                   COUNT(DISTINCT CASE WHEN sub.status = 'graded_published' THEN sub.student_id END) AS published_count,
                   MAX(CASE WHEN sub.status IN ('submitted', 'late_submitted', 'resubmitted') THEN sub.submit_time END) AS latest_pending_submit_time
            FROM assignment a
            LEFT JOIN enrollment e ON e.teaching_class_id = a.teaching_class_id
            LEFT JOIN assignment_submission sub ON sub.assignment_id = a.id AND sub.student_id = e.student_id
            WHERE a.teaching_class_id = ?
            GROUP BY a.id
            ORDER BY CASE WHEN pending_grade_count > 0 THEN 0 ELSE 1 END,
                     latest_pending_submit_time DESC, unpublished_count DESC,
                     CASE a.status WHEN 'draft' THEN 2 ELSE 1 END, a.due_time ASC, a.id DESC
            """,
            (teaching_class_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_assignment_roster(ctx: AuthContext, assignment_id: int) -> list[dict[str, Any]]:
    assignment = get_assignment(ctx, assignment_id)
    require_teacher_of_class(ctx, assignment["teaching_class_id"])
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT e.student_id, s.student_no, s.name AS student_name,
                   sub.id AS submission_id, sub.submit_time, sub.score, sub.late,
                   COALESCE(sub.status, 'missing') AS status, sub.feedback,
                   (SELECT MAX(version_no) FROM submission_version sv WHERE sv.submission_id = sub.id) AS version_no,
                   (SELECT content FROM submission_version sv WHERE sv.submission_id = sub.id ORDER BY version_no DESC LIMIT 1) AS content,
                   (SELECT file_name FROM submission_version sv WHERE sv.submission_id = sub.id AND file_key IS NOT NULL ORDER BY version_no DESC LIMIT 1) AS file_name,
                   (SELECT version_no FROM submission_version sv WHERE sv.submission_id = sub.id AND file_key IS NOT NULL ORDER BY version_no DESC LIMIT 1) AS file_version_no,
                   (SELECT file_size FROM submission_version sv WHERE sv.submission_id = sub.id AND file_key IS NOT NULL ORDER BY version_no DESC LIMIT 1) AS file_size,
                   (SELECT COUNT(*) FROM submission_version sv WHERE sv.submission_id = sub.id) AS version_count
            FROM enrollment e
            JOIN student s ON s.id = e.student_id
            LEFT JOIN assignment_submission sub ON sub.assignment_id = ? AND sub.student_id = e.student_id
            WHERE e.teaching_class_id = ?
            ORDER BY CASE COALESCE(sub.status, 'missing')
                WHEN 'submitted' THEN 1 WHEN 'late_submitted' THEN 1 WHEN 'resubmitted' THEN 1
                WHEN 'graded_unpublished' THEN 2 WHEN 'returned' THEN 3 WHEN 'missing' THEN 4 ELSE 5 END,
                s.student_no
            """,
            (assignment_id, assignment["teaching_class_id"]),
        ).fetchall()
    return [dict(row) for row in rows]


def create_assignment(ctx: AuthContext, teaching_class_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    require_teacher_of_class(ctx, teaching_class_id)
    title = str(payload.get("title") or "").strip()
    due_time = str(payload.get("due_time") or "").strip()
    if not title or not due_time:
        raise ValueError("作业标题和截止时间不能为空")
    max_score = float(payload.get("max_score") or 100)
    if max_score <= 0:
        raise ValueError("满分必须大于 0")
    status = str(payload.get("status") or "published")
    if status not in {"draft", "published"}:
        raise ValueError("作业初始状态只能是 draft 或 published")
    due_time = _normalized_time(due_time)
    if status == "published" and _parse_time(due_time) <= datetime.now(timezone.utc):
        raise ValueError("发布作业时截止时间必须晚于当前时间")
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO assignment(teaching_class_id, title, assignment_type, publish_time, due_time, max_score, weight, status, instructions, allow_late)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                teaching_class_id,
                title,
                str(payload.get("assignment_type") or "homework"),
                now_iso(),
                due_time,
                max_score,
                float(payload.get("weight") or 0.1),
                status,
                str(payload.get("instructions") or "").strip(),
                1 if payload.get("allow_late", True) else 0,
            ),
        )
        assignment_id = int(cur.lastrowid)
        _audit(conn, ctx, "assignment", assignment_id, "create_assignment", None, status)
        if status == "published":
            _notify_students_for_assignment(conn, teaching_class_id, assignment_id, title)
        conn.commit()
        return get_assignment(ctx, assignment_id)


def get_assignment(ctx: AuthContext, assignment_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT a.*, c.name AS course_name
            FROM assignment a
            JOIN teaching_class tc ON tc.id = a.teaching_class_id
            JOIN course c ON c.id = tc.course_id
            WHERE a.id = ?
            """,
            (assignment_id,),
        ).fetchone()
    if not row:
        forbidden()
    data = dict(row)
    if ctx.role == "teacher":
        require_teacher_of_class(ctx, data["teaching_class_id"])
    elif ctx.role == "student":
        from app.core.authorization import require_course_member

        require_course_member(ctx, data["teaching_class_id"])
        if data["status"] == "draft":
            forbidden()
    else:
        forbidden()
    return data


def update_assignment(ctx: AuthContext, assignment_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    assignment = get_assignment(ctx, assignment_id)
    if ctx.role != "teacher":
        forbidden()
    if assignment["status"] != "draft":
        raise ValueError("只有草稿作业可以编辑")
    title = str(payload.get("title") or "").strip()
    due_time = _normalized_time(str(payload.get("due_time") or "").strip())
    max_score = float(payload.get("max_score") or 100)
    if not title:
        raise ValueError("作业标题不能为空")
    if _parse_time(due_time) <= datetime.now(timezone.utc):
        raise ValueError("截止时间必须晚于当前时间")
    if max_score <= 0:
        raise ValueError("满分必须大于 0")
    with connect() as conn:
        conn.execute(
            """
            UPDATE assignment SET title = ?, instructions = ?, due_time = ?, max_score = ?,
                assignment_type = ?, weight = ?, allow_late = ? WHERE id = ?
            """,
            (
                title,
                str(payload.get("instructions") or "").strip(),
                due_time,
                max_score,
                str(payload.get("assignment_type") or "homework"),
                float(payload.get("weight") or 0.1),
                1 if payload.get("allow_late", True) else 0,
                assignment_id,
            ),
        )
        _audit(conn, ctx, "assignment", assignment_id, "update_assignment", "draft", "draft")
        conn.commit()
    return get_assignment(ctx, assignment_id)


def publish_assignment(ctx: AuthContext, assignment_id: int) -> dict[str, Any]:
    assignment = get_assignment(ctx, assignment_id)
    if ctx.role != "teacher":
        forbidden()
    if assignment["status"] != "draft":
        raise ValueError("只有草稿作业可以发布")
    if _parse_time(assignment["due_time"]) <= datetime.now(timezone.utc):
        raise ValueError("截止时间已过，请先修改作业")
    with connect() as conn:
        published_at = now_iso()
        conn.execute("UPDATE assignment SET status = 'published', publish_time = ? WHERE id = ?", (published_at, assignment_id))
        _audit(conn, ctx, "assignment", assignment_id, "publish_assignment", "draft", "published")
        _notify_students_for_assignment(conn, assignment["teaching_class_id"], assignment_id, assignment["title"])
        conn.commit()
    return get_assignment(ctx, assignment_id)


def submit_assignment(
    ctx: AuthContext,
    assignment_id: int,
    content: str,
    file_name: str | None = None,
    file_content_base64: str | None = None,
    retain_existing_file: bool = True,
) -> dict[str, Any]:
    if ctx.role != "student" or not ctx.row_scope.get("student_id"):
        forbidden()
    student_id = ctx.row_scope["student_id"]
    content = content.strip()
    file_bytes: bytes | None = None
    safe_file_name = Path(file_name or "").name
    if file_content_base64:
        if not safe_file_name or Path(safe_file_name).suffix.lower() not in ALLOWED_FILE_SUFFIXES:
            raise ValueError("附件仅支持 PDF、Word、ZIP、图片或文本文件")
        try:
            file_bytes = base64.b64decode(file_content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("附件内容无效") from exc
        if len(file_bytes) > MAX_FILE_BYTES:
            raise ValueError("附件不能超过 5MB")
    elif safe_file_name:
        raise ValueError("附件内容不能为空")
    assignment = get_assignment(ctx, assignment_id)
    if assignment["status"] != "published":
        raise ValueError("当前作业不可提交")
    overdue = _parse_time(assignment["due_time"]) < datetime.now(timezone.utc)
    if overdue and not assignment["allow_late"]:
        raise ValueError("作业已截止且不允许补交")
    next_status = "late_submitted" if overdue else "submitted"
    with connect() as conn:
        row = conn.execute(
            "SELECT id, status FROM assignment_submission WHERE assignment_id = ? AND student_id = ?",
            (assignment_id, student_id),
        ).fetchone()
        before = row["status"] if row else "not_submitted"
        previous_file = None
        if row and retain_existing_file and file_bytes is None:
            previous_file = conn.execute(
                """
                SELECT file_name, file_key, file_size
                FROM submission_version
                WHERE submission_id = ? AND file_key IS NOT NULL
                ORDER BY version_no DESC LIMIT 1
                """,
                (row["id"],),
            ).fetchone()
        if not content and file_bytes is None and previous_file is None:
            raise ValueError("提交说明和附件不能同时为空")
        if row and before in {"graded_published", "graded_unpublished"}:
            raise ValueError("已评分提交不能直接覆盖")
        if row:
            submission_id = row["id"]
            if before == "returned":
                next_status = "resubmitted"
            conn.execute(
                "UPDATE assignment_submission SET submit_time = ?, late = ?, status = ?, feedback = NULL WHERE id = ?",
                (now_iso(), 1 if overdue else 0, next_status, submission_id),
            )
        else:
            submission_id = int(conn.execute(
                """
                SELECT COALESCE(MAX(value), 0) + 1
                FROM (
                    SELECT MAX(id) AS value FROM assignment_submission
                    UNION ALL SELECT MAX(submission_id) FROM submission_version
                    UNION ALL SELECT MAX(submission_id) FROM grading_record
                )
                """
            ).fetchone()[0])
            conn.execute(
                """
                INSERT INTO assignment_submission(id, assignment_id, student_id, submit_time, score, late, status)
                VALUES (?, ?, ?, ?, NULL, ?, ?)
                """,
                (submission_id, assignment_id, student_id, now_iso(), 1 if overdue else 0, next_status),
            )
        version_no = conn.execute("SELECT COALESCE(MAX(version_no), 0) + 1 FROM submission_version WHERE submission_id = ?", (submission_id,)).fetchone()[0]
        file_key = None
        file_size = None
        if file_bytes is not None:
            suffix = Path(safe_file_name).suffix.lower()
            target_dir = SUBMISSION_DIR / str(submission_id)
            target_dir.mkdir(parents=True, exist_ok=True)
            file_key = f"{submission_id}/v{version_no}-{secrets.token_hex(8)}{suffix}"
            (SUBMISSION_DIR / file_key).write_bytes(file_bytes)
            file_size = len(file_bytes)
        elif previous_file is not None:
            safe_file_name = previous_file["file_name"]
            file_key = previous_file["file_key"]
            file_size = previous_file["file_size"]
        conn.execute(
            """
            INSERT INTO submission_version(submission_id, version_no, content, file_name, submitted_at, submitter_user, file_key, file_size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (submission_id, version_no, content, safe_file_name or None, now_iso(), ctx.username, file_key, file_size),
        )
        _audit(conn, ctx, "assignment_submission", submission_id, "submit_assignment", before, next_status)
        conn.commit()
    return get_submission(ctx, submission_id)


def get_submission(ctx: AuthContext, submission_id: int) -> dict[str, Any]:
    scope = require_submission_access(ctx, submission_id)
    with connect() as conn:
        versions = conn.execute(
            "SELECT version_no, content, file_name, file_size, submitted_at FROM submission_version WHERE submission_id = ? ORDER BY version_no",
            (submission_id,),
        ).fetchall()
        grade = conn.execute(
            "SELECT score, feedback, status, published, created_at, published_at FROM grading_record WHERE submission_id = ? ORDER BY id DESC LIMIT 1",
            (submission_id,),
        ).fetchone()
    data = dict(scope.data)
    data["versions"] = [dict(row) for row in versions]
    data["grade"] = dict(grade) if grade else None
    if ctx.role == "student" and data["grade"] and not data["grade"]["published"]:
        data["grade"] = {"status": "grading", "published": 0}
    return data


def get_submission_file(ctx: AuthContext, submission_id: int, version_no: int) -> tuple[Path, str]:
    require_submission_access(ctx, submission_id)
    with connect() as conn:
        row = conn.execute(
            "SELECT file_key, file_name FROM submission_version WHERE submission_id = ? AND version_no = ?",
            (submission_id, version_no),
        ).fetchone()
    if not row or not row["file_key"]:
        raise ValueError("该版本没有可下载附件")
    path = (SUBMISSION_DIR / row["file_key"]).resolve()
    if SUBMISSION_DIR.resolve() not in path.parents or not path.is_file():
        raise ValueError("附件不存在")
    return path, row["file_name"]


def return_submission(ctx: AuthContext, submission_id: int, feedback: str) -> dict[str, Any]:
    feedback = feedback.strip()
    if not feedback:
        raise ValueError("退回原因不能为空")
    scope = require_submission_access(ctx, submission_id)
    if ctx.role != "teacher":
        forbidden()
    before = scope.data["status"]
    if before not in {"submitted", "late_submitted", "resubmitted"}:
        raise ValueError("当前提交状态不能退回")
    with connect() as conn:
        conn.execute("UPDATE assignment_submission SET status = 'returned', feedback = ? WHERE id = ?", (feedback, submission_id))
        _audit(conn, ctx, "assignment_submission", submission_id, "return_submission", before, "returned")
        _notify_submission_student(conn, submission_id, "returned", "作业已退回", feedback)
        conn.commit()
    return get_submission(ctx, submission_id)


def grade_submission(ctx: AuthContext, submission_id: int, score: float, feedback: str) -> dict[str, Any]:
    scope = require_submission_access(ctx, submission_id)
    if ctx.role != "teacher":
        forbidden()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT a.max_score, sub.status
            FROM assignment_submission sub
            JOIN assignment a ON a.id = sub.assignment_id
            WHERE sub.id = ?
            """,
            (submission_id,),
        ).fetchone()
        if not row:
            forbidden()
        if row["status"] not in {"submitted", "late_submitted", "resubmitted"}:
            raise ValueError("当前提交状态不能评分")
        if score < 0 or score > row["max_score"]:
            raise ValueError("分数必须在 0 到满分之间")
        conn.execute(
            """
            INSERT INTO grading_record(submission_id, grader_teacher_id, score, feedback, status, published, created_at)
            VALUES (?, ?, ?, ?, 'graded_unpublished', 0, ?)
            """,
            (submission_id, ctx.row_scope["teacher_id"], score, feedback.strip(), now_iso()),
        )
        conn.execute(
            "UPDATE assignment_submission SET score = ?, status = 'graded_unpublished', feedback = ? WHERE id = ?",
            (score, feedback.strip(), submission_id),
        )
        _audit(conn, ctx, "assignment_submission", submission_id, "grade_submission", row["status"], "graded_unpublished")
        conn.commit()
    return get_submission(ctx, submission_id)


def publish_assignment_grades(ctx: AuthContext, assignment_id: int) -> dict[str, Any]:
    assignment = get_assignment(ctx, assignment_id)
    if ctx.role != "teacher":
        forbidden()
    require_teacher_of_class(ctx, assignment["teaching_class_id"])
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT sub.id
            FROM assignment_submission sub
            WHERE sub.assignment_id = ? AND sub.status = 'graded_unpublished'
            """,
            (assignment_id,),
        ).fetchall()
        for row in rows:
            submission_id = row["id"]
            conn.execute("UPDATE assignment_submission SET status = 'graded_published' WHERE id = ?", (submission_id,))
            conn.execute(
                """
                UPDATE grading_record SET status = 'graded_published', published = 1, published_at = ?
                WHERE id = (SELECT MAX(id) FROM grading_record WHERE submission_id = ?)
                """,
                (now_iso(), submission_id),
            )
            _audit(conn, ctx, "assignment_submission", submission_id, "publish_grade", "graded_unpublished", "graded_published")
            _notify_submission_student(conn, submission_id, "grade_published", "作业成绩已发布", assignment["title"])
        conn.commit()
    return {"published_count": len(rows)}


def _notify_students_for_assignment(conn, teaching_class_id: int, assignment_id: int, title: str) -> None:
    rows = conn.execute(
        """
        SELECT u.username
        FROM enrollment e
        JOIN app_user u ON u.student_id = e.student_id
        WHERE e.teaching_class_id = ?
        """,
        (teaching_class_id,),
    ).fetchall()
    for row in rows:
        _notify(conn, row["username"], "assignment_published", "新作业已发布", title, "assignment", assignment_id)


def _notify_submission_student(conn, submission_id: int, kind: str, title: str, body: str) -> None:
    row = conn.execute(
        """
        SELECT u.username
        FROM assignment_submission sub
        JOIN app_user u ON u.student_id = sub.student_id
        WHERE sub.id = ?
        """,
        (submission_id,),
    ).fetchone()
    if row:
        _notify(conn, row["username"], kind, title, body, "assignment_submission", submission_id)
