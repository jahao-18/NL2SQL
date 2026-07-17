"""Stage D course sessions, attendance and course Q&A services."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.core.authorization import (
    connect,
    forbidden,
    require_counselor_of_student,
    require_course_member,
    require_student_self,
    require_teacher_of_class,
)
from app.core.business_domains import AuthContext


ATTENDANCE_STATUSES = {"present", "late", "leave", "absent"}
QUESTION_VISIBILITIES = {"public", "private"}
QUESTION_STATUSES = {"open", "answered", "closed"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _valid_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("课程日期格式应为 YYYY-MM-DD") from exc


def _audit(conn, ctx: AuthContext, resource_type: str, resource_id: int, action: str, before: str | None, after: str | None) -> None:
    conn.execute(
        "INSERT INTO audit_log(actor_user, actor_role, resource_type, resource_id, action, before_state, after_state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ctx.username, ctx.role, resource_type, resource_id, action, before, after, _now()),
    )


def _notify(conn, username: str, kind: str, title: str, body: str, resource_type: str, resource_id: int) -> None:
    conn.execute(
        "INSERT INTO notification(recipient_username, type, title, body, resource_type, resource_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (username, kind, title, body, resource_type, resource_id, _now()),
    )


def _teacher_usernames(conn, teaching_class_id: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT au.username
        FROM teaching_class tc
        JOIN staff st ON st.teacher_id = tc.teacher_id
        JOIN person_identity pi ON pi.person_type = 'staff' AND pi.entity_id = st.id AND pi.status = 'verified'
        JOIN app_user au ON au.id = pi.user_id AND au.status = 'active'
        WHERE tc.id = ?
        """,
        (teaching_class_id,),
    ).fetchall()
    return [row["username"] for row in rows]


def _student_username(conn, student_id: int) -> str | None:
    row = conn.execute(
        """
        SELECT au.username
        FROM person_identity pi
        JOIN app_user au ON au.id = pi.user_id AND au.status = 'active'
        WHERE pi.person_type = 'student' AND pi.entity_id = ? AND pi.status = 'verified'
        LIMIT 1
        """,
        (student_id,),
    ).fetchone()
    return row["username"] if row else None


def create_course_session(ctx: AuthContext, teaching_class_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    require_teacher_of_class(ctx, teaching_class_id)
    session_date = _valid_date(str(payload.get("session_date") or ""))
    status = str(payload.get("status") or "scheduled")
    if status not in {"scheduled", "completed", "cancelled"}:
        raise ValueError("课程场次状态不正确")
    with connect() as conn:
        session_no = payload.get("session_no")
        if session_no is None:
            session_no = int(conn.execute("SELECT COALESCE(MAX(session_no), 0) + 1 FROM course_session WHERE teaching_class_id = ?", (teaching_class_id,)).fetchone()[0])
        if int(session_no) <= 0:
            raise ValueError("课次必须大于 0")
        now = _now()
        try:
            cur = conn.execute(
                """
                INSERT INTO course_session(teaching_class_id, session_no, session_date, start_time, end_time, classroom, topic, status, created_by_user_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (teaching_class_id, int(session_no), session_date, payload.get("start_time"), payload.get("end_time"), str(payload.get("classroom") or "").strip(), str(payload.get("topic") or "").strip(), status, ctx.user_id, now, now),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise ValueError("该课程日期和课次已存在") from exc
            raise
        session_id = int(cur.lastrowid)
        _audit(conn, ctx, "course_session", session_id, "create_session", None, status)
        conn.commit()
    return get_session(ctx, session_id)


def get_session(ctx: AuthContext, session_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM course_session WHERE id = ?", (session_id,)).fetchone()
    if not row:
        raise ValueError("课程场次不存在")
    require_course_member(ctx, row["teaching_class_id"])
    return dict(row)


def list_course_sessions(ctx: AuthContext, teaching_class_id: int) -> list[dict[str, Any]]:
    require_course_member(ctx, teaching_class_id)
    student_id = ctx.row_scope.get("student_id") if ctx.role == "student" else None
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT cs.*, COUNT(DISTINCT e.student_id) AS enrolled_count,
                   COUNT(DISTINCT a.student_id) AS recorded_count,
                   MAX(CASE WHEN a.student_id = ? THEN a.status END) AS my_status,
                   MAX(CASE WHEN a.student_id = ? THEN a.note END) AS my_note
            FROM course_session cs
            LEFT JOIN enrollment e ON e.teaching_class_id = cs.teaching_class_id
            LEFT JOIN attendance a ON a.course_session_id = cs.id
            WHERE cs.teaching_class_id = ?
            GROUP BY cs.id
            ORDER BY cs.session_date DESC, cs.session_no DESC
            """,
            (student_id, student_id, teaching_class_id),
        ).fetchall()
    items = [dict(row) for row in rows]
    if ctx.role == "student":
        for item in items:
            item.pop("created_by_user_id", None)
            item.pop("enrolled_count", None)
            item.pop("recorded_count", None)
    return items


def session_attendance(ctx: AuthContext, session_id: int) -> dict[str, Any]:
    with connect() as conn:
        session = conn.execute("SELECT * FROM course_session WHERE id = ?", (session_id,)).fetchone()
        if not session:
            raise ValueError("课程场次不存在")
        require_course_member(ctx, session["teaching_class_id"])
        if ctx.role == "teacher":
            rows = conn.execute(
                """
                SELECT s.id AS student_id, s.student_no, s.name AS student_name,
                       a.id AS attendance_id, a.status, a.note, a.updated_at
                FROM enrollment e JOIN student s ON s.id = e.student_id
                LEFT JOIN attendance a ON a.course_session_id = ? AND a.student_id = s.id
                WHERE e.teaching_class_id = ? ORDER BY s.student_no
                """,
                (session_id, session["teaching_class_id"]),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT student_id, status, note, updated_at FROM attendance WHERE course_session_id = ? AND student_id = ?",
                (session_id, ctx.row_scope["student_id"]),
            ).fetchall()
    return {"session": dict(session), "items": [dict(row) for row in rows]}


def save_session_attendance(ctx: AuthContext, session_id: int, entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not entries:
        raise ValueError("至少需要一条考勤记录")
    with connect() as conn:
        session = conn.execute("SELECT * FROM course_session WHERE id = ?", (session_id,)).fetchone()
        if not session:
            raise ValueError("课程场次不存在")
        require_teacher_of_class(ctx, session["teaching_class_id"])
        enrolled = {int(row[0]) for row in conn.execute("SELECT student_id FROM enrollment WHERE teaching_class_id = ?", (session["teaching_class_id"],)).fetchall()}
        seen: set[int] = set()
        changed = 0
        now = _now()
        for entry in entries:
            student_id = int(entry.get("student_id") or 0)
            status = str(entry.get("status") or "")
            if student_id in seen or student_id not in enrolled:
                raise ValueError("考勤学生不在本课程或存在重复记录")
            if status not in ATTENDANCE_STATUSES:
                raise ValueError("考勤状态只能是出勤、迟到、请假或缺勤")
            seen.add(student_id)
            existing = conn.execute("SELECT id, status FROM attendance WHERE course_session_id = ? AND student_id = ?", (session_id, student_id)).fetchone()
            note = str(entry.get("note") or "").strip()[:500]
            if existing:
                conn.execute("UPDATE attendance SET status = ?, note = ?, recorded_by_user_id = ?, updated_at = ? WHERE id = ?", (status, note, ctx.user_id, now, existing["id"]))
                _audit(conn, ctx, "attendance", existing["id"], "correct_attendance" if existing["status"] != status else "update_attendance_note", existing["status"], status)
            else:
                cur = conn.execute(
                    "INSERT INTO attendance(teaching_class_id, student_id, session_no, class_date, status, course_session_id, note, recorded_by_user_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (session["teaching_class_id"], student_id, session["session_no"], session["session_date"], status, session_id, note, ctx.user_id, now),
                )
                _audit(conn, ctx, "attendance", int(cur.lastrowid), "record_attendance", None, status)
            changed += 1
        conn.execute("UPDATE course_session SET status = 'completed', updated_at = ? WHERE id = ?", (now, session_id))
        conn.commit()
    return {"session_id": session_id, "updated_count": changed}


def student_attendance_facts(ctx: AuthContext, student_id: int) -> list[dict[str, Any]]:
    if ctx.role == "student":
        require_student_self(ctx, student_id)
    elif ctx.role == "counselor":
        require_counselor_of_student(ctx, student_id)
    else:
        forbidden()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.student_id, c.name AS course_name, c.course_code,
                   cs.id AS session_id, cs.session_no, cs.session_date, cs.start_time, cs.classroom,
                   a.status, a.note, a.updated_at
            FROM attendance a
            JOIN course_session cs ON cs.id = a.course_session_id
            JOIN teaching_class tc ON tc.id = a.teaching_class_id
            JOIN course c ON c.id = tc.course_id
            WHERE a.student_id = ? ORDER BY cs.session_date DESC, cs.session_no DESC
            """,
            (student_id,),
        ).fetchall()
    items = [dict(row) for row in rows]
    if ctx.role == "counselor":
        for item in items:
            item.pop("note", None)
            item.pop("updated_at", None)
    return items


def create_question(ctx: AuthContext, teaching_class_id: int, title: str, body: str, visibility: str) -> dict[str, Any]:
    require_course_member(ctx, teaching_class_id)
    if ctx.role != "student":
        forbidden()
    if visibility not in QUESTION_VISIBILITIES:
        raise ValueError("问题可见范围不正确")
    if not title.strip() or not body.strip():
        raise ValueError("问题标题和正文不能为空")
    with connect() as conn:
        now = _now()
        cur = conn.execute(
            "INSERT INTO course_question(teaching_class_id, student_id, title, body, visibility, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'open', ?, ?)",
            (teaching_class_id, ctx.row_scope["student_id"], title.strip(), body.strip(), visibility, now, now),
        )
        question_id = int(cur.lastrowid)
        for username in _teacher_usernames(conn, teaching_class_id):
            _notify(conn, username, "course_question", "课程新增问题", title.strip(), "course_question", question_id)
        conn.commit()
    return question_detail(ctx, question_id)


def _question_row(conn, question_id: int):
    return conn.execute(
        "SELECT q.*, s.name AS student_name, s.student_no FROM course_question q JOIN student s ON s.id = q.student_id WHERE q.id = ?",
        (question_id,),
    ).fetchone()


def _require_question_access(ctx: AuthContext, row) -> None:
    require_course_member(ctx, row["teaching_class_id"])
    if ctx.role == "student" and row["visibility"] == "private" and row["student_id"] != ctx.row_scope.get("student_id"):
        forbidden()


def _serialize_question(ctx: AuthContext, row, replies: list[dict[str, Any]]) -> dict[str, Any]:
    item = dict(row)
    item["is_own"] = ctx.role == "student" and item["student_id"] == ctx.row_scope.get("student_id")
    if ctx.role == "student":
        item.pop("student_id", None)
        item.pop("student_no", None)
        item["student_name"] = "我" if item["is_own"] else "课程同学"
        for reply in replies:
            reply.pop("reply_user_id", None)
    item["replies"] = replies
    return item


def list_questions(ctx: AuthContext, teaching_class_id: int) -> list[dict[str, Any]]:
    require_course_member(ctx, teaching_class_id)
    with connect() as conn:
        params: list[Any] = [teaching_class_id]
        visibility_sql = ""
        if ctx.role == "student":
            visibility_sql = "AND (q.visibility = 'public' OR q.student_id = ?)"
            params.append(ctx.row_scope["student_id"])
        rows = conn.execute(
            f"SELECT q.*, s.name AS student_name, s.student_no FROM course_question q JOIN student s ON s.id = q.student_id WHERE q.teaching_class_id = ? {visibility_sql} ORDER BY q.pinned DESC, CASE q.status WHEN 'open' THEN 1 WHEN 'answered' THEN 2 ELSE 3 END, q.updated_at DESC",
            params,
        ).fetchall()
        items = []
        for row in rows:
            replies = [dict(reply) for reply in conn.execute("SELECT id, reply_user_id, reply_role, body, created_at FROM course_question_reply WHERE question_id = ? ORDER BY id", (row["id"],)).fetchall()]
            items.append(_serialize_question(ctx, row, replies))
    return items


def question_detail(ctx: AuthContext, question_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = _question_row(conn, question_id)
        if not row:
            raise ValueError("课程问题不存在")
        _require_question_access(ctx, row)
        replies = [dict(reply) for reply in conn.execute("SELECT id, reply_user_id, reply_role, body, created_at FROM course_question_reply WHERE question_id = ? ORDER BY id", (question_id,)).fetchall()]
    return _serialize_question(ctx, row, replies)


def reply_question(ctx: AuthContext, question_id: int, body: str) -> dict[str, Any]:
    if not body.strip():
        raise ValueError("回复内容不能为空")
    with connect() as conn:
        row = _question_row(conn, question_id)
        if not row:
            raise ValueError("课程问题不存在")
        _require_question_access(ctx, row)
        if row["status"] == "closed":
            raise ValueError("已关闭的问题不能继续回复")
        if ctx.role == "student" and row["student_id"] != ctx.row_scope.get("student_id"):
            forbidden()
        if ctx.role not in {"teacher", "student"}:
            forbidden()
        now = _now()
        conn.execute("INSERT INTO course_question_reply(question_id, reply_user_id, reply_role, body, created_at) VALUES (?, ?, ?, ?, ?)", (question_id, ctx.user_id, ctx.role, body.strip(), now))
        next_status = "answered" if ctx.role == "teacher" else "open"
        conn.execute("UPDATE course_question SET status = ?, updated_at = ? WHERE id = ?", (next_status, now, question_id))
        if ctx.role == "teacher":
            username = _student_username(conn, row["student_id"])
            if username:
                _notify(conn, username, "course_question_reply", "课程问题已回复", row["title"], "course_question", question_id)
        else:
            for username in _teacher_usernames(conn, row["teaching_class_id"]):
                _notify(conn, username, "course_question_followup", "学生追问课程问题", row["title"], "course_question", question_id)
        conn.commit()
    return question_detail(ctx, question_id)


def moderate_question(ctx: AuthContext, question_id: int, status: str | None, pinned: bool | None) -> dict[str, Any]:
    with connect() as conn:
        row = _question_row(conn, question_id)
        if not row:
            raise ValueError("课程问题不存在")
        require_teacher_of_class(ctx, row["teaching_class_id"])
        next_status = status or row["status"]
        if next_status not in QUESTION_STATUSES:
            raise ValueError("问题状态不正确")
        next_pinned = int(bool(pinned)) if pinned is not None else row["pinned"]
        conn.execute("UPDATE course_question SET status = ?, pinned = ?, updated_at = ? WHERE id = ?", (next_status, next_pinned, _now(), question_id))
        _audit(conn, ctx, "course_question", question_id, "moderate_question", f"{row['status']}:{row['pinned']}", f"{next_status}:{next_pinned}")
        conn.commit()
    return question_detail(ctx, question_id)
