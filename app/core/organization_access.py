"""Organization directory, position assignments and scoped review queues."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.core import teaching_migrations
from app.core.business_domains import AuthContext, AuthorizationError, _verify_password
from app.core.teaching_migrations import _ensure_role_binding


POSITION_ROLE = {
    "college_primary_manager": "college_manager",
    "college_deputy_manager": "college_manager",
    "identity_reviewer": "identity_reviewer",
    "counselor": "counselor",
    "academic_officer": "academic_office",
    "platform_admin": "admin",
}

MIN_FORMAL_PLATFORM_ADMINS = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(teaching_migrations.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _audit(
    conn: sqlite3.Connection,
    ctx: AuthContext,
    resource_type: str,
    resource_id: int,
    action: str,
    before: Any = None,
    after: Any = None,
) -> None:
    def encode(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    conn.execute(
        """
        INSERT INTO audit_log(actor_user, actor_role, resource_type, resource_id, action,
                              before_state, after_state, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ctx.username, ctx.role, resource_type, resource_id, action, encode(before), encode(after), _now()),
    )


def _require_admin_reauth(
    conn: sqlite3.Connection,
    ctx: AuthContext,
    password: str | None,
    *,
    resource_id: int,
    action: str,
) -> None:
    if ctx.role != "admin" or ctx.user_id is None:
        raise AuthorizationError("只有平台管理员可以执行管理员岗位操作")
    row = conn.execute("SELECT password_hash FROM app_user WHERE id = ? AND status = 'active'", (ctx.user_id,)).fetchone()
    if not row or not password or not _verify_password(password, str(row[0])):
        _audit(
            conn,
            ctx,
            "platform_admin_security",
            resource_id,
            "reauth_failed",
            after={"requested_action": action},
        )
        conn.commit()
        raise AuthorizationError("管理员密码验证失败，本次高风险操作已记录")


def _formal_platform_admin_count(conn: sqlite3.Connection, *, excluding_assignment_id: int | None = None) -> int:
    return int(conn.execute(
        """
        SELECT count(DISTINCT pa.user_id)
        FROM position_assignment pa
        JOIN organization_position_slot ops ON ops.id = pa.position_slot_id
        JOIN user_role_binding urb ON urb.position_assignment_id = pa.id
        JOIN app_user au ON au.id = pa.user_id
        WHERE ops.position_code = 'platform_admin' AND pa.status = 'active'
          AND urb.role_code = 'admin' AND urb.status = 'active'
          AND au.active = 1 AND au.status = 'active'
          AND (pa.valid_until IS NULL OR datetime(pa.valid_until) > datetime('now'))
          AND (? IS NULL OR pa.id <> ?)
        """,
        (excluding_assignment_id, excluding_assignment_id),
    ).fetchone()[0])


def _validate_assignment_dates(
    assignment_type: str,
    valid_from: str,
    valid_until: str | None,
    *,
    allow_past_until: bool = False,
) -> None:
    try:
        start = datetime.fromisoformat(valid_from.replace("Z", "+00:00"))
        end = datetime.fromisoformat(valid_until.replace("Z", "+00:00")) if valid_until else None
    except ValueError as exc:
        raise ValueError("任职日期格式无效") from exc
    if assignment_type in {"acting", "temporary"} and end is None:
        raise ValueError("代理或临时岗位必须设置明确的到期时间")
    comparable_start = start.astimezone(timezone.utc).replace(tzinfo=None) if start.tzinfo else start
    comparable_end = end.astimezone(timezone.utc).replace(tzinfo=None) if end and end.tzinfo else end
    if comparable_end is not None and comparable_end <= comparable_start:
        raise ValueError("到期时间必须晚于生效时间")
    if comparable_end is not None and not allow_past_until:
        if comparable_end <= datetime.now(timezone.utc).replace(tzinfo=None):
            raise ValueError("到期时间必须晚于当前时间")


def _college_scope(ctx: AuthContext) -> int | None:
    value = ctx.row_scope.get("college_id")
    return int(value) if value is not None else None


def _require_org_reader(ctx: AuthContext) -> None:
    if ctx.role not in {"admin", "academic_office", "college_manager", "identity_reviewer", "counselor"}:
        raise AuthorizationError("当前岗位无权查看组织目录")


def _unit_allowed(ctx: AuthContext, source_college_id: int | None) -> bool:
    if ctx.role in {"admin", "academic_office"}:
        return True
    college_id = _college_scope(ctx)
    return college_id is not None and source_college_id == college_id


def list_organization_units(ctx: AuthContext) -> dict[str, Any]:
    _require_org_reader(ctx)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT ou.id, ou.code, ou.name, ou.unit_type, ou.source_college_id, ou.status,
                   sum(CASE WHEN ops.position_code = 'college_primary_manager' AND pa.status = 'active' THEN 1 ELSE 0 END) AS primary_managers,
                   sum(CASE WHEN ops.position_code = 'identity_reviewer' AND pa.status = 'active' THEN 1 ELSE 0 END) AS identity_reviewers,
                   sum(CASE WHEN ops.position_code = 'counselor' AND pa.status = 'active' THEN 1 ELSE 0 END) AS counselor_positions
            FROM organization_unit ou
            LEFT JOIN organization_position_slot ops ON ops.organization_unit_id = ou.id
            LEFT JOIN position_assignment pa ON pa.position_slot_id = ops.id
                AND pa.status = 'active' AND (pa.valid_until IS NULL OR datetime(pa.valid_until) > datetime('now'))
            WHERE ou.status = 'active'
            GROUP BY ou.id ORDER BY ou.unit_type, ou.id
            """
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            if row["unit_type"] == "college" and not _unit_allowed(ctx, row["source_college_id"]):
                continue
            if row["unit_type"] != "college" and ctx.role not in {"admin", "academic_office"}:
                continue
            item = dict(row)
            if row["unit_type"] == "college":
                college_id = int(row["source_college_id"])
                item["class_count"] = int(conn.execute(
                    "SELECT count(*) FROM class_group cg JOIN major m ON m.id = cg.major_id WHERE m.college_id = ?",
                    (college_id,),
                ).fetchone()[0])
                item["covered_class_count"] = int(conn.execute(
                    """
                    SELECT count(DISTINCT ccg.class_group_id) FROM counselor_class_group ccg
                    JOIN class_group cg ON cg.id = ccg.class_group_id JOIN major m ON m.id = cg.major_id
                    WHERE m.college_id = ?
                    """,
                    (college_id,),
                ).fetchone()[0])
                item["pending_reviews"] = int(conn.execute(
                    """
                    SELECT count(*) FROM review_task rt JOIN organization_review_queue q ON q.id = rt.queue_id
                    WHERE q.organization_unit_id = ? AND rt.status IN ('pending', 'claimed', 'escalated')
                    """,
                    (row["id"],),
                ).fetchone()[0])
                issues = []
                if int(row["primary_managers"] or 0) < 1:
                    issues.append("学院主要负责人空缺")
                if int(row["identity_reviewers"] or 0) < 1:
                    issues.append("身份审核员空缺")
                if item["covered_class_count"] < item["class_count"]:
                    issues.append(f"{item['class_count'] - item['covered_class_count']} 个行政班未配置辅导员")
                item["issues"] = issues
            else:
                item["issues"] = []
            items.append(item)
    return {"items": items}


def list_staff(ctx: AuthContext, college_id: int | None = None, query: str = "") -> dict[str, Any]:
    _require_org_reader(ctx)
    scoped_college = _college_scope(ctx)
    if ctx.role not in {"admin", "academic_office"}:
        college_id = scoped_college
    elif college_id is not None:
        college_id = int(college_id)
    params: list[Any] = []
    where = ["1 = 1"]
    if college_id is not None:
        where.append("st.college_id = ?")
        params.append(college_id)
    if query.strip():
        where.append("(st.name LIKE ? OR st.staff_no LIKE ?)")
        value = f"%{query.strip()}%"
        params.extend([value, value])
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT st.id, st.staff_no, st.name, st.college_id, c.name AS college_name,
                   st.staff_type, st.employment_status, st.teacher_id, st.counselor_id,
                   pi.id AS person_identity_id, au.id AS user_id, au.username, au.status AS account_status,
                   group_concat(DISTINCT urb.role_code) AS roles
            FROM staff st LEFT JOIN college c ON c.id = st.college_id
            LEFT JOIN person_identity pi ON pi.person_type = 'staff' AND pi.entity_id = st.id AND pi.status = 'verified'
            LEFT JOIN app_user au ON au.id = pi.user_id
            LEFT JOIN user_role_binding urb ON urb.user_id = au.id AND urb.status = 'active'
            WHERE {' AND '.join(where)}
            GROUP BY st.id ORDER BY st.college_id, st.staff_no LIMIT 500
            """,
            tuple(params),
        ).fetchall()
    return {"items": [{**dict(row), "roles": (row["roles"] or "").split(",") if row["roles"] else []} for row in rows]}


def list_class_groups(ctx: AuthContext, college_id: int | None = None) -> dict[str, Any]:
    _require_org_reader(ctx)
    scoped_college = _college_scope(ctx)
    if ctx.role not in {"admin", "academic_office"}:
        college_id = scoped_college
    elif college_id is not None:
        college_id = int(college_id)
    if college_id is None:
        return {"items": []}
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT cg.id, cg.name, cg.grade_year, m.name AS major_name, m.college_id,
                   group_concat(DISTINCT co.name) AS counselor_names
            FROM class_group cg
            JOIN major m ON m.id = cg.major_id
            LEFT JOIN counselor_class_group ccg ON ccg.class_group_id = cg.id
            LEFT JOIN counselor co ON co.id = ccg.counselor_id
            WHERE m.college_id = ?
            GROUP BY cg.id ORDER BY cg.grade_year DESC, cg.name, cg.id
            """,
            (college_id,),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


def list_position_slots(ctx: AuthContext, organization_unit_id: int | None = None) -> dict[str, Any]:
    _require_org_reader(ctx)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT ops.*, ou.name AS organization_name, ou.unit_type, ou.source_college_id
            FROM organization_position_slot ops JOIN organization_unit ou ON ou.id = ops.organization_unit_id
            WHERE (? IS NULL OR ops.organization_unit_id = ?) AND ops.status = 'active'
            ORDER BY ou.id, ops.id
            """,
            (organization_unit_id, organization_unit_id),
        ).fetchall()
        items = []
        for row in rows:
            if not _unit_allowed(ctx, row["source_college_id"]):
                continue
            assignments = conn.execute(
                """
                SELECT pa.id, pa.assignment_type, pa.status, pa.valid_from, pa.valid_until,
                       pa.appointment_reason, st.id AS staff_id, st.staff_no, st.name, au.id AS user_id
                FROM position_assignment pa JOIN staff st ON st.id = pa.staff_id
                JOIN app_user au ON au.id = pa.user_id
                WHERE pa.position_slot_id = ? AND pa.status = 'active'
                  AND (pa.valid_until IS NULL OR datetime(pa.valid_until) > datetime('now'))
                ORDER BY pa.id
                """,
                (row["id"],),
            ).fetchall()
            assignment_items = []
            for assignment in assignments:
                assignment_item = dict(assignment)
                scope_rows = conn.execute(
                    """
                    SELECT rsb.scope_type, rsb.scope_id
                    FROM user_role_binding urb
                    JOIN role_scope_binding rsb ON rsb.role_binding_id = urb.id
                    WHERE urb.position_assignment_id = ? AND urb.status = 'active'
                    ORDER BY rsb.id
                    """,
                    (assignment["id"],),
                ).fetchall()
                assignment_item["scopes"] = [dict(scope) for scope in scope_rows]
                assignment_item["scope_ids"] = [
                    int(scope["scope_id"])
                    for scope in scope_rows
                    if scope["scope_type"] == "class_group" and scope["scope_id"] is not None
                ]
                assignment_items.append(assignment_item)
            items.append({**dict(row), "assignments": assignment_items, "active_occupants": len(assignments)})
    return {"items": items}


def _load_slot_and_check_assignment_authority(conn: sqlite3.Connection, ctx: AuthContext, slot_id: int) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT ops.*, ou.unit_type, ou.source_college_id, ou.name AS organization_name
        FROM organization_position_slot ops JOIN organization_unit ou ON ou.id = ops.organization_unit_id
        WHERE ops.id = ? AND ops.status = 'active' AND ou.status = 'active'
        """,
        (slot_id,),
    ).fetchone()
    if not row:
        raise ValueError("岗位编制不存在或已停用")
    if ctx.role == "admin":
        return row
    if ctx.role == "academic_office" and row["position_code"] != "platform_admin":
        return row
    if (
        ctx.role == "college_manager"
        and row["source_college_id"] == _college_scope(ctx)
        and row["position_code"] in {"identity_reviewer", "counselor"}
    ):
        return row
    raise AuthorizationError("当前岗位无权管理该组织岗位")


def create_position_assignment(
    ctx: AuthContext,
    *,
    position_slot_id: int,
    user_id: int,
    assignment_type: str,
    scope_ids: list[int],
    valid_from: str,
    valid_until: str | None,
    reason: str,
    reauth_password: str | None = None,
) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("岗位任命必须填写依据")
    if assignment_type not in {"primary", "deputy", "acting", "temporary", "reviewer"}:
        raise ValueError("不支持的任职类型")
    _validate_assignment_dates(assignment_type, valid_from, valid_until)
    now = _now()
    with _connect() as conn:
        slot = _load_slot_and_check_assignment_authority(conn, ctx, position_slot_id)
        if slot["position_code"] == "platform_admin":
            _require_admin_reauth(
                conn, ctx, reauth_password, resource_id=position_slot_id, action="appoint_platform_admin"
            )
        if ctx.user_id == user_id and slot["position_code"] in {"college_primary_manager", "platform_admin"}:
            if slot["position_code"] == "platform_admin":
                _audit(
                    conn, ctx, "platform_admin_security", position_slot_id, "self_grant_blocked",
                    after={"target_user_id": user_id},
                )
                conn.commit()
            raise AuthorizationError("不能给自己授予高权限岗位")
        person = conn.execute(
            """
            SELECT st.*, au.id AS user_id FROM person_identity pi JOIN staff st ON st.id = pi.entity_id
            JOIN app_user au ON au.id = pi.user_id
            WHERE pi.person_type = 'staff' AND pi.status = 'verified' AND au.id = ?
              AND st.employment_status = 'active' AND au.status = 'active'
            """,
            (user_id,),
        ).fetchone()
        if not person:
            raise ValueError("只能任命已验证且在职的教职工")
        if slot["source_college_id"] is not None and person["college_id"] != slot["source_college_id"]:
            raise AuthorizationError("不能将其他学院人员任命到本学院岗位")
        active_count = int(conn.execute(
            "SELECT count(*) FROM position_assignment WHERE position_slot_id = ? AND status = 'active' AND (valid_until IS NULL OR datetime(valid_until) > datetime('now'))",
            (position_slot_id,),
        ).fetchone()[0])
        if slot["max_occupants"] is not None and active_count >= int(slot["max_occupants"]):
            raise ValueError("该岗位已达到最大任职人数，请先结束或调整现有任职")
        role_code = POSITION_ROLE[str(slot["position_code"])]
        scopes: list[tuple[str, int | None]]
        if role_code == "counselor":
            if not scope_ids:
                raise ValueError("辅导员岗位至少需要选择一个行政班")
            marks = ",".join("?" for _ in scope_ids)
            valid_classes = {
                int(row[0]) for row in conn.execute(
                    f"""
                    SELECT cg.id FROM class_group cg JOIN major m ON m.id = cg.major_id
                    WHERE cg.id IN ({marks}) AND m.college_id = ?
                    """,
                    (*scope_ids, slot["source_college_id"]),
                ).fetchall()
            }
            if valid_classes != set(scope_ids):
                raise AuthorizationError("所选行政班包含其他学院或不存在的班级")
            scopes = [("class_group", value) for value in scope_ids]
            counselor_id = person["counselor_id"]
            if counselor_id is None:
                cursor = conn.execute(
                    "INSERT INTO counselor(counselor_no, name, college_id) VALUES (?, ?, ?)",
                    (person["staff_no"], person["name"], person["college_id"]),
                )
                counselor_id = int(cursor.lastrowid)
                conn.execute("UPDATE staff SET counselor_id = ?, updated_at = ? WHERE id = ?", (counselor_id, now, person["id"]))
            conn.execute("UPDATE app_user SET counselor_id = ?, college_id = ?, updated_at = ? WHERE id = ?", (counselor_id, person["college_id"], now, user_id))
            conn.executemany(
                "INSERT OR IGNORE INTO counselor_class_group(counselor_id, class_group_id) VALUES (?, ?)",
                [(counselor_id, value) for value in scope_ids],
            )
        elif role_code in {"college_manager", "identity_reviewer"}:
            scopes = [("college", int(slot["source_college_id"]))]
        elif role_code == "academic_office":
            scopes = [("academic_office", int(slot["organization_unit_id"]))]
        else:
            scopes = [("platform", int(slot["organization_unit_id"]))]
        cursor = conn.execute(
            """
            INSERT INTO position_assignment
            (position_slot_id, staff_id, user_id, assignment_type, status, valid_from, valid_until,
             appointed_by_user_id, appointment_reason, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
            """,
            (position_slot_id, person["id"], user_id, assignment_type, valid_from, valid_until,
             ctx.user_id, reason.strip(), now, now),
        )
        assignment_id = int(cursor.lastrowid)
        binding_id = _ensure_role_binding(conn, user_id, role_code, "position", scopes, assignment_id, reason.strip())
        conn.execute(
            "UPDATE user_role_binding SET valid_from = ?, valid_until = ?, updated_at = ? WHERE id = ?",
            (valid_from, valid_until, now, binding_id),
        )
        conn.execute("INSERT OR IGNORE INTO user_role(user_id, role_code) VALUES (?, ?)", (user_id, role_code))
        _audit(
            conn,
            ctx,
            "position_assignment",
            assignment_id,
            "admin_appointed" if slot["position_code"] == "platform_admin" else "appointed",
            after={"role": role_code, "scopes": scopes, "user_id": user_id, "reason": reason.strip()},
        )
        conn.commit()
    return {"item": {"id": assignment_id, "role_binding_id": binding_id, "role_code": role_code}}


def end_position_assignment(
    ctx: AuthContext,
    assignment_id: int,
    reason: str,
    *,
    reauth_password: str | None = None,
) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("结束任职必须填写原因")
    now = _now()
    with _connect() as conn:
        assignment = conn.execute(
            """
            SELECT pa.*, ops.position_code FROM position_assignment pa
            JOIN organization_position_slot ops ON ops.id = pa.position_slot_id WHERE pa.id = ?
            """,
            (assignment_id,),
        ).fetchone()
        if not assignment:
            raise ValueError("任职记录不存在")
        _load_slot_and_check_assignment_authority(conn, ctx, int(assignment["position_slot_id"]))
        if assignment["status"] != "active":
            raise ValueError("该任职已经结束")
        if assignment["position_code"] == "platform_admin":
            _require_admin_reauth(
                conn, ctx, reauth_password, resource_id=assignment_id, action="revoke_platform_admin"
            )
            if int(assignment["user_id"]) == int(ctx.user_id or 0):
                _audit(conn, ctx, "platform_admin_security", assignment_id, "self_revoke_blocked")
                conn.commit()
                raise AuthorizationError("不能撤销当前正在使用的管理员岗位，请由另一名管理员操作")
            if _formal_platform_admin_count(conn, excluding_assignment_id=assignment_id) < MIN_FORMAL_PLATFORM_ADMINS:
                _audit(
                    conn, ctx, "platform_admin_security", assignment_id, "minimum_admins_blocked",
                    after={"minimum": MIN_FORMAL_PLATFORM_ADMINS},
                )
                conn.commit()
                raise ValueError(f"平台必须至少保留 {MIN_FORMAL_PLATFORM_ADMINS} 名有效的具名管理员")
        conn.execute(
            """
            UPDATE position_assignment SET status = 'ended', ended_by_user_id = ?, ended_at = ?,
                end_reason = ?, updated_at = ? WHERE id = ?
            """,
            (ctx.user_id, now, reason.strip(), now, assignment_id),
        )
        conn.execute(
            """
            UPDATE user_role_binding SET status = 'revoked', revoked_by_user_id = ?, revoked_at = ?,
                revoke_reason = ?, updated_at = ? WHERE position_assignment_id = ? AND status = 'active'
            """,
            (ctx.user_id, now, reason.strip(), now, assignment_id),
        )
        conn.execute("UPDATE app_user SET session_version = session_version + 1, updated_at = ? WHERE id = ?", (now, assignment["user_id"]))
        _audit(
            conn,
            ctx,
            "position_assignment",
            assignment_id,
            "admin_revoked" if assignment["position_code"] == "platform_admin" else "ended",
            before={"status": "active", "user_id": assignment["user_id"]},
            after={"status": "ended", "reason": reason.strip()},
        )
        conn.commit()
    return {"ended": True, "id": assignment_id}


def position_assignment_impact(ctx: AuthContext, assignment_id: int) -> dict[str, Any]:
    with _connect() as conn:
        assignment = conn.execute(
            """
            SELECT pa.*, ops.position_code, ops.title AS position_title, ops.organization_unit_id,
                   ou.name AS organization_name, st.name, st.staff_no
            FROM position_assignment pa
            JOIN organization_position_slot ops ON ops.id = pa.position_slot_id
            JOIN organization_unit ou ON ou.id = ops.organization_unit_id
            JOIN staff st ON st.id = pa.staff_id
            WHERE pa.id = ?
            """,
            (assignment_id,),
        ).fetchone()
        if not assignment:
            raise ValueError("任职记录不存在")
        _load_slot_and_check_assignment_authority(conn, ctx, int(assignment["position_slot_id"]))
        scopes = [
            dict(row) for row in conn.execute(
                """
                SELECT rsb.scope_type, rsb.scope_id,
                       CASE WHEN rsb.scope_type = 'class_group' THEN cg.name ELSE NULL END AS scope_name
                FROM user_role_binding urb
                JOIN role_scope_binding rsb ON rsb.role_binding_id = urb.id
                LEFT JOIN class_group cg ON rsb.scope_type = 'class_group' AND cg.id = rsb.scope_id
                WHERE urb.position_assignment_id = ? AND urb.status = 'active'
                ORDER BY rsb.id
                """,
                (assignment_id,),
            ).fetchall()
        ]
        pending_tasks = int(conn.execute(
            """
            SELECT count(*) FROM review_task rt
            JOIN organization_review_queue q ON q.id = rt.queue_id
            WHERE q.organization_unit_id = ? AND rt.status IN ('pending', 'claimed', 'escalated')
            """,
            (assignment["organization_unit_id"],),
        ).fetchone()[0])
        remaining_admins = None
        can_end = assignment["status"] == "active"
        warnings: list[str] = []
        if assignment["position_code"] == "counselor" and scopes:
            warnings.append(f"该辅导员仍关联 {len(scopes)} 个行政班，建议优先使用岗位交接")
        if assignment["position_code"] in {"college_primary_manager", "identity_reviewer"} and pending_tasks:
            warnings.append(f"所属组织仍有 {pending_tasks} 个待审核任务；任务会保留在组织队列中")
        if assignment["position_code"] == "platform_admin":
            remaining_admins = _formal_platform_admin_count(conn, excluding_assignment_id=assignment_id)
            if remaining_admins < MIN_FORMAL_PLATFORM_ADMINS:
                can_end = False
                warnings.append(f"撤销后不足 {MIN_FORMAL_PLATFORM_ADMINS} 名具名管理员，系统将禁止操作")
        return {
            "item": {
                **dict(assignment),
                "scopes": scopes,
                "pending_tasks": pending_tasks,
                "remaining_formal_admins": remaining_admins,
                "requires_reauth": assignment["position_code"] == "platform_admin",
                "can_end": can_end,
                "warnings": warnings,
            }
        }


def update_position_assignment(
    ctx: AuthContext,
    assignment_id: int,
    *,
    scope_ids: list[int] | None,
    valid_until: str | None,
    reason: str,
    reauth_password: str | None = None,
) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("调整岗位必须填写原因")
    now = _now()
    with _connect() as conn:
        assignment = conn.execute(
            """
            SELECT pa.*, ops.position_code, ou.source_college_id
            FROM position_assignment pa JOIN organization_position_slot ops ON ops.id = pa.position_slot_id
            JOIN organization_unit ou ON ou.id = ops.organization_unit_id
            WHERE pa.id = ?
            """,
            (assignment_id,),
        ).fetchone()
        if not assignment:
            raise ValueError("任职记录不存在")
        _load_slot_and_check_assignment_authority(conn, ctx, int(assignment["position_slot_id"]))
        if assignment["status"] != "active":
            raise ValueError("只能调整有效任职")
        _validate_assignment_dates(
            str(assignment["assignment_type"]), str(assignment["valid_from"]), valid_until
        )
        if assignment["position_code"] == "platform_admin":
            _require_admin_reauth(
                conn, ctx, reauth_password, resource_id=assignment_id, action="update_platform_admin"
            )
            if valid_until is not None and _formal_platform_admin_count(conn, excluding_assignment_id=assignment_id) < MIN_FORMAL_PLATFORM_ADMINS:
                _audit(
                    conn, ctx, "platform_admin_security", assignment_id, "unsafe_expiry_blocked",
                    after={"valid_until": valid_until, "minimum": MIN_FORMAL_PLATFORM_ADMINS},
                )
                conn.commit()
                raise ValueError(f"设置该到期时间后无法保证至少 {MIN_FORMAL_PLATFORM_ADMINS} 名具名管理员")
        binding = conn.execute(
            "SELECT id, role_code FROM user_role_binding WHERE position_assignment_id = ? AND status = 'active'",
            (assignment_id,),
        ).fetchone()
        if not binding:
            raise ValueError("岗位角色绑定不存在")
        before_scopes = [
            (str(row[0]), row[1]) for row in conn.execute(
                "SELECT scope_type, scope_id FROM role_scope_binding WHERE role_binding_id = ? ORDER BY id",
                (binding["id"],),
            ).fetchall()
        ]
        after_scopes = before_scopes
        if scope_ids is not None:
            if assignment["position_code"] != "counselor":
                raise ValueError("该岗位范围由所属组织固定，不能手工修改")
            if not scope_ids:
                raise ValueError("辅导员岗位至少需要一个行政班范围")
            marks = ",".join("?" for _ in scope_ids)
            valid = {
                int(row[0]) for row in conn.execute(
                    f"""
                    SELECT cg.id FROM class_group cg JOIN major m ON m.id = cg.major_id
                    WHERE cg.id IN ({marks}) AND m.college_id = ?
                    """,
                    (*scope_ids, assignment["source_college_id"]),
                ).fetchall()
            }
            if valid != set(scope_ids):
                raise AuthorizationError("调整范围包含其他学院或不存在的行政班")
            conn.execute("DELETE FROM role_scope_binding WHERE role_binding_id = ?", (binding["id"],))
            conn.executemany(
                "INSERT INTO role_scope_binding(role_binding_id, scope_type, scope_id, created_at) VALUES (?, 'class_group', ?, ?)",
                [(binding["id"], value, now) for value in scope_ids],
            )
            counselor_id = conn.execute("SELECT counselor_id FROM app_user WHERE id = ?", (assignment["user_id"],)).fetchone()[0]
            if counselor_id:
                conn.executemany(
                    "INSERT OR IGNORE INTO counselor_class_group(counselor_id, class_group_id) VALUES (?, ?)",
                    [(counselor_id, value) for value in scope_ids],
                )
                removed = {int(value) for kind, value in before_scopes if kind == "class_group"} - set(scope_ids)
                for class_id in removed:
                    used_elsewhere = conn.execute(
                        """
                        SELECT 1 FROM user_role_binding urb JOIN role_scope_binding rsb ON rsb.role_binding_id = urb.id
                        WHERE urb.user_id = ? AND urb.id <> ? AND urb.role_code = 'counselor'
                          AND urb.status = 'active' AND rsb.scope_type = 'class_group' AND rsb.scope_id = ? LIMIT 1
                        """,
                        (assignment["user_id"], binding["id"], class_id),
                    ).fetchone()
                    if not used_elsewhere:
                        conn.execute(
                            "DELETE FROM counselor_class_group WHERE counselor_id = ? AND class_group_id = ?",
                            (counselor_id, class_id),
                        )
            after_scopes = [("class_group", value) for value in scope_ids]
        conn.execute(
            "UPDATE position_assignment SET valid_until = ?, appointment_reason = ?, updated_at = ? WHERE id = ?",
            (valid_until, reason.strip(), now, assignment_id),
        )
        conn.execute(
            "UPDATE user_role_binding SET valid_until = ?, grant_reason = ?, updated_at = ? WHERE id = ?",
            (valid_until, reason.strip(), now, binding["id"]),
        )
        conn.execute("UPDATE app_user SET session_version = session_version + 1, updated_at = ? WHERE id = ?", (now, assignment["user_id"]))
        _audit(
            conn,
            ctx,
            "position_assignment",
            assignment_id,
            "admin_updated" if assignment["position_code"] == "platform_admin" else "updated",
            before={"valid_until": assignment["valid_until"], "scopes": before_scopes},
            after={"valid_until": valid_until, "scopes": after_scopes, "reason": reason.strip()},
        )
        conn.commit()
    return {"updated": True, "id": assignment_id, "scopes": [{"scope_type": kind, "scope_id": value} for kind, value in after_scopes]}


def transfer_position_assignment(
    ctx: AuthContext,
    assignment_id: int,
    *,
    successor_user_id: int,
    assignment_type: str,
    scope_ids: list[int] | None,
    valid_from: str,
    valid_until: str | None,
    reason: str,
    reauth_password: str | None = None,
) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("岗位交接必须填写交接依据")
    if assignment_type not in {"primary", "deputy", "acting", "temporary", "reviewer"}:
        raise ValueError("不支持的任职类型")
    _validate_assignment_dates(assignment_type, valid_from, valid_until)
    now = _now()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        assignment = conn.execute(
            """
            SELECT pa.*, ops.position_code, ops.organization_unit_id, ou.source_college_id
            FROM position_assignment pa
            JOIN organization_position_slot ops ON ops.id = pa.position_slot_id
            JOIN organization_unit ou ON ou.id = ops.organization_unit_id
            WHERE pa.id = ?
            """,
            (assignment_id,),
        ).fetchone()
        if not assignment:
            raise ValueError("任职记录不存在")
        _load_slot_and_check_assignment_authority(conn, ctx, int(assignment["position_slot_id"]))
        if assignment["status"] != "active":
            raise ValueError("只能交接当前有效的任职")
        if int(assignment["user_id"]) == int(successor_user_id):
            raise ValueError("继任人不能与当前任职人相同")
        if assignment["position_code"] == "platform_admin":
            _require_admin_reauth(
                conn, ctx, reauth_password, resource_id=assignment_id, action="transfer_platform_admin"
            )
            if int(successor_user_id) == int(ctx.user_id or 0):
                _audit(
                    conn, ctx, "platform_admin_security", assignment_id, "self_transfer_grant_blocked",
                    after={"successor_user_id": successor_user_id},
                )
                conn.commit()
                raise AuthorizationError("不能通过岗位交接给自己授予管理员权限")
        successor = conn.execute(
            """
            SELECT st.*, au.id AS user_id
            FROM person_identity pi JOIN staff st ON st.id = pi.entity_id
            JOIN app_user au ON au.id = pi.user_id
            WHERE pi.person_type = 'staff' AND pi.status = 'verified' AND au.id = ?
              AND st.employment_status = 'active' AND au.active = 1 AND au.status = 'active'
            """,
            (successor_user_id,),
        ).fetchone()
        if not successor:
            raise ValueError("继任人必须是已验证且在职的教职工")
        if assignment["source_college_id"] is not None and successor["college_id"] != assignment["source_college_id"]:
            raise AuthorizationError("继任人必须属于该岗位所在学院")

        old_binding = conn.execute(
            "SELECT id, role_code FROM user_role_binding WHERE position_assignment_id = ? AND status = 'active'",
            (assignment_id,),
        ).fetchone()
        if not old_binding:
            raise ValueError("当前岗位角色绑定不存在")
        old_scopes = [
            (str(row[0]), row[1]) for row in conn.execute(
                "SELECT scope_type, scope_id FROM role_scope_binding WHERE role_binding_id = ? ORDER BY id",
                (old_binding["id"],),
            ).fetchall()
        ]
        role_code = POSITION_ROLE[str(assignment["position_code"])]
        scopes: list[tuple[str, int | None]]
        if role_code == "counselor":
            selected_ids = scope_ids if scope_ids is not None else [
                int(value) for kind, value in old_scopes if kind == "class_group" and value is not None
            ]
            if not selected_ids:
                raise ValueError("辅导员岗位交接至少需要一个行政班范围")
            marks = ",".join("?" for _ in selected_ids)
            valid_classes = {
                int(row[0]) for row in conn.execute(
                    f"""
                    SELECT cg.id FROM class_group cg JOIN major m ON m.id = cg.major_id
                    WHERE cg.id IN ({marks}) AND m.college_id = ?
                    """,
                    (*selected_ids, assignment["source_college_id"]),
                ).fetchall()
            }
            if valid_classes != set(selected_ids):
                raise AuthorizationError("交接范围包含其他学院或不存在的行政班")
            scopes = [("class_group", value) for value in selected_ids]
            counselor_id = successor["counselor_id"]
            if counselor_id is None:
                existing = conn.execute("SELECT id FROM counselor WHERE counselor_no = ?", (successor["staff_no"],)).fetchone()
                if existing:
                    counselor_id = int(existing[0])
                else:
                    cursor = conn.execute(
                        "INSERT INTO counselor(counselor_no, name, college_id) VALUES (?, ?, ?)",
                        (successor["staff_no"], successor["name"], successor["college_id"]),
                    )
                    counselor_id = int(cursor.lastrowid)
                conn.execute("UPDATE staff SET counselor_id = ?, updated_at = ? WHERE id = ?", (counselor_id, now, successor["id"]))
            conn.execute(
                "UPDATE app_user SET counselor_id = ?, college_id = ?, updated_at = ? WHERE id = ?",
                (counselor_id, successor["college_id"], now, successor_user_id),
            )
            conn.executemany(
                "INSERT OR IGNORE INTO counselor_class_group(counselor_id, class_group_id) VALUES (?, ?)",
                [(counselor_id, value) for value in selected_ids],
            )
        elif role_code in {"college_manager", "identity_reviewer"}:
            scopes = [("college", int(assignment["source_college_id"]))]
        elif role_code == "academic_office":
            scopes = [("academic_office", int(assignment["organization_unit_id"]))]
        else:
            scopes = [("platform", int(assignment["organization_unit_id"]))]

        cursor = conn.execute(
            """
            INSERT INTO position_assignment
            (position_slot_id, staff_id, user_id, assignment_type, status, valid_from, valid_until,
             appointed_by_user_id, appointment_reason, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
            """,
            (assignment["position_slot_id"], successor["id"], successor_user_id, assignment_type,
             valid_from, valid_until, ctx.user_id, reason.strip(), now, now),
        )
        successor_assignment_id = int(cursor.lastrowid)
        successor_binding_id = _ensure_role_binding(
            conn, successor_user_id, role_code, "position", scopes, successor_assignment_id, reason.strip()
        )
        conn.execute(
            "UPDATE user_role_binding SET valid_from = ?, valid_until = ?, updated_at = ? WHERE id = ?",
            (valid_from, valid_until, now, successor_binding_id),
        )
        conn.execute("INSERT OR IGNORE INTO user_role(user_id, role_code) VALUES (?, ?)", (successor_user_id, role_code))
        conn.execute(
            """
            UPDATE position_assignment SET status = 'ended', ended_by_user_id = ?, ended_at = ?,
                end_reason = ?, updated_at = ? WHERE id = ?
            """,
            (ctx.user_id, now, f"岗位交接：{reason.strip()}", now, assignment_id),
        )
        conn.execute(
            """
            UPDATE user_role_binding SET status = 'revoked', revoked_by_user_id = ?, revoked_at = ?,
                revoke_reason = ?, updated_at = ? WHERE id = ?
            """,
            (ctx.user_id, now, f"岗位交接：{reason.strip()}", now, old_binding["id"]),
        )
        conn.execute(
            "UPDATE app_user SET session_version = session_version + 1, updated_at = ? WHERE id IN (?, ?)",
            (now, assignment["user_id"], successor_user_id),
        )
        if role_code == "counselor":
            old_counselor = conn.execute("SELECT counselor_id FROM app_user WHERE id = ?", (assignment["user_id"],)).fetchone()
            if old_counselor and old_counselor[0]:
                for kind, class_id in old_scopes:
                    if kind != "class_group" or class_id is None:
                        continue
                    still_used = conn.execute(
                        """
                        SELECT 1 FROM user_role_binding urb
                        JOIN role_scope_binding rsb ON rsb.role_binding_id = urb.id
                        WHERE urb.user_id = ? AND urb.status = 'active' AND urb.role_code = 'counselor'
                          AND rsb.scope_type = 'class_group' AND rsb.scope_id = ? LIMIT 1
                        """,
                        (assignment["user_id"], class_id),
                    ).fetchone()
                    if not still_used:
                        conn.execute(
                            "DELETE FROM counselor_class_group WHERE counselor_id = ? AND class_group_id = ?",
                            (old_counselor[0], class_id),
                        )
        _audit(
            conn,
            ctx,
            "position_assignment",
            assignment_id,
            "admin_transferred" if assignment["position_code"] == "platform_admin" else "transferred",
            before={"assignment_id": assignment_id, "user_id": assignment["user_id"], "scopes": old_scopes},
            after={
                "assignment_id": successor_assignment_id,
                "user_id": successor_user_id,
                "role": role_code,
                "scopes": scopes,
                "reason": reason.strip(),
            },
        )
        conn.commit()
    return {
        "transferred": True,
        "ended_assignment_id": assignment_id,
        "item": {
            "id": successor_assignment_id,
            "role_binding_id": successor_binding_id,
            "role_code": role_code,
            "user_id": successor_user_id,
        },
    }


def list_review_queues(ctx: AuthContext) -> dict[str, Any]:
    _require_org_reader(ctx)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT q.*, ou.name AS organization_name,
                   sum(CASE WHEN rt.status IN ('pending', 'claimed', 'escalated') THEN 1 ELSE 0 END) AS pending_count
            FROM organization_review_queue q JOIN organization_unit ou ON ou.id = q.organization_unit_id
            LEFT JOIN review_task rt ON rt.queue_id = q.id
            WHERE q.status = 'active' GROUP BY q.id ORDER BY ou.id, q.id
            """
        ).fetchall()
        items = [dict(row) for row in rows if _unit_allowed(ctx, row["scope_id"] if row["scope_type"] == "college" else conn.execute(
            "SELECT source_college_id FROM organization_unit WHERE id = ?", (row["organization_unit_id"],)
        ).fetchone()[0])]
    return {"items": items}


def list_review_tasks(ctx: AuthContext, queue_id: int, status: str = "pending") -> dict[str, Any]:
    queues = {item["id"] for item in list_review_queues(ctx)["items"]}
    if queue_id not in queues:
        raise AuthorizationError("无权查看该组织审核队列")
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT rt.*, ia.submitted_identifier, ia.submitted_name, ia.identity_type,
                   au.username, au.display_name
            FROM review_task rt LEFT JOIN identity_application ia
              ON rt.resource_type = 'identity_application' AND ia.id = rt.resource_id
            LEFT JOIN app_user au ON au.id = ia.user_id
            WHERE rt.queue_id = ? AND (? = 'all' OR rt.status = ?)
            ORDER BY rt.due_at, rt.id
            """,
            (queue_id, status, status),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}
