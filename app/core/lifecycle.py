"""B.7 lifecycle details, impact calculation and account security actions."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.core import teaching_migrations
from app.core.business_domains import AuthContext, AuthorizationError, ROLES, _verify_password
from app.core.organization_access import MIN_FORMAL_PLATFORM_ADMINS


EVENT_LABELS = {
    "position_end": "结束岗位任职",
    "staff_transfer": "教职工调岗",
    "student_leave": "学生休学",
    "student_resume": "学生复学",
    "student_graduation": "学生毕业",
    "student_withdrawal": "学生退学",
    "staff_termination": "教职工离职",
    "staff_retirement": "教职工退休",
    "account_security_suspend": "账号安全停用",
    "account_security_restore": "账号安全恢复",
    "account_closure": "用户主动销户",
}

STUDENT_EVENTS = {"student_leave", "student_resume", "student_graduation", "student_withdrawal"}
STAFF_EVENTS = {"position_end", "staff_transfer", "staff_termination", "staff_retirement"}
ACCOUNT_EVENTS = {"account_security_suspend", "account_closure"}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(teaching_migrations.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _audit(
    conn: sqlite3.Connection,
    ctx: AuthContext,
    resource_id: int,
    action: str,
    *,
    before: Any = None,
    after: Any = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_log(actor_user, actor_role, resource_type, resource_id, action,
                              before_state, after_state, created_at)
        VALUES (?, ?, 'account_security', ?, ?, ?, ?, ?)
        """,
        (
            ctx.username,
            ctx.role,
            resource_id,
            action,
            json.dumps(before, ensure_ascii=False) if before is not None else None,
            json.dumps(after, ensure_ascii=False) if after is not None else None,
            _now(),
        ),
    )


def _require_security_admin_reauth(
    conn: sqlite3.Connection,
    ctx: AuthContext,
    password: str | None,
    *,
    resource_id: int,
    action: str,
) -> None:
    if ctx.role != "admin" or ctx.user_id is None:
        raise AuthorizationError("只有平台管理员可以执行账号安全操作")
    row = conn.execute(
        "SELECT password_hash FROM app_user WHERE id = ? AND status = 'active'",
        (ctx.user_id,),
    ).fetchone()
    if not row or not password or not _verify_password(password, str(row[0])):
        _audit(conn, ctx, resource_id, "reauth_failed", after={"requested_action": action})
        conn.commit()
        raise AuthorizationError("管理员密码验证失败，本次高风险操作已记录")


def _formal_platform_admin_count_excluding(conn: sqlite3.Connection, user_id: int) -> int:
    return int(conn.execute(
        """
        SELECT count(DISTINCT pa.user_id)
        FROM position_assignment pa
        JOIN organization_position_slot ops ON ops.id = pa.position_slot_id
        JOIN user_role_binding urb ON urb.position_assignment_id = pa.id
        JOIN app_user au ON au.id = pa.user_id
        WHERE ops.position_code = 'platform_admin' AND pa.status = 'active'
          AND urb.role_code = 'admin' AND urb.status = 'active'
          AND au.active = 1 AND au.status = 'active' AND pa.user_id <> ?
          AND (pa.valid_until IS NULL OR datetime(pa.valid_until) > datetime('now'))
        """,
        (user_id,),
    ).fetchone()[0])


def _has_formal_platform_admin_position(conn: sqlite3.Connection, user_id: int) -> bool:
    return conn.execute(
        """
        SELECT 1 FROM position_assignment pa
        JOIN organization_position_slot ops ON ops.id = pa.position_slot_id
        WHERE pa.user_id = ? AND pa.status = 'active' AND ops.position_code = 'platform_admin'
          AND (pa.valid_until IS NULL OR datetime(pa.valid_until) > datetime('now'))
        LIMIT 1
        """,
        (user_id,),
    ).fetchone() is not None


def _json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def _target(conn: sqlite3.Connection, person_identity_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT pi.id AS person_identity_id, pi.user_id, pi.person_type, pi.entity_id,
               pi.status AS identity_status, pi.verified_at,
               au.username, au.display_name, au.status AS account_status, au.active,
               au.session_version, au.last_login_at,
               CASE WHEN pi.person_type = 'student' THEN s.college_id ELSE st.college_id END AS college_id,
               CASE WHEN pi.person_type = 'student' THEN s.student_no ELSE st.staff_no END AS identifier,
               CASE WHEN pi.person_type = 'student' THEN s.status ELSE st.employment_status END AS source_status,
               s.class_id, cg.name AS class_name, st.teacher_id, st.counselor_id,
               c.name AS college_name
        FROM person_identity pi
        JOIN app_user au ON au.id = pi.user_id
        LEFT JOIN student s ON pi.person_type = 'student' AND s.id = pi.entity_id
        LEFT JOIN class_group cg ON cg.id = s.class_id
        LEFT JOIN staff st ON pi.person_type = 'staff' AND st.id = pi.entity_id
        LEFT JOIN college c ON c.id = CASE WHEN pi.person_type = 'student' THEN s.college_id ELSE st.college_id END
        WHERE pi.id = ?
        """,
        (person_identity_id,),
    ).fetchone()
    if not row:
        raise FileNotFoundError("人员身份不存在")
    return dict(row)


def _can_read(conn: sqlite3.Connection, ctx: AuthContext, target: dict[str, Any]) -> bool:
    if ctx.user_id == target["user_id"]:
        return True
    if ctx.role == "admin":
        return True
    if ctx.role == "academic_office":
        return target["person_type"] == "student"
    if ctx.role in {"college_manager", "identity_reviewer"}:
        return bool(ctx.row_scope.get("college_id")) and int(ctx.row_scope["college_id"]) == int(target["college_id"] or 0)
    if ctx.role == "counselor" and target["person_type"] == "student" and ctx.role_binding_id:
        return conn.execute(
            """
            SELECT 1 FROM role_scope_binding
            WHERE role_binding_id = ? AND scope_type = 'class_group' AND scope_id = ?
            """,
            (ctx.role_binding_id, target["class_id"]),
        ).fetchone() is not None
    return False


def _require_read(conn: sqlite3.Connection, ctx: AuthContext, target: dict[str, Any]) -> None:
    if not _can_read(conn, ctx, target):
        raise AuthorizationError("当前岗位无权查看该人员的生命周期信息")


def _affiliations(conn: sqlite3.Connection, person_identity_id: int) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(
        """
        SELECT pa.id, pa.affiliation_type, pa.source_entity_id, pa.status, pa.valid_from,
               pa.valid_until, pa.source_system, ou.name AS organization_name
        FROM person_affiliation pa
        LEFT JOIN organization_unit ou ON ou.id = pa.organization_unit_id
        WHERE pa.person_identity_id = ? ORDER BY pa.valid_from DESC, pa.id DESC
        """,
        (person_identity_id,),
    ).fetchall()]


def _roles(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT urb.id, urb.role_code, urb.status, urb.source, urb.valid_from, urb.valid_until,
               urb.position_assignment_id, urb.selectable, ops.title AS position_title,
               ou.name AS organization_name
        FROM user_role_binding urb
        LEFT JOIN position_assignment pa ON pa.id = urb.position_assignment_id
        LEFT JOIN organization_position_slot ops ON ops.id = pa.position_slot_id
        LEFT JOIN organization_unit ou ON ou.id = ops.organization_unit_id
        WHERE urb.user_id = ? ORDER BY CASE urb.status WHEN 'active' THEN 0 ELSE 1 END, urb.id
        """,
        (user_id,),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["role_label"] = ROLES.get(row["role_code"], {}).get("label", row["role_code"])
        item["selectable"] = bool(row["selectable"])
        item["scopes"] = [dict(scope) for scope in conn.execute(
            "SELECT scope_type, scope_id FROM role_scope_binding WHERE role_binding_id = ? ORDER BY id",
            (row["id"],),
        ).fetchall()]
        items.append(item)
    return items


def _positions(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(
        """
        SELECT pa.id, pa.assignment_type, pa.status, pa.valid_from, pa.valid_until,
               pa.appointment_reason, ops.position_code, ops.title, ops.min_occupants,
               ou.id AS organization_unit_id, ou.name AS organization_name
        FROM position_assignment pa
        JOIN organization_position_slot ops ON ops.id = pa.position_slot_id
        JOIN organization_unit ou ON ou.id = ops.organization_unit_id
        WHERE pa.user_id = ? ORDER BY CASE pa.status WHEN 'active' THEN 0 ELSE 1 END, pa.id
        """,
        (user_id,),
    ).fetchall()]


def person_lifecycle_detail(ctx: AuthContext, person_identity_id: int) -> dict[str, Any]:
    with _connect() as conn:
        target = _target(conn, person_identity_id)
        _require_read(conn, ctx, target)
        events = []
        for row in conn.execute(
            """
            SELECT id, event_type, status, effective_at, reason, impact_snapshot,
                   error_message, created_at, updated_at, completed_at
            FROM identity_lifecycle_event WHERE person_identity_id = ?
            ORDER BY created_at DESC, id DESC LIMIT 100
            """,
            (person_identity_id,),
        ).fetchall():
            item = dict(row)
            item["event_label"] = EVENT_LABELS.get(row["event_type"], row["event_type"])
            item["impact_snapshot"] = _json(row["impact_snapshot"])
            events.append(item)
        history = [dict(row) for row in conn.execute(
            """
            SELECT id, from_status, to_status, reason, session_version, created_at
            FROM account_status_history WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 100
            """,
            (target["user_id"],),
        ).fetchall()]
        item = {
            "person": target,
            "affiliations": _affiliations(conn, person_identity_id),
            "roles": _roles(conn, int(target["user_id"])),
            "positions": _positions(conn, int(target["user_id"])),
            "events": events,
            "account_status_history": history,
        }
    return {"item": item, "read_only": True}


def _security_snapshot(conn: sqlite3.Connection, target: dict[str, Any]) -> dict[str, Any]:
    user_id = int(target["user_id"])
    active_positions = [item["id"] for item in _positions(conn, user_id) if item["status"] == "active"]
    active_bindings = [item["id"] for item in _roles(conn, user_id) if item["status"] == "active"]
    claimed_tasks = [int(row[0]) for row in conn.execute(
        "SELECT id FROM review_task WHERE claimed_by_user_id = ? AND status = 'claimed' ORDER BY id",
        (user_id,),
    ).fetchall()]
    return {
        "account_status": target["account_status"],
        "session_version": int(target["session_version"] or 0),
        "active_position_assignment_ids": active_positions,
        "active_role_binding_ids": active_bindings,
        "claimed_review_task_ids": claimed_tasks,
    }


def _security_action(
    ctx: AuthContext,
    person_identity_id: int,
    *,
    action: str,
    reason: str,
    reauth_password: str | None,
) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("请填写账号安全操作依据")
    if action not in {"suspend", "restore"}:
        raise ValueError("不支持的账号安全操作")
    expected_status = "active" if action == "suspend" else "security_suspended"
    next_status = "security_suspended" if action == "suspend" else "active"
    event_type = "account_security_suspend" if action == "suspend" else "account_security_restore"
    with _connect() as conn:
        target = _target(conn, person_identity_id)
        if ctx.role != "admin":
            raise AuthorizationError("只有平台管理员可以执行账号安全操作")
        _require_security_admin_reauth(
            conn, ctx, reauth_password, resource_id=int(target["user_id"]), action=event_type,
        )
        if target["account_status"] != expected_status:
            raise ValueError(
                "账号当前不是可安全冻结状态" if action == "suspend" else "只有安全冻结中的账号可以恢复"
            )
        if action == "suspend" and int(target["user_id"]) == int(ctx.user_id or 0):
            _audit(conn, ctx, int(target["user_id"]), "self_suspend_blocked")
            conn.commit()
            raise AuthorizationError("不能安全冻结当前正在使用的管理员账号")
        if action == "suspend" and _has_formal_platform_admin_position(conn, int(target["user_id"])):
            remaining = _formal_platform_admin_count_excluding(conn, int(target["user_id"]))
            if remaining < MIN_FORMAL_PLATFORM_ADMINS:
                _audit(
                    conn, ctx, int(target["user_id"]), "minimum_admins_blocked",
                    after={"remaining_formal_platform_admins": remaining, "minimum": MIN_FORMAL_PLATFORM_ADMINS},
                )
                conn.commit()
                raise AuthorizationError(
                    f"安全冻结后正式平台管理员将少于 {MIN_FORMAL_PLATFORM_ADMINS} 人，不能执行"
                )

        before = _security_snapshot(conn, target)
        now = _now()
        next_session_version = int(target["session_version"] or 0) + 1
        conn.execute("BEGIN IMMEDIATE")
        changed = conn.execute(
            """
            UPDATE app_user SET status = ?, session_version = ?, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (next_status, next_session_version, now, target["user_id"], expected_status),
        ).rowcount
        if changed != 1:
            conn.rollback()
            raise ValueError("账号状态已发生变化，请刷新后重试")
        after = {**before, "account_status": next_status, "session_version": next_session_version}
        event_id = conn.execute(
            """
            INSERT INTO identity_lifecycle_event
            (event_type, target_user_id, person_identity_id, status, effective_at, reason,
             impact_snapshot, requested_by_user_id, approved_by_user_id, executed_by_user_id,
             created_at, updated_at, completed_at)
            VALUES (?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_type, target["user_id"], person_identity_id, now, reason.strip(),
                json.dumps({"before": before, "after": after}, ensure_ascii=False),
                ctx.user_id, ctx.user_id, ctx.user_id, now, now, now,
            ),
        ).lastrowid
        conn.execute(
            """
            INSERT INTO account_status_history
            (user_id, lifecycle_event_id, from_status, to_status, actor_user_id, reason, session_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (target["user_id"], event_id, expected_status, next_status, ctx.user_id, reason.strip(), next_session_version, now),
        )
        _audit(conn, ctx, int(target["user_id"]), "suspended" if action == "suspend" else "restored", before=before, after=after)
        conn.commit()
    return {
        "item": {
            "person_identity_id": person_identity_id,
            "user_id": int(target["user_id"]),
            "account_status": next_status,
            "session_version": next_session_version,
            "event_id": int(event_id),
            "roles_or_positions_changed": False,
            "message": "账号已安全冻结，所有既有会话已失效" if action == "suspend" else "账号已恢复；仅当前仍有效的岗位和身份可在重新登录后使用",
        }
    }


def security_suspend_account(
    ctx: AuthContext, person_identity_id: int, reason: str, reauth_password: str | None,
) -> dict[str, Any]:
    return _security_action(
        ctx, person_identity_id, action="suspend", reason=reason, reauth_password=reauth_password,
    )


def security_restore_account(
    ctx: AuthContext, person_identity_id: int, reason: str, reauth_password: str | None,
) -> dict[str, Any]:
    return _security_action(
        ctx, person_identity_id, action="restore", reason=reason, reauth_password=reauth_password,
    )


def _audit_student_lifecycle(
    conn: sqlite3.Connection, ctx: AuthContext, student_id: int, action: str, before: Any, after: Any,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_log(actor_user, actor_role, resource_type, resource_id, action,
                              before_state, after_state, created_at)
        VALUES (?, ?, 'student_lifecycle', ?, ?, ?, ?, ?)
        """,
        (
            ctx.username, ctx.role, student_id, action,
            json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), _now(),
        ),
    )


def _require_student_lifecycle_manager(ctx: AuthContext) -> None:
    if ctx.role != "academic_office" or ctx.user_id is None:
        raise AuthorizationError("只有教务处工作身份可以办理学生学籍生命周期事项")


def _student_lifecycle_snapshot(conn: sqlite3.Connection, target: dict[str, Any]) -> dict[str, Any]:
    return {
        "student_status": target["source_status"],
        "account_status": target["account_status"],
        "session_version": int(target["session_version"] or 0),
        "student_role_bindings": [
            {"id": item["id"], "status": item["status"]}
            for item in _roles(conn, int(target["user_id"])) if item["role_code"] == "student"
        ],
    }


def _student_affiliation(conn: sqlite3.Connection, person_identity_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, organization_unit_id FROM person_affiliation
        WHERE person_identity_id = ? AND affiliation_type = 'student'
        ORDER BY valid_from DESC, id DESC LIMIT 1
        """,
        (person_identity_id,),
    ).fetchone()


def _staff_affiliation(conn: sqlite3.Connection, person_identity_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT id, organization_unit_id FROM person_affiliation
           WHERE person_identity_id = ? AND affiliation_type = 'staff'
           ORDER BY valid_from DESC, id DESC LIMIT 1""",
        (person_identity_id,),
    ).fetchone()


def _apply_student_lifecycle_event(
    conn: sqlite3.Connection,
    ctx: AuthContext,
    target: dict[str, Any],
    event_type: str,
    reason: str,
) -> dict[str, Any]:
    expected_statuses = {
        "student_leave": {"active"},
        "student_resume": {"leave"},
        "student_graduation": {"active", "leave"},
        "student_withdrawal": {"active", "leave"},
    }
    if event_type not in expected_statuses:
        raise ValueError("不支持的学生生命周期事件")
    if target["person_type"] != "student":
        raise ValueError("该操作只适用于学生身份")
    if target["source_status"] not in expected_statuses[event_type]:
        raise ValueError("学生当前学籍状态不能执行该操作")
    if target["account_status"] != "active":
        raise ValueError("账号当前不是正常状态，不能直接办理学籍生命周期事项")

    now = _now()
    before = _student_lifecycle_snapshot(conn, target)
    user_id = int(target["user_id"])
    student_id = int(target["entity_id"])
    person_identity_id = int(target["person_identity_id"])
    next_student_status = {
        "student_leave": "leave",
        "student_resume": "active",
        "student_graduation": "graduated",
        "student_withdrawal": "withdrawn",
    }[event_type]
    next_account_status = "active" if event_type in {"student_leave", "student_resume"} else "archived"
    next_session_version = int(target["session_version"] or 0) + 1

    conn.execute(
        "UPDATE student SET status = ? WHERE id = ? AND status = ?",
        (next_student_status, student_id, target["source_status"]),
    )
    affiliation = _student_affiliation(conn, person_identity_id)
    if event_type == "student_resume":
        organization_unit_id = int(affiliation["organization_unit_id"]) if affiliation and affiliation["organization_unit_id"] else teaching_migrations._college_unit_id(int(target["college_id"]))
        if affiliation:
            conn.execute("UPDATE person_affiliation SET updated_at = ? WHERE id = ?", (now, affiliation["id"]))
        conn.execute(
            """
            INSERT INTO person_affiliation
            (person_identity_id, affiliation_type, source_entity_id, organization_unit_id,
             status, valid_from, source_system, created_at, updated_at)
            VALUES (?, 'student', ?, ?, 'active', ?, 'lifecycle', ?, ?)
            """,
            (person_identity_id, student_id, organization_unit_id, now, now, now),
        )
        teaching_migrations._ensure_role_binding(
            conn, user_id, "student", "lifecycle_resume", [("student_id", student_id)],
            None, "学生复学后重新授予当前有效学生身份",
        )
    elif affiliation:
        conn.execute(
            """
            UPDATE person_affiliation SET status = ?, valid_until = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_student_status, now, now, affiliation["id"]),
        )

    if event_type == "student_leave":
        conn.execute(
            """
            UPDATE user_role_binding SET status = 'suspended', updated_at = ?
            WHERE user_id = ? AND role_code = 'student' AND status = 'active'
            """,
            (now, user_id),
        )
    elif event_type in {"student_graduation", "student_withdrawal"}:
        conn.execute(
            """
            UPDATE user_role_binding
            SET status = 'revoked', valid_until = ?, revoked_by_user_id = ?, revoked_at = ?,
                revoke_reason = ?, updated_at = ?
            WHERE user_id = ? AND role_code = 'student' AND status = 'active'
            """,
            (now, ctx.user_id, now, reason.strip(), now, user_id),
        )
    conn.execute(
        "UPDATE app_user SET status = ?, session_version = ?, updated_at = ? WHERE id = ?",
        (next_account_status, next_session_version, now, user_id),
    )
    after = {
        **before,
        "student_status": next_student_status,
        "account_status": next_account_status,
        "session_version": next_session_version,
        "student_role_binding_effect": "new_active_binding" if event_type == "student_resume" else (
            "suspended" if event_type == "student_leave" else "revoked"
        ),
    }
    event_id = conn.execute(
        """
        INSERT INTO identity_lifecycle_event
        (event_type, target_user_id, person_identity_id, status, effective_at, reason,
         impact_snapshot, requested_by_user_id, approved_by_user_id, executed_by_user_id,
         created_at, updated_at, completed_at)
        VALUES (?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_type, user_id, person_identity_id, now, reason.strip(),
            json.dumps({"before": before, "after": after}, ensure_ascii=False),
            ctx.user_id, ctx.user_id, ctx.user_id, now, now, now,
        ),
    ).lastrowid
    if next_account_status != before["account_status"]:
        conn.execute(
            """
            INSERT INTO account_status_history
            (user_id, lifecycle_event_id, from_status, to_status, actor_user_id, reason, session_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, event_id, before["account_status"], next_account_status, ctx.user_id, reason.strip(), next_session_version, now),
        )
    _audit_student_lifecycle(conn, ctx, student_id, event_type, before, after)
    return {
        "person_identity_id": person_identity_id,
        "student_id": student_id,
        "student_status": next_student_status,
        "account_status": next_account_status,
        "session_version": next_session_version,
        "event_id": int(event_id),
    }


def student_lifecycle_action(ctx: AuthContext, person_identity_id: int, event_type: str, reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("请填写学籍变动依据")
    _require_student_lifecycle_manager(ctx)
    with _connect() as conn:
        target = _target(conn, person_identity_id)
        conn.execute("BEGIN IMMEDIATE")
        item = _apply_student_lifecycle_event(conn, ctx, target, event_type, reason)
        conn.commit()
    return {"item": item}


def batch_graduate_students(ctx: AuthContext, person_identity_ids: list[int], reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("请填写批量毕业依据")
    _require_student_lifecycle_manager(ctx)
    unique_ids = list(dict.fromkeys(int(value) for value in person_identity_ids))
    if not unique_ids:
        raise ValueError("至少选择一名学生")
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        targets = [_target(conn, person_identity_id) for person_identity_id in unique_ids]
        # Validate the full batch before mutating any record.
        for target in targets:
            if target["person_type"] != "student" or target["source_status"] not in {"active", "leave"} or target["account_status"] != "active":
                conn.rollback()
                raise ValueError(f"学生 {target['identifier']} 当前不能办理毕业")
        items = [_apply_student_lifecycle_event(conn, ctx, target, "student_graduation", reason) for target in targets]
        conn.commit()
    return {"items": items, "count": len(items)}


def list_student_lifecycle(ctx: AuthContext, status: str = "active") -> dict[str, Any]:
    _require_student_lifecycle_manager(ctx)
    allowed = {"active", "leave", "graduated", "withdrawn", "all"}
    if status not in allowed:
        raise ValueError("不支持的学生状态筛选")
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT pi.id AS person_identity_id, s.id AS student_id, s.student_no, s.name,
                   s.status AS student_status, c.name AS college_name, cg.name AS class_name,
                   au.status AS account_status
            FROM student s
            JOIN person_identity pi ON pi.person_type = 'student' AND pi.entity_id = s.id AND pi.status = 'verified'
            JOIN app_user au ON au.id = pi.user_id
            LEFT JOIN college c ON c.id = s.college_id
            LEFT JOIN class_group cg ON cg.id = s.class_id
            WHERE (? = 'all' OR s.status = ?)
            ORDER BY s.college_id, s.class_id, s.student_no LIMIT 1000
            """,
            (status, status),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


def _staff_snapshot(conn: sqlite3.Connection, target: dict[str, Any]) -> dict[str, Any]:
    user_id = int(target["user_id"])
    return {
        "staff_status": target["source_status"], "college_id": target["college_id"],
        "account_status": target["account_status"], "session_version": int(target["session_version"] or 0),
        "active_position_ids": [item["id"] for item in _positions(conn, user_id) if item["status"] == "active"],
        "active_role_binding_ids": [item["id"] for item in _roles(conn, user_id) if item["status"] == "active" and item["role_code"] != "self_service"],
    }


def _require_staff_lifecycle_admin(conn: sqlite3.Connection, ctx: AuthContext, password: str, target_user_id: int, action: str) -> None:
    _require_security_admin_reauth(conn, ctx, password, resource_id=target_user_id, action=action)
    if int(ctx.user_id or 0) == target_user_id:
        raise AuthorizationError("不能办理当前正在使用的管理员账号的人事退出事项")


def request_staff_lifecycle(
    ctx: AuthContext, person_identity_id: int, event_type: str, reason: str, reauth_password: str, destination_college_id: int | None = None,
) -> dict[str, Any]:
    if event_type not in {"staff_transfer", "staff_termination", "staff_retirement"}:
        raise ValueError("不支持的职工生命周期事项")
    if not reason.strip():
        raise ValueError("请填写人事变动依据")
    with _connect() as conn:
        target = _target(conn, person_identity_id)
        if target["person_type"] != "staff" or target["source_status"] != "active" or target["account_status"] != "active":
            raise ValueError("职工当前状态不能发起该事项")
        _require_staff_lifecycle_admin(conn, ctx, reauth_password, int(target["user_id"]), event_type)
        if event_type == "staff_transfer":
            if not destination_college_id or int(destination_college_id) == int(target["college_id"] or 0):
                raise ValueError("请选择不同的目标学院")
            if not conn.execute("SELECT 1 FROM college WHERE id = ?", (destination_college_id,)).fetchone():
                raise ValueError("目标学院不存在")
        now = _now()
        snapshot = _staff_snapshot(conn, target)
        snapshot["destination_college_id"] = destination_college_id
        event_id = conn.execute(
            """
            INSERT INTO identity_lifecycle_event
            (event_type, target_user_id, person_identity_id, status, effective_at, reason, impact_snapshot,
             requested_by_user_id, created_at, updated_at)
            VALUES (?, ?, ?, 'pending_approval', ?, ?, ?, ?, ?, ?)
            """,
            (event_type, target["user_id"], person_identity_id, now, reason.strip(), json.dumps(snapshot, ensure_ascii=False), ctx.user_id, now, now),
        ).lastrowid
        _audit_student_lifecycle(conn, ctx, int(target["entity_id"]), f"{event_type}_requested", snapshot, {"event_id": event_id})
        conn.commit()
    return {"item": {"event_id": int(event_id), "status": "pending_approval", "requires_second_admin": True}}


def _create_staff_handover_rows(conn: sqlite3.Connection, event_id: int, target: dict[str, Any], now: str) -> int:
    user_id = int(target["user_id"])
    count = 0
    for row in conn.execute("SELECT id, queue_id FROM review_task WHERE claimed_by_user_id = ? AND status = 'claimed'", (user_id,)).fetchall():
        conn.execute("UPDATE review_task SET status = 'pending', claimed_by_user_id = NULL, claimed_at = NULL, updated_at = ? WHERE id = ?", (now, row["id"]))
        conn.execute("INSERT INTO responsibility_handover(lifecycle_event_id, resource_type, resource_id, from_user_id, to_queue_id, status, note, assigned_at, created_at, updated_at) VALUES (?, 'review_task', ?, ?, ?, 'assigned', '已返回原组织审核队列', ?, ?, ?)", (event_id, row["id"], user_id, row["queue_id"], now, now, now)); count += 1
    if target["teacher_id"] is not None:
        for row in conn.execute("SELECT id FROM teaching_class WHERE teacher_id = ?", (target["teacher_id"],)).fetchall():
            conn.execute("INSERT INTO responsibility_handover(lifecycle_event_id, resource_type, resource_id, from_user_id, status, note, created_at, updated_at) VALUES (?, 'teaching_class', ?, ?, 'exception', '教学责任需由教务另行指定接任教师', ?, ?)", (event_id, row["id"], user_id, now, now)); count += 1
    if target["counselor_id"] is not None:
        for row in conn.execute("SELECT id FROM support_case WHERE counselor_id = ? AND status <> 'closed'", (target["counselor_id"],)).fetchall():
            conn.execute("INSERT INTO responsibility_handover(lifecycle_event_id, resource_type, resource_id, from_user_id, status, note, created_at, updated_at) VALUES (?, 'support_case', ?, ?, 'exception', '未关闭个案已进入学院人工交接清单', ?, ?)", (event_id, row["id"], user_id, now, now)); count += 1
    return count


def confirm_staff_lifecycle(ctx: AuthContext, event_id: int, reauth_password: str) -> dict[str, Any]:
    with _connect() as conn:
        event = conn.execute("SELECT * FROM identity_lifecycle_event WHERE id = ?", (event_id,)).fetchone()
        if not event or event["status"] != "pending_approval":
            raise ValueError("待确认的人事事项不存在或已处理")
        if int(event["requested_by_user_id"] or 0) == int(ctx.user_id or 0):
            raise AuthorizationError("必须由另一名具名管理员完成第二次确认")
        target = _target(conn, int(event["person_identity_id"]))
        _require_staff_lifecycle_admin(conn, ctx, reauth_password, int(target["user_id"]), str(event["event_type"]))
        if target["source_status"] != "active" or target["account_status"] != "active":
            raise ValueError("职工状态已变化，不能执行该事项")
        before = _staff_snapshot(conn, target)
        payload = _json(event["impact_snapshot"]) or {}
        destination_college_id = payload.get("destination_college_id")
        now = _now(); user_id = int(target["user_id"]); staff_id = int(target["entity_id"])
        conn.execute("BEGIN IMMEDIATE")
        if event["event_type"] == "staff_transfer":
            conn.execute("UPDATE staff SET college_id = ?, employment_status = 'transferred', updated_at = ? WHERE id = ?", (destination_college_id, now, staff_id))
            aff = _staff_affiliation(conn, int(target["person_identity_id"]))
            if aff: conn.execute("UPDATE person_affiliation SET status = 'transferred', valid_until = ?, updated_at = ? WHERE id = ?", (now, now, aff["id"]))
            conn.execute("INSERT INTO person_affiliation(person_identity_id, affiliation_type, source_entity_id, organization_unit_id, status, valid_from, source_system, created_at, updated_at) VALUES (?, 'staff', ?, ?, 'active', ?, 'lifecycle', ?, ?)", (target["person_identity_id"], staff_id, teaching_migrations._college_unit_id(int(destination_college_id)), now, now, now))
            conn.execute("UPDATE staff SET employment_status = 'active', updated_at = ? WHERE id = ?", (now, staff_id))
            next_account_status = 'active'; next_staff_status = 'active'
        else:
            next_staff_status = 'terminated' if event["event_type"] == 'staff_termination' else 'retired'; next_account_status = 'archived'
            conn.execute("UPDATE staff SET employment_status = ?, updated_at = ? WHERE id = ?", (next_staff_status, now, staff_id))
            aff = _staff_affiliation(conn, int(target["person_identity_id"]))
            if aff: conn.execute("UPDATE person_affiliation SET status = ?, valid_until = ?, updated_at = ? WHERE id = ?", (next_staff_status, now, now, aff["id"]))
        conn.execute("UPDATE position_assignment SET status = 'ended', ended_by_user_id = ?, ended_at = ?, end_reason = ?, updated_at = ? WHERE user_id = ? AND status = 'active'", (ctx.user_id, now, event["reason"], now, user_id))
        conn.execute("UPDATE user_role_binding SET status = 'revoked', revoked_by_user_id = ?, revoked_at = ?, revoke_reason = ?, valid_until = ?, updated_at = ? WHERE user_id = ? AND role_code <> 'self_service' AND status = 'active'", (ctx.user_id, now, event["reason"], now, now, user_id))
        handover_count = _create_staff_handover_rows(conn, event_id, target, now)
        version = int(target["session_version"] or 0) + 1
        conn.execute("UPDATE app_user SET status = ?, session_version = ?, updated_at = ? WHERE id = ?", (next_account_status, version, now, user_id))
        after = {**before, "staff_status": next_staff_status, "account_status": next_account_status, "session_version": version, "handover_count": handover_count}
        conn.execute("UPDATE identity_lifecycle_event SET status = 'completed', approved_by_user_id = ?, executed_by_user_id = ?, updated_at = ?, completed_at = ?, impact_snapshot = ? WHERE id = ?", (ctx.user_id, ctx.user_id, now, now, json.dumps({"before": before, "after": after}, ensure_ascii=False), event_id))
        if next_account_status != before["account_status"]: conn.execute("INSERT INTO account_status_history(user_id, lifecycle_event_id, from_status, to_status, actor_user_id, reason, session_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (user_id, event_id, before["account_status"], next_account_status, ctx.user_id, event["reason"], version, now))
        _audit_student_lifecycle(conn, ctx, staff_id, f"{event['event_type']}_confirmed", before, after)
        conn.commit()
    return {"item": {"event_id": event_id, "status": "completed", "session_version": version, "handover_count": handover_count}}


def my_lifecycle_detail(ctx: AuthContext) -> dict[str, Any]:
    if ctx.user_id is None:
        raise FileNotFoundError("当前账号没有人员身份")
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM person_identity WHERE user_id = ? AND status = 'verified'", (ctx.user_id,)
        ).fetchone()
    if not row:
        raise FileNotFoundError("当前账号没有已核验人员身份")
    return person_lifecycle_detail(ctx, int(row[0]))


def _active_role_filter(event_type: str) -> str:
    if event_type in STUDENT_EVENTS:
        return "urb.role_code = 'student'"
    if event_type == "position_end":
        return "urb.position_assignment_id IS NOT NULL"
    if event_type in {"staff_transfer", "staff_termination", "staff_retirement"}:
        return "urb.role_code <> 'self_service'"
    return "1 = 1"


def _minimum_coverage_blockers(conn: sqlite3.Connection, positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for position in positions:
        if position["status"] != "active" or int(position["min_occupants"] or 0) <= 0:
            continue
        count = int(conn.execute(
            """
            SELECT count(*) FROM position_assignment pa
            JOIN organization_position_slot ops ON ops.id = pa.position_slot_id
            WHERE ops.id = (SELECT position_slot_id FROM position_assignment WHERE id = ?)
              AND pa.status = 'active' AND (pa.valid_until IS NULL OR datetime(pa.valid_until) > datetime('now'))
            """,
            (position["id"],),
        ).fetchone()[0])
        if count - 1 < int(position["min_occupants"]):
            blockers.append({
                "code": "minimum_position_coverage",
                "message": f"{position['organization_name']}的{position['title']}岗位低于最低覆盖要求",
                "resource_type": "position_assignment",
                "resource_id": position["id"],
            })
    return blockers


def lifecycle_impact(ctx: AuthContext, person_identity_id: int, event_type: str) -> dict[str, Any]:
    if event_type not in EVENT_LABELS:
        raise ValueError("不支持的生命周期事件类型")
    with _connect() as conn:
        target = _target(conn, person_identity_id)
        _require_read(conn, ctx, target)
        if event_type in STUDENT_EVENTS and target["person_type"] != "student":
            raise ValueError("该事件只适用于学生身份")
        if event_type in STAFF_EVENTS and target["person_type"] != "staff":
            raise ValueError("该事件只适用于教职工身份")

        positions = _positions(conn, int(target["user_id"]))
        active_positions = [item for item in positions if item["status"] == "active"]
        role_filter = _active_role_filter(event_type)
        affected_roles = [dict(row) for row in conn.execute(
            f"""
            SELECT urb.id, urb.role_code, urb.position_assignment_id, urb.valid_until
            FROM user_role_binding urb WHERE urb.user_id = ? AND urb.status = 'active' AND {role_filter}
            ORDER BY urb.id
            """,
            (target["user_id"],),
        ).fetchall()]
        claimed_tasks = [dict(row) for row in conn.execute(
            """
            SELECT rt.id, rt.task_type, rt.resource_type, rt.resource_id, rt.status,
                   rt.queue_id, q.name AS queue_name
            FROM review_task rt JOIN organization_review_queue q ON q.id = rt.queue_id
            WHERE rt.claimed_by_user_id = ? AND rt.status = 'claimed' ORDER BY rt.id
            """,
            (target["user_id"],),
        ).fetchall()]

        responsibilities: list[dict[str, Any]] = []
        if target["person_type"] == "staff":
            if target["teacher_id"] is not None:
                classes = conn.execute(
                    "SELECT id, year, semester, classroom FROM teaching_class WHERE teacher_id = ? ORDER BY id",
                    (target["teacher_id"],),
                ).fetchall()
                for row in classes:
                    open_assignments = int(conn.execute(
                        "SELECT count(*) FROM assignment WHERE teaching_class_id = ? AND status IN ('draft','published')",
                        (row["id"],),
                    ).fetchone()[0])
                    responsibilities.append({
                        "resource_type": "teaching_class", "resource_id": row["id"],
                        "label": f"{row['year']} {row['semester']} 教学班",
                        "open_items": open_assignments, "handover_required": True,
                    })
            if target["counselor_id"] is not None:
                cases = conn.execute(
                    "SELECT id, code, title, status FROM support_case WHERE counselor_id = ? AND status <> 'closed' ORDER BY id",
                    (target["counselor_id"],),
                ).fetchall()
                responsibilities.extend({
                    "resource_type": "support_case", "resource_id": row["id"],
                    "label": f"{row['code']} {row['title']}", "status": row["status"],
                    "handover_required": True,
                } for row in cases)
        else:
            active_courses = int(conn.execute(
                "SELECT count(*) FROM enrollment WHERE student_id = ?", (target["entity_id"],)
            ).fetchone()[0])
            pending_assignments = int(conn.execute(
                """
                SELECT count(*) FROM assignment a JOIN enrollment e ON e.teaching_class_id = a.teaching_class_id
                LEFT JOIN assignment_submission sub ON sub.assignment_id = a.id AND sub.student_id = e.student_id
                WHERE e.student_id = ? AND a.status = 'published' AND sub.id IS NULL
                """,
                (target["entity_id"],),
            ).fetchone()[0])
            responsibilities.append({
                "resource_type": "student_course_membership", "resource_id": target["entity_id"],
                "label": "当前选课与未完成作业", "active_courses": active_courses,
                "open_items": pending_assignments, "handover_required": False,
            })

        blockers: list[dict[str, Any]] = []
        requires_position_exit = event_type in {"staff_transfer", "staff_termination", "staff_retirement", "account_closure"}
        if requires_position_exit and active_positions:
            blockers.append({
                "code": "active_positions",
                "message": f"仍有 {len(active_positions)} 个有效岗位，必须先结束或完成交接",
                "resource_type": "position_assignment",
                "count": len(active_positions),
            })
        if event_type == "account_closure" and claimed_tasks:
            blockers.append({
                "code": "claimed_review_tasks", "message": "仍有已领取审核任务，必须先释放或移交",
                "resource_type": "review_task", "count": len(claimed_tasks),
            })
        if event_type in {"position_end", "staff_transfer", "staff_termination", "staff_retirement", "account_closure"}:
            blockers.extend(_minimum_coverage_blockers(conn, active_positions))

        warnings: list[dict[str, Any]] = []
        if responsibilities:
            warnings.append({
                "code": "open_responsibilities",
                "message": f"发现 {len(responsibilities)} 项课程、支持或学籍责任，需要确认保留或移交",
                "count": len(responsibilities),
            })
        if event_type == "account_security_suspend" and active_positions:
            warnings.append({
                "code": "emergency_coverage",
                "message": "安全停用应立即撤权，但会产生岗位覆盖异常，需要同步通知组织负责人",
                "count": len(active_positions),
            })

        impact = {
            "event_type": event_type,
            "event_label": EVENT_LABELS[event_type],
            "read_only": True,
            "target": target,
            "session": {
                "current_session_version": target["session_version"],
                "revoke_all_sessions": event_type != "student_resume",
                "active_session_count_available": False,
            },
            "affected_roles": affected_roles,
            "active_positions": active_positions,
            "claimed_review_tasks": claimed_tasks,
            "responsibilities": responsibilities,
            "blockers": blockers,
            "warnings": warnings,
            "handover_required": bool(claimed_tasks or any(item.get("handover_required") for item in responsibilities)),
            "can_execute": not blockers,
            "execution_available": False,
        }
    return {"item": impact}


def my_lifecycle_impact(ctx: AuthContext, event_type: str) -> dict[str, Any]:
    if ctx.user_id is None:
        raise FileNotFoundError("当前账号没有人员身份")
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM person_identity WHERE user_id = ? AND status = 'verified'", (ctx.user_id,)
        ).fetchone()
    if not row:
        raise FileNotFoundError("当前账号没有已核验人员身份")
    return lifecycle_impact(ctx, int(row[0]), event_type)
