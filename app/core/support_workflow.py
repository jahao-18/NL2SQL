"""Learning-support workflow for counselors and students."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.core.authorization import connect, forbidden, require_counselor_of_student, require_student_self, require_support_case_access
from app.core.business_domains import AuthContext


RULES = {
    "two_missing_assignments_same_course": {
        "title": "连续未提交课程作业",
        "suggested_action": "先确认未提交原因，再与学生约定补交和后续学习计划。",
    },
    "two_late_submissions_same_course": {
        "title": "多次迟交课程作业",
        "suggested_action": "与学生一起拆分任务，并约定在截止前一天检查提交状态。",
    },
    "two_absences_same_course": {
        "title": "连续缺勤需确认",
        "suggested_action": "先核实缺勤原因和课程参与情况，必要时安排后续复查。",
    },
}

STATUS_TRANSITIONS = {
    "open": {"contacted", "closed"},
    "contacted": {"tracking", "closed"},
    "tracking": {"improved", "closed"},
    "improved": {"closed"},
    "closed": set(),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _audit(conn, ctx: AuthContext, case_id: int, action: str, before: str | None, after: str | None) -> None:
    conn.execute(
        """
        INSERT INTO audit_log(actor_user, actor_role, resource_type, resource_id, action, before_state, after_state, created_at)
        VALUES (?, ?, 'support_case', ?, ?, ?, ?, ?)
        """,
        (ctx.username, ctx.role, case_id, action, before, after, now_iso()),
    )


def _evidence(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {"summary": value}


def _counselor_for_student(conn, student_id: int) -> int | None:
    row = conn.execute(
        """
        SELECT ccg.counselor_id
        FROM student s
        JOIN counselor_class_group ccg ON ccg.class_group_id = s.class_id
        WHERE s.id = ?
        ORDER BY ccg.counselor_id LIMIT 1
        """,
        (student_id,),
    ).fetchone()
    return int(row["counselor_id"]) if row else None


def _create_rule_case(
    conn,
    rule_code: str,
    trigger_key: str,
    student_id: int,
    evidence: dict[str, Any],
    target_counselor_id: int | None,
) -> bool:
    counselor_id = _counselor_for_student(conn, student_id)
    if target_counselor_id is not None and counselor_id != target_counselor_id:
        return False
    rule = RULES[rule_code]
    existing = conn.execute(
        "SELECT id FROM support_case WHERE student_id = ? AND rule_code = ? AND status != 'closed' LIMIT 1",
        (student_id, rule_code),
    ).fetchone()
    if existing:
        return False
    if counselor_id is None:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO support_unassigned_case
            (student_id, rule_code, trigger_key, title, evidence, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'unassigned', ?)
            """,
            (student_id, rule_code, trigger_key, rule["title"], json.dumps(evidence, ensure_ascii=False), now_iso()),
        )
        return cur.rowcount > 0
    code = f"AUTO-{trigger_key}"
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO support_case
        (code, student_id, counselor_id, rule_code, title, evidence, status, created_at,
         review_at, closed_reason, visible_to_student, suggested_action, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'open', ?, NULL, NULL, 0, ?, ?)
        """,
        (
            code,
            student_id,
            counselor_id,
            rule_code,
            rule["title"],
            json.dumps(evidence, ensure_ascii=False),
            now_iso(),
            rule["suggested_action"],
            now_iso(),
        ),
    )
    if cur.rowcount > 0:
        conn.execute(
            """
            INSERT INTO audit_log(actor_user, actor_role, resource_type, resource_id, action, before_state, after_state, created_at)
            VALUES ('system', 'system', 'support_case', ?, 'rule_match', NULL, 'open', ?)
            """,
            (int(cur.lastrowid), now_iso()),
        )
    return cur.rowcount > 0


def refresh_support_cases(ctx: AuthContext) -> dict[str, int]:
    counselor_id = ctx.row_scope.get("counselor_id")
    if ctx.role != "counselor" or not counselor_id:
        forbidden()
    created = 0
    checked = 0
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT e.student_id, tc.id AS teaching_class_id, c.name AS course_name,
                   a.id AS assignment_id, a.title, a.due_time,
                   CASE WHEN sub.id IS NULL OR sub.submit_time IS NULL OR sub.status = 'missing' THEN 1 ELSE 0 END AS missing
            FROM enrollment e
            JOIN teaching_class tc ON tc.id = e.teaching_class_id
            JOIN course c ON c.id = tc.course_id
            JOIN assignment a ON a.teaching_class_id = tc.id
            LEFT JOIN assignment_submission sub ON sub.assignment_id = a.id AND sub.student_id = e.student_id
            JOIN student s ON s.id = e.student_id
            JOIN counselor_class_group ccg ON ccg.class_group_id = s.class_id
            WHERE ccg.counselor_id = ? AND a.status != 'draft'
              AND (a.status = 'closed' OR datetime(a.due_time) <= datetime('now'))
            ORDER BY e.student_id, tc.id, a.due_time, a.id
            """,
            (counselor_id,),
        ).fetchall()
        assignment_groups: dict[tuple[int, int], list[Any]] = defaultdict(list)
        for row in rows:
            assignment_groups[(row["student_id"], row["teaching_class_id"])].append(row)
        for (student_id, teaching_class_id), events in assignment_groups.items():
            checked += 1
            for first, second in zip(events, events[1:]):
                if first["missing"] and second["missing"]:
                    evidence = {
                        "course": second["course_name"],
                        "fact": "连续两次作业未提交",
                        "events": [
                            {"assignment": first["title"], "due_time": first["due_time"]},
                            {"assignment": second["title"], "due_time": second["due_time"]},
                        ],
                    }
                    trigger = f"MISS-{teaching_class_id}-{student_id}-{first['assignment_id']}-{second['assignment_id']}"
                    created += int(_create_rule_case(conn, "two_missing_assignments_same_course", trigger, student_id, evidence, counselor_id))
                    break

        late_rows = conn.execute(
            """
            SELECT e.student_id, tc.id AS teaching_class_id, c.name AS course_name,
                   GROUP_CONCAT(a.title, '、') AS assignments, COUNT(*) AS event_count
            FROM assignment_submission sub
            JOIN assignment a ON a.id = sub.assignment_id
            JOIN teaching_class tc ON tc.id = a.teaching_class_id
            JOIN course c ON c.id = tc.course_id
            JOIN enrollment e ON e.teaching_class_id = tc.id AND e.student_id = sub.student_id
            JOIN student s ON s.id = e.student_id
            JOIN counselor_class_group ccg ON ccg.class_group_id = s.class_id
            WHERE ccg.counselor_id = ? AND sub.late = 1
            GROUP BY e.student_id, tc.id
            HAVING COUNT(*) >= 2
            """,
            (counselor_id,),
        ).fetchall()
        for row in late_rows:
            evidence = {"course": row["course_name"], "fact": "累计两次及以上迟交", "events": row["assignments"].split("、")}
            trigger = f"LATE-{row['teaching_class_id']}-{row['student_id']}"
            created += int(_create_rule_case(conn, "two_late_submissions_same_course", trigger, row["student_id"], evidence, counselor_id))

        absent_rows = conn.execute(
            """
            SELECT a1.student_id, a1.teaching_class_id, c.name AS course_name,
                   a1.session_no AS first_session, a2.session_no AS second_session,
                   a1.class_date AS first_date, a2.class_date AS second_date
            FROM attendance a1
            JOIN attendance a2 ON a2.teaching_class_id = a1.teaching_class_id
              AND a2.student_id = a1.student_id AND a2.session_no = a1.session_no + 1
            JOIN teaching_class tc ON tc.id = a1.teaching_class_id
            JOIN course c ON c.id = tc.course_id
            JOIN student s ON s.id = a1.student_id
            JOIN counselor_class_group ccg ON ccg.class_group_id = s.class_id
            WHERE ccg.counselor_id = ? AND a1.status = 'absent' AND a2.status = 'absent'
            """,
            (counselor_id,),
        ).fetchall()
        for row in absent_rows:
            evidence = {
                "course": row["course_name"],
                "fact": "连续两次缺勤",
                "events": [
                    {"session": row["first_session"], "date": row["first_date"]},
                    {"session": row["second_session"], "date": row["second_date"]},
                ],
            }
            trigger = f"ABS-{row['teaching_class_id']}-{row['student_id']}-{row['first_session']}-{row['second_session']}"
            created += int(_create_rule_case(conn, "two_absences_same_course", trigger, row["student_id"], evidence, counselor_id))
        conn.commit()
    return {"checked_groups": checked, "created_count": created}


def list_support_cases(ctx: AuthContext, status: str | None = None) -> list[dict[str, Any]]:
    with connect() as conn:
        if ctx.role == "counselor" and ctx.row_scope.get("counselor_id"):
            params: list[Any] = [ctx.row_scope["counselor_id"]]
            status_sql = ""
            if status and status != "all":
                status_sql = " AND sc.status = ?"
                params.append(status)
            rows = conn.execute(
                f"""
                SELECT sc.id, sc.code, sc.student_id, s.student_no, s.name AS student_name,
                       cg.name AS class_name, sc.rule_code, sc.title, sc.evidence, sc.status,
                       sc.created_at, sc.review_at, sc.visible_to_student, sc.suggested_action, sc.updated_at,
                       (SELECT COUNT(*) FROM support_case_log WHERE case_id = sc.id) AS log_count
                FROM support_case sc
                JOIN student s ON s.id = sc.student_id
                JOIN class_group cg ON cg.id = s.class_id
                WHERE sc.counselor_id = ? {status_sql}
                ORDER BY CASE sc.status WHEN 'open' THEN 1 WHEN 'contacted' THEN 2 WHEN 'tracking' THEN 3 WHEN 'improved' THEN 4 ELSE 5 END,
                         COALESCE(sc.review_at, sc.created_at), sc.id DESC
                """,
                params,
            ).fetchall()
        elif ctx.role == "student" and ctx.row_scope.get("student_id"):
            rows = conn.execute(
                """
                SELECT sc.id, sc.code, sc.title, sc.evidence, sc.status, sc.created_at, sc.review_at,
                       sc.suggested_action, c.name AS counselor_name
                FROM support_case sc
                JOIN counselor c ON c.id = sc.counselor_id
                WHERE sc.student_id = ? AND sc.visible_to_student = 1
                ORDER BY CASE sc.status WHEN 'contacted' THEN 1 WHEN 'tracking' THEN 2 WHEN 'improved' THEN 3 ELSE 4 END,
                         sc.id DESC
                """,
                (ctx.row_scope["student_id"],),
            ).fetchall()
        else:
            forbidden()
    items = [dict(row) for row in rows]
    for item in items:
        item["evidence"] = _evidence(item["evidence"])
    return items


def get_support_case(ctx: AuthContext, case_id: int) -> dict[str, Any]:
    scope = require_support_case_access(ctx, case_id)
    data = dict(scope.data)
    data["evidence"] = _evidence(data["evidence"])
    if ctx.role == "counselor":
        with connect() as conn:
            logs = conn.execute(
                """
                SELECT id, actor_user, action, note, contact_method, student_feedback,
                       follow_up_at, visible_to_student, created_at
                FROM support_case_log WHERE case_id = ? ORDER BY created_at, id
                """,
                (case_id,),
            ).fetchall()
        data["logs"] = [dict(row) for row in logs]
    return data


def transition_support_case(ctx: AuthContext, case_id: int, target_status: str, payload: dict[str, Any]) -> dict[str, Any]:
    scope = require_support_case_access(ctx, case_id)
    if ctx.role != "counselor":
        forbidden()
    before = scope.data["status"]
    if target_status not in STATUS_TRANSITIONS.get(before, set()):
        raise ValueError("当前状态不能执行该操作")
    note = str(payload.get("note") or "").strip()
    contact_method = str(payload.get("contact_method") or "").strip() or None
    student_feedback = str(payload.get("student_feedback") or "").strip() or None
    follow_up_at = str(payload.get("follow_up_at") or "").strip() or None
    visible = bool(payload.get("visible_to_student", False))
    if not note:
        raise ValueError("处理记录不能为空")
    if target_status == "contacted" and not contact_method:
        raise ValueError("首次联系必须选择联系方式")
    if target_status == "tracking" and not follow_up_at:
        raise ValueError("进入跟进中必须填写复查时间")
    closed_reason = note if target_status == "closed" else None
    with connect() as conn:
        conn.execute(
            """
            UPDATE support_case
            SET status = ?, review_at = COALESCE(?, review_at),
                closed_reason = COALESCE(?, closed_reason), visible_to_student = CASE WHEN ? THEN 1 ELSE visible_to_student END,
                updated_at = ?
            WHERE id = ?
            """,
            (target_status, follow_up_at, closed_reason, 1 if visible else 0, now_iso(), case_id),
        )
        conn.execute(
            """
            INSERT INTO support_case_log
            (case_id, actor_user, action, note, created_at, contact_method, student_feedback, follow_up_at, visible_to_student)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (case_id, ctx.username, target_status, note, now_iso(), contact_method, student_feedback, follow_up_at, 1 if visible else 0),
        )
        _audit(conn, ctx, case_id, f"support_{target_status}", before, target_status)
        if visible:
            user = conn.execute("SELECT username FROM app_user WHERE student_id = ?", (scope.data["student_id"],)).fetchone()
            if user:
                conn.execute(
                    """
                    INSERT INTO notification(recipient_username, type, title, body, resource_type, resource_id, created_at)
                    VALUES (?, 'support_update', '学习支持事项有更新', ?, 'support_case', ?, ?)
                    """,
                    (user["username"], "请查看辅导员已共享的学习支持建议。", case_id, now_iso()),
                )
        conn.commit()
    return get_support_case(ctx, case_id)


def create_support_request(ctx: AuthContext, payload: dict[str, Any]) -> dict[str, Any]:
    student_id = ctx.row_scope.get("student_id")
    if ctx.role != "student" or not student_id:
        forbidden()
    message = str(payload.get("message") or "").strip()
    request_type = str(payload.get("request_type") or "appointment").strip()
    preferred_time = str(payload.get("preferred_time") or "").strip() or None
    if not message:
        raise ValueError("请填写希望沟通的问题")
    with connect() as conn:
        counselor_id = _counselor_for_student(conn, student_id)
        cur = conn.execute(
            """
            INSERT INTO support_request
            (student_id, counselor_id, request_type, message, preferred_time, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'submitted', ?, ?)
            """,
            (student_id, counselor_id, request_type, message, preferred_time, now_iso(), now_iso()),
        )
        request_id = int(cur.lastrowid)
        conn.execute(
            """
            INSERT INTO audit_log(actor_user, actor_role, resource_type, resource_id, action, before_state, after_state, created_at)
            VALUES (?, ?, 'support_request', ?, 'create_support_request', NULL, 'submitted', ?)
            """,
            (ctx.username, ctx.role, request_id, now_iso()),
        )
        if counselor_id:
            counselor_user = conn.execute("SELECT username FROM app_user WHERE counselor_id = ?", (counselor_id,)).fetchone()
            if counselor_user:
                conn.execute(
                    """
                    INSERT INTO notification(recipient_username, type, title, body, resource_type, resource_id, created_at)
                    VALUES (?, 'support_request', '收到新的学生沟通请求', '请在学习支持工作台查看并处理。', 'support_request', ?, ?)
                    """,
                    (counselor_user["username"], request_id, now_iso()),
                )
        conn.commit()
    return get_support_request(ctx, request_id)


def get_support_request(ctx: AuthContext, request_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT sr.*, s.name AS student_name, s.student_no, c.name AS counselor_name
            FROM support_request sr
            JOIN student s ON s.id = sr.student_id
            LEFT JOIN counselor c ON c.id = sr.counselor_id
            WHERE sr.id = ?
            """,
            (request_id,),
        ).fetchone()
    if not row:
        forbidden()
    data = dict(row)
    if ctx.role == "student":
        require_student_self(ctx, data["student_id"])
    elif ctx.role == "counselor":
        require_counselor_of_student(ctx, data["student_id"])
    else:
        forbidden()
    return data


def list_support_requests(ctx: AuthContext) -> list[dict[str, Any]]:
    with connect() as conn:
        if ctx.role == "student" and ctx.row_scope.get("student_id"):
            rows = conn.execute(
                """
                SELECT sr.*, c.name AS counselor_name FROM support_request sr
                LEFT JOIN counselor c ON c.id = sr.counselor_id
                WHERE sr.student_id = ? ORDER BY sr.created_at DESC
                """,
                (ctx.row_scope["student_id"],),
            ).fetchall()
        elif ctx.role == "counselor" and ctx.row_scope.get("counselor_id"):
            rows = conn.execute(
                """
                SELECT sr.*, s.name AS student_name, s.student_no FROM support_request sr
                JOIN student s ON s.id = sr.student_id
                WHERE sr.counselor_id = ? ORDER BY CASE sr.status WHEN 'submitted' THEN 1 WHEN 'accepted' THEN 2 ELSE 3 END, sr.created_at DESC
                """,
                (ctx.row_scope["counselor_id"],),
            ).fetchall()
        else:
            forbidden()
    return [dict(row) for row in rows]


def update_support_request(ctx: AuthContext, request_id: int, status: str, response: str) -> dict[str, Any]:
    data = get_support_request(ctx, request_id)
    if ctx.role != "counselor":
        forbidden()
    if status not in {"accepted", "completed", "declined"}:
        raise ValueError("请求状态不正确")
    response = response.strip()
    if not response:
        raise ValueError("请填写给学生的回复")
    with connect() as conn:
        conn.execute(
            "UPDATE support_request SET status = ?, counselor_response = ?, updated_at = ? WHERE id = ?",
            (status, response, now_iso(), request_id),
        )
        user = conn.execute("SELECT username FROM app_user WHERE student_id = ?", (data["student_id"],)).fetchone()
        if user:
            conn.execute(
                """
                INSERT INTO notification(recipient_username, type, title, body, resource_type, resource_id, created_at)
                VALUES (?, 'support_request_update', '沟通请求有回复', ?, 'support_request', ?, ?)
                """,
                (user["username"], response, request_id, now_iso()),
            )
        conn.execute(
            """
            INSERT INTO audit_log(actor_user, actor_role, resource_type, resource_id, action, before_state, after_state, created_at)
            VALUES (?, ?, 'support_request', ?, 'update_support_request', ?, ?, ?)
            """,
            (ctx.username, ctx.role, request_id, data["status"], status, now_iso()),
        )
        conn.commit()
    return get_support_request(ctx, request_id)
