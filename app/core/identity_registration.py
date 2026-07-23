"""Self-service account registration with organization-scoped identity approval."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.core import teaching_migrations
from app.core.business_domains import AuthContext, AuthorizationError, _hash_password


LOGIN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{3,39}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(teaching_migrations.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _application_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "identity_type": row["identity_type"],
        "identity_type_label": "学生" if row["identity_type"] == "student" else "教职工",
        "identifier": row["submitted_identifier"],
        "submitted_name": row["submitted_name"],
        "matched_name": row["matched_name"],
        "organization_name": row["organization_name"] or "待确认组织",
        "class_name": row["class_name"],
        "status": row["status"],
        "status_label": {
            "pending": "等待审核",
            "approved": "已通过",
            "rejected": "未通过",
            "withdrawn": "已撤回",
        }.get(row["status"], row["status"]),
        "assigned_approver_role": row["assigned_approver_role"],
        "approver_name": row["approver_name"],
        "review_note": row["review_note"],
        "submitted_at": row["submitted_at"],
        "reviewed_at": row["reviewed_at"],
    }


APPLICATION_SELECT = """
    SELECT ia.*, au.username, au.display_name,
           COALESCE(s.name, st.name, t.name) AS matched_name,
           c.name AS organization_name, cg.name AS class_name,
           reviewer.display_name AS approver_name
    FROM identity_application ia
    JOIN app_user au ON au.id = ia.user_id
    LEFT JOIN student s ON ia.identity_type = 'student' AND s.id = ia.matched_entity_id
    LEFT JOIN teacher t ON ia.identity_type = 'teacher' AND t.id = ia.matched_entity_id
    LEFT JOIN staff st ON ia.identity_type = 'teacher' AND st.id = ia.matched_staff_id
    LEFT JOIN college c ON c.id = ia.matched_college_id
    LEFT JOIN class_group cg ON cg.id = ia.matched_class_id
    LEFT JOIN app_user reviewer ON reviewer.id = ia.reviewed_by_user_id
"""


def register_account(
    *, password: str, display_name: str, identity_type: str, identifier: str
) -> dict[str, Any]:
    display_name = display_name.strip()
    identifier = identifier.strip()
    username = identifier
    if len(password) < 8 or len(password) > 32:
        raise ValueError("密码长度需为 8-32 位")
    if len(display_name) < 2 or len(display_name) > 40:
        raise ValueError("姓名长度需为 2-40 位")
    if identity_type not in {"student", "teacher"}:
        raise ValueError("注册身份只能选择学生或教职工")
    if not identifier or len(identifier) > 40:
        raise ValueError("请输入有效的学号或工号")
    if not LOGIN_ID_RE.fullmatch(identifier):
        raise ValueError("学号或工号格式无效")

    now = _now()
    with _connect() as conn:
        if conn.execute("SELECT 1 FROM app_user WHERE lower(username) = lower(?)", (username,)).fetchone():
            raise ValueError("该学号或工号已注册或正在审核")

        if identity_type == "student":
            identity = conn.execute(
                """
                SELECT s.id, s.name, s.college_id, s.class_id
                FROM student s WHERE s.student_no = ? AND trim(s.name) = ? AND s.status = 'active'
                """,
                (identifier, display_name),
            ).fetchone()
        else:
            identity = conn.execute(
                """
                SELECT st.id, st.name, st.college_id, NULL AS class_id, st.teacher_id, st.id AS staff_id
                FROM staff st
                WHERE st.staff_no = ? AND trim(st.name) = ? AND st.employment_status = 'active'
                """,
                (identifier, display_name),
            ).fetchone()
        if not identity:
            raise ValueError("未匹配到有效的校内身份，请核对姓名和学号/工号")

        entity_id = int(identity["id"])
        if identity_type == "student":
            already_bound = conn.execute(
                """
                SELECT 1 FROM identity_binding WHERE identity_type = 'student' AND entity_id = ?
                UNION SELECT 1 FROM app_user WHERE student_id = ?
                UNION SELECT 1 FROM identity_application
                WHERE identity_type = 'student' AND matched_entity_id = ? AND status IN ('pending', 'approved')
                LIMIT 1
                """,
                (entity_id, entity_id, entity_id),
            ).fetchone()
        else:
            already_bound = conn.execute(
                """
                SELECT 1 FROM person_identity WHERE person_type = 'staff' AND entity_id = ?
                UNION SELECT 1 FROM app_user WHERE teacher_id = ? AND ? IS NOT NULL
                UNION SELECT 1 FROM identity_application
                WHERE identity_type = 'teacher' AND matched_staff_id = ? AND status IN ('pending', 'approved')
                LIMIT 1
                """,
                (entity_id, identity["teacher_id"], identity["teacher_id"], entity_id),
            ).fetchone()
        if already_bound:
            raise ValueError("该校内身份已经绑定账号，请联系负责人处理")

        approver_user_id: int | None = None
        approver_role = "academic_office" if identity_type == "student" else "college_manager"
        if identity_type == "student":
            approver = conn.execute(
                """
                SELECT au.id FROM user_role_binding urb
                JOIN role_scope_binding rsb ON rsb.role_binding_id = urb.id
                JOIN app_user au ON au.id = urb.user_id
                LEFT JOIN position_assignment pa ON pa.id = urb.position_assignment_id
                WHERE urb.role_code = 'counselor' AND urb.status = 'active'
                  AND datetime(urb.valid_from) <= datetime('now')
                  AND (urb.valid_until IS NULL OR datetime(urb.valid_until) > datetime('now'))
                  AND (pa.id IS NULL OR (pa.status = 'active'
                       AND (pa.valid_until IS NULL OR datetime(pa.valid_until) > datetime('now'))))
                  AND rsb.scope_type = 'class_group' AND rsb.scope_id = ?
                  AND au.active = 1 AND au.status = 'active'
                ORDER BY au.id LIMIT 1
                """,
                (identity["class_id"],),
            ).fetchone()
            if approver:
                approver_user_id, approver_role = int(approver["id"]), "counselor"
        else:
            approver = conn.execute(
                """
                SELECT au.id FROM user_role_binding urb
                JOIN role_scope_binding rsb ON rsb.role_binding_id = urb.id
                JOIN app_user au ON au.id = urb.user_id
                LEFT JOIN position_assignment pa ON pa.id = urb.position_assignment_id
                WHERE urb.role_code IN ('college_manager', 'identity_reviewer')
                  AND urb.status = 'active'
                  AND datetime(urb.valid_from) <= datetime('now')
                  AND (urb.valid_until IS NULL OR datetime(urb.valid_until) > datetime('now'))
                  AND (pa.id IS NULL OR (pa.status = 'active'
                       AND (pa.valid_until IS NULL OR datetime(pa.valid_until) > datetime('now'))))
                  AND rsb.scope_type = 'college' AND rsb.scope_id = ?
                  AND au.active = 1 AND au.status = 'active'
                ORDER BY CASE urb.role_code WHEN 'identity_reviewer' THEN 0 ELSE 1 END, au.id LIMIT 1
                """,
                (identity["college_id"],),
            ).fetchone()
            if approver:
                approver_user_id = int(approver["id"])
        if approver_user_id is None:
            fallback_roles = ("academic_office", "admin") if identity_type == "student" else ("admin",)
            placeholders = ",".join("?" for _ in fallback_roles)
            approver = conn.execute(
                f"""
                SELECT au.id, urb.role_code AS role FROM user_role_binding urb
                JOIN app_user au ON au.id = urb.user_id
                LEFT JOIN position_assignment pa ON pa.id = urb.position_assignment_id
                WHERE urb.role_code IN ({placeholders}) AND urb.status = 'active'
                  AND datetime(urb.valid_from) <= datetime('now')
                  AND (urb.valid_until IS NULL OR datetime(urb.valid_until) > datetime('now'))
                  AND (pa.id IS NULL OR (pa.status = 'active'
                       AND (pa.valid_until IS NULL OR datetime(pa.valid_until) > datetime('now'))))
                  AND au.active = 1 AND au.status = 'active'
                ORDER BY CASE urb.role_code WHEN ? THEN 0 ELSE 1 END, au.id LIMIT 1
                """,
                (*fallback_roles, fallback_roles[0]),
            ).fetchone()
            if approver:
                approver_user_id, approver_role = int(approver["id"]), str(approver["role"])

        cursor = conn.execute(
            """
            INSERT INTO app_user
            (username, display_name, role, password_hash, student_id, teacher_id, counselor_id,
             college_id, active, status, created_at, updated_at)
            VALUES (?, ?, 'pending', ?, NULL, NULL, NULL, NULL, 1, 'pending_approval', ?, ?)
            """,
            (username, display_name, _hash_password(password), now, now),
        )
        user_id = int(cursor.lastrowid)
        cursor = conn.execute(
            """
            INSERT INTO identity_application
            (user_id, identity_type, submitted_identifier, submitted_name, matched_entity_id,
             matched_college_id, matched_class_id, matched_staff_id, status, assigned_approver_user_id,
             assigned_approver_role, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (user_id, identity_type, identifier, display_name, entity_id, identity["college_id"],
             identity["class_id"], entity_id if identity_type == "teacher" else None,
             approver_user_id, approver_role, now),
        )
        application_id = int(cursor.lastrowid)
        if identity_type == "student":
            queue = conn.execute(
                """
                SELECT id FROM organization_review_queue
                WHERE queue_type = 'student_identity' AND scope_type = 'class_group' AND scope_id = ? AND status = 'active'
                """,
                (identity["class_id"],),
            ).fetchone()
        else:
            queue = conn.execute(
                """
                SELECT id FROM organization_review_queue
                WHERE queue_type = 'staff_identity' AND scope_type = 'college' AND scope_id = ? AND status = 'active'
                """,
                (identity["college_id"],),
            ).fetchone()
        queue_id = int(queue["id"]) if queue else 300001
        task_cursor = conn.execute(
            """
            INSERT INTO review_task
            (queue_id, task_type, resource_type, resource_id, status, due_at, created_at, updated_at)
            VALUES (?, 'identity_review', 'identity_application', ?, 'pending', datetime(?, '+48 hours'), ?, ?)
            """,
            (queue_id, application_id, now, now, now),
        )
        conn.execute(
            "UPDATE identity_application SET review_queue_id = ?, review_task_id = ? WHERE id = ?",
            (queue_id, int(task_cursor.lastrowid), application_id),
        )
        conn.execute(
            """
            INSERT INTO audit_log
            (actor_user, actor_role, resource_type, resource_id, action, before_state, after_state, created_at)
            VALUES (?, 'pending', 'identity_application', ?, 'submitted', NULL, 'pending', ?)
            """,
            (username, application_id, now),
        )
        row = conn.execute(APPLICATION_SELECT + " WHERE ia.id = ?", (application_id,)).fetchone()
        conn.commit()
    return {"item": _application_dict(row), "message": "账号已创建，身份申请已提交审核"}


def my_application(ctx: AuthContext) -> dict[str, Any]:
    if ctx.user_id is None:
        return {"item": None}
    with _connect() as conn:
        row = conn.execute(
            APPLICATION_SELECT + " WHERE ia.user_id = ? ORDER BY ia.id DESC LIMIT 1", (ctx.user_id,)
        ).fetchone()
    return {"item": _application_dict(row) if row else None}


def _review_scope_sql(ctx: AuthContext) -> tuple[str, tuple[Any, ...]]:
    if ctx.role == "admin":
        return "1 = 1", ()
    if ctx.role == "academic_office":
        return "ia.identity_type = 'student'", ()
    if ctx.role == "counselor" and ctx.role_binding_id is not None:
        return (
            "ia.identity_type = 'student' AND ia.matched_class_id IN "
            "(SELECT scope_id FROM role_scope_binding WHERE role_binding_id = ? AND scope_type = 'class_group')",
            (int(ctx.role_binding_id),),
        )
    if ctx.role in {"college_manager", "identity_reviewer"} and ctx.role_binding_id is not None:
        return (
            "ia.matched_college_id IN "
            "(SELECT scope_id FROM role_scope_binding WHERE role_binding_id = ? AND scope_type = 'college')",
            (int(ctx.role_binding_id),),
        )
    raise AuthorizationError("当前岗位没有身份审核权限")


def list_applications(ctx: AuthContext, status: str = "pending") -> dict[str, Any]:
    if status not in {"pending", "approved", "rejected", "all"}:
        raise ValueError("不支持的申请状态")
    scope_sql, params = _review_scope_sql(ctx)
    status_sql = "" if status == "all" else " AND ia.status = ?"
    query_params = params if status == "all" else (*params, status)
    with _connect() as conn:
        rows = conn.execute(
            APPLICATION_SELECT + f" WHERE {scope_sql}{status_sql} ORDER BY ia.submitted_at, ia.id",
            query_params,
        ).fetchall()
    return {"items": [_application_dict(row) for row in rows]}


def review_application(ctx: AuthContext, application_id: int, decision: str, note: str = "") -> dict[str, Any]:
    if decision not in {"approve", "reject"}:
        raise ValueError("审核决定只能是通过或拒绝")
    scope_sql, scope_params = _review_scope_sql(ctx)
    now = _now()
    with _connect() as conn:
        row = conn.execute(
            APPLICATION_SELECT + f" WHERE ia.id = ? AND {scope_sql}", (application_id, *scope_params)
        ).fetchone()
        if not row:
            raise AuthorizationError("无权审核该身份申请")
        if row["status"] != "pending":
            raise ValueError("该申请已经处理")
        if decision == "approve":
            if row["identity_type"] == "student":
                duplicate = conn.execute(
                    "SELECT 1 FROM person_identity WHERE person_type = 'student' AND entity_id = ?",
                    (row["matched_entity_id"],),
                ).fetchone()
            else:
                duplicate = conn.execute(
                    "SELECT 1 FROM person_identity WHERE person_type = 'staff' AND entity_id = ?",
                    (row["matched_staff_id"],),
                ).fetchone()
            if duplicate:
                raise ValueError("该身份已被其他账号绑定")
            staff = None
            if row["identity_type"] == "teacher":
                staff = conn.execute(
                    "SELECT id, teacher_id FROM staff WHERE id = ? AND employment_status = 'active'",
                    (row["matched_staff_id"],),
                ).fetchone()
                if not staff:
                    raise ValueError("教职工目录状态已变化，请重新提交申请")
            role = "student" if row["identity_type"] == "student" else "teacher" if staff["teacher_id"] else "staff"
            student_id = row["matched_entity_id"] if role == "student" else None
            teacher_id = staff["teacher_id"] if role == "teacher" else None
            conn.execute(
                """
                UPDATE app_user SET role = ?, student_id = ?, teacher_id = ?, college_id = ?,
                    status = 'active', active = 1, updated_at = ? WHERE id = ?
                """,
                (role, student_id, teacher_id, row["matched_college_id"], now, row["user_id"]),
            )
            conn.execute("INSERT OR REPLACE INTO user_role(user_id, role_code) VALUES (?, ?)", (row["user_id"], role))
            person_type = "student" if role == "student" else "staff"
            person_entity_id = row["matched_entity_id"] if role == "student" else row["matched_staff_id"]
            conn.execute(
                """
                INSERT INTO person_identity
                (user_id, person_type, entity_id, status, verified_by_user_id, verified_at)
                VALUES (?, ?, ?, 'verified', ?, ?)
                """,
                (row["user_id"], person_type, person_entity_id, ctx.user_id, now),
            )
            if role == "student":
                conn.execute(
                    """
                    INSERT INTO identity_binding
                    (user_id, identity_type, entity_id, verified_by_user_id, verified_at)
                    VALUES (?, 'student', ?, ?, ?)
                    """,
                    (row["user_id"], student_id, ctx.user_id, now),
                )
            elif role == "teacher":
                conn.execute(
                    """
                    INSERT INTO identity_binding
                    (user_id, identity_type, entity_id, verified_by_user_id, verified_at)
                    VALUES (?, 'teacher', ?, ?, ?)
                    """,
                    (row["user_id"], teacher_id, ctx.user_id, now),
                )
            from app.core.teaching_migrations import _ensure_lifecycle_identity, _ensure_role_binding
            scopes = [("self", int(student_id))] if role == "student" else [("teacher", int(teacher_id))] if role == "teacher" else []
            _ensure_role_binding(conn, int(row["user_id"]), role, "identity", scopes, None, "校内身份审核通过")
            _ensure_lifecycle_identity(conn, int(row["user_id"]))
            next_status, action = "approved", "approved"
        else:
            conn.execute(
                "UPDATE app_user SET status = 'rejected', updated_at = ? WHERE id = ?",
                (now, row["user_id"]),
            )
            next_status, action = "rejected", "rejected"
        conn.execute(
            """
            UPDATE identity_application SET status = ?, reviewed_by_user_id = ?, review_note = ?, reviewed_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (next_status, ctx.user_id, note.strip()[:500], now, application_id),
        )
        conn.execute(
            """
            INSERT INTO audit_log
            (actor_user, actor_role, resource_type, resource_id, action, before_state, after_state, created_at)
            VALUES (?, ?, 'identity_application', ?, ?, 'pending', ?, ?)
            """,
            (ctx.username, ctx.role, application_id, action, next_status, now),
        )
        if row["review_task_id"]:
            conn.execute(
                """
                UPDATE review_task SET status = ?, processed_by_user_id = ?, processed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_status, ctx.user_id, now, now, row["review_task_id"]),
            )
        updated = conn.execute(APPLICATION_SELECT + " WHERE ia.id = ?", (application_id,)).fetchone()
        conn.commit()
    return {"item": _application_dict(updated)}


def batch_review_applications(
    ctx: AuthContext, application_ids: list[int], decision: str, note: str = ""
) -> dict[str, Any]:
    ids = list(dict.fromkeys(int(value) for value in application_ids))
    if not ids or len(ids) > 100:
        raise ValueError("每次请选择 1-100 条身份申请")
    if decision not in {"approve", "reject"}:
        raise ValueError("审核决定只能是通过或拒绝")
    if decision == "reject" and not note.strip():
        raise ValueError("批量拒绝必须填写原因")

    scope_sql, scope_params = _review_scope_sql(ctx)
    marks = ",".join("?" for _ in ids)
    with _connect() as conn:
        allowed = {
            int(row[0])
            for row in conn.execute(
                f"SELECT ia.id FROM identity_application ia WHERE ia.id IN ({marks}) AND ia.status = 'pending' AND {scope_sql}",
                (*ids, *scope_params),
            ).fetchall()
        }
    if allowed != set(ids):
        raise AuthorizationError("所选申请包含无权处理或已经处理的记录")

    items = [review_application(ctx, application_id, decision, note)["item"] for application_id in ids]
    return {"items": items, "processed_count": len(items)}
