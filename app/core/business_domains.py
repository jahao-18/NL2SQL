"""Demo role and business-domain permissions for the teaching platform."""
from __future__ import annotations


import json
import base64
import hashlib
import hmac
import secrets
import time
import re
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any

from app.core.config import ROOT_DIR, settings
from app.core.schema import SchemaInfo


ALL_TABLES = {
    "college",
    "major",
    "class_group",
    "student",
    "teacher",
    "course",
    "course_prerequisite",
    "teaching_class",
    "enrollment",
    "score",
    "evaluation",
    "assignment",
    "assignment_submission",
    "attendance",
    "learning_activity",
    "scholarship",
    "academic_warning",
    "counselor_class_group",
    "support_case",
    "support_request",
    "academic_teaching_operations_summary",
    "college_teacher_workload_summary",
    "college_quality_summary",
}


PROTECTED_RESOURCES: dict[str, dict[str, Any]] = {
    "teacher_identity": {
        "label": "教师身份",
        "aliases": [
            "教师", "老师", "任课教师", "教员", "授课教师", "教师姓名", "教师是谁",
            "teacher", "teachers", "instructor", "instructors", "faculty", "professor",
            "professors", "lecturer", "lecturers", "teacher name", "teacher names",
        ],
        "columns": ["teacher.id", "teacher.name", "teacher.teacher_no", "teaching_class.teacher_id"],
    },
    "student_identity": {
        "label": "学生身份",
        "aliases": [
            "学生名单", "学生姓名", "学生学号", "学号", "姓名", "挂科名单", "其他学生",
            "student name", "student names", "student list", "student roster", "student no",
            "student number", "student id", "students who", "failed students",
        ],
        "columns": [
            "student.id", "student.name", "student.student_no",
            "assignment_submission.student_id", "evaluation.student_id", "attendance.student_id",
            "learning_activity.student_id", "scholarship.student_id",
            "academic_warning.student_id",
        ],
    },
    "evaluation_raw": {
        "label": "评教原文",
        "aliases": [
            "评教原文", "评价原文", "评价内容", "评教评论", "评论内容", "原始评价",
            "evaluation comment", "evaluation comments", "review text", "review comments",
            "feedback text", "raw feedback", "comments",
        ],
        "columns": ["evaluation.comment"],
    },
    "schoolwide_scope": {
        "label": "全校范围",
        "aliases": [
            "全校", "所有学院", "各学院", "其他学院", "外学院", "全院校", "全体学院",
            "school-wide", "schoolwide", "whole school", "all colleges", "all departments",
            "other colleges", "other departments", "campus-wide",
        ],
        "columns": [],
    },
    "teacher_private_id": {
        "label": "教师工号",
        "aliases": ["教师工号", "工号", "teacher no", "teacher number", "employee number", "employee id"],
        "columns": ["teacher.teacher_no"],
    },
}


BUSINESS_DOMAINS: dict[str, dict[str, Any]] = {
    "student_affairs": {
        "name": "student_affairs",
        "label": "学生学籍域",
        "description": "面向学籍、学院、专业、班级和学生规模分析。",
        "tables": ["college", "major", "class_group", "student", "scholarship", "academic_warning"],
    },
    "teaching_operation": {
        "name": "teaching_operation",
        "label": "教学运行域",
        "description": "面向课程、开课班、选课容量和教学安排分析。",
        "tables": ["college", "teacher", "course", "course_prerequisite", "teaching_class", "enrollment", "assignment", "assignment_submission", "attendance", "learning_activity"],
    },
    "grade_quality": {
        "name": "grade_quality",
        "label": "成绩质量域",
        "description": "面向成绩分布、及格率、挂科率和课程质量分析。",
        "tables": ["college", "major", "student", "course", "teaching_class", "enrollment", "score", "assignment_submission", "attendance", "learning_activity"],
    },
    "student_support": {
        "name": "student_support",
        "label": "学习支持域",
        "description": "面向辅导员和授权学生工作场景的学习支持待办、事实依据和跟进分析。",
        "tables": ["college", "major", "class_group", "student", "academic_warning", "attendance", "assignment", "assignment_submission", "counselor_class_group", "support_case", "support_request"],
    },
    "evaluation_feedback": {
        "name": "evaluation_feedback",
        "label": "评教反馈域",
        "description": "面向学生评教、教师授课反馈和课程体验分析。",
        "tables": ["college", "teacher", "course", "teaching_class", "evaluation", "attendance", "learning_activity"],
    },
    "personal_learning": {
        "name": "personal_learning",
        "label": "个人学习域",
        "description": "面向学生个人选课、成绩和课程评价查询演示。",
        "tables": ["course", "course_prerequisite", "teaching_class", "enrollment", "score", "evaluation", "assignment", "assignment_submission", "attendance", "learning_activity", "scholarship", "academic_warning"],
    },
    "academic_operations_summary": {
        "name": "academic_operations_summary", "label": "教务运行汇总域",
        "description": "仅面向教务的教学任务、容量、异常和成绩状态汇总。",
        "tables": ["academic_teaching_operations_summary"],
    },
    "college_operations_summary": {
        "name": "college_operations_summary", "label": "学院教学汇总域",
        "description": "仅面向本学院的课程运行、教师工作量和质量聚合。",
        "tables": ["academic_teaching_operations_summary", "college_teacher_workload_summary", "college_quality_summary"],
    },
}


ROLES: dict[str, dict[str, Any]] = {
    "admin": {
        "name": "admin",
        "label": "校级管理员",
        "description": "可查看全部教学业务域和治理配置。",
        "domains": list(BUSINESS_DOMAINS),
        "features": ["dashboard", "ask", "knowledge", "schema", "governance", "assistant_quality", "data_access", "approval_center", "organization_management", "personal_center"],
    },
    "academic_office": {
        "name": "academic_office",
        "label": "教务处老师",
        "description": "关注学籍、教学运行和成绩质量。",
        "domains": ["academic_operations_summary"],
        "features": ["dashboard", "ask", "teaching_operations", "notifications", "approval_center", "organization_management", "personal_center"],
        "denied_resources": ["evaluation_raw", "teacher_private_id"],
    },
    "college_manager": {
        "name": "college_manager",
        "label": "学院负责人",
        "description": "关注本学院教学运行、成绩质量和评教反馈。",
        "domains": ["college_operations_summary"],
        "features": ["dashboard", "ask", "teaching_operations", "notifications", "approval_center", "organization_management", "personal_center"],
        "denied_resources": ["schoolwide_scope", "evaluation_raw", "teacher_private_id"],
    },
    "teacher": {
        "name": "teacher",
        "label": "任课教师",
        "description": "关注授课班级、成绩质量和评教反馈。",
        "domains": ["teaching_operation", "grade_quality", "evaluation_feedback"],
        "features": ["dashboard", "ask", "assignments", "course_analytics", "course_space", "attendance", "course_questions", "teaching_operations", "notifications", "personal_center"],
        "denied_resources": ["schoolwide_scope", "evaluation_raw", "teacher_private_id"],
        # 任课教师可以在本人授课班范围内查看学生姓名；内部关联键仍只允许
        # 用于 JOIN/WHERE，不能作为问数结果直接输出。
        "denied_columns": [
            "student.id", "assignment_submission.student_id", "evaluation.student_id",
            "attendance.student_id", "learning_activity.student_id",
        ],
    },
    "counselor": {
        "name": "counselor",
        "label": "辅导员",
        "description": "关注本人所带行政班学生的学习支持待办和跟进记录。",
        "domains": ["student_support"],
        "features": ["dashboard", "ask", "student_support", "approval_center", "personal_center"],
        "denied_resources": ["schoolwide_scope", "teacher_private_id", "evaluation_raw"],
    },
    "student": {
        "name": "student",
        "label": "学生",
        "description": "关注个人学习相关的课程、选课、成绩和评教。",
        "domains": ["personal_learning"],
        "features": ["dashboard", "ask", "assignments", "course_analytics", "course_space", "attendance", "course_questions", "notifications", "student_support", "personal_center"],
        "denied_resources": ["teacher_identity", "student_identity", "schoolwide_scope"],
    },
    "pending": {
        "name": "pending",
        "label": "身份待审核",
        "description": "账号已创建，等待校内身份审核。",
        "domains": [],
        "features": ["registration_status"],
    },
    "staff": {
        "name": "staff",
        "label": "已验证教职工",
        "description": "已完成教职工身份验证，等待教学任务或岗位任命。",
        "domains": [],
        "features": ["personal_center"],
    },
    "identity_reviewer": {
        "name": "identity_reviewer",
        "label": "身份审核员",
        "description": "处理所属学院的教职工与学生身份申请。",
        "domains": [],
        "features": ["approval_center", "personal_center"],
    },
    "self_service": {
        "name": "self_service",
        "label": "个人自助",
        "description": "仅用于个人资料、账号安全和生命周期状态，不包含教学或管理数据权限。",
        "domains": [],
        "features": ["personal_center"],
    },
}


NAVIGATION_ITEMS: tuple[dict[str, str], ...] = (
    {"view": "dashboard-view", "label": "首页", "feature": "dashboard", "group": "工作台"},
    {"view": "assignment-workflow-view", "label": "课程作业", "feature": "assignments", "group": "教学业务"},
    {"view": "course-analytics-view", "label": "课程分析", "feature": "course_analytics", "group": "教学业务"},
    {"view": "course-space-view", "label": "我的课程", "feature": "course_space", "group": "教学业务"},
    {"view": "attendance-view", "label": "课程考勤", "feature": "attendance", "group": "教学业务"},
    {"view": "course-questions-view", "label": "课程答疑", "feature": "course_questions", "group": "教学业务"},
    {"view": "teaching-operations-view", "label": "教学运行", "feature": "teaching_operations", "group": "教学管理"},
    {"view": "notifications-view", "label": "通知中心", "feature": "notifications", "group": "我的"},
    {"view": "support-workbench-view", "label": "学习支持", "feature": "student_support", "group": "学生工作"},
    {"view": "identity-approval-view", "label": "身份审核", "feature": "approval_center", "group": "组织管理"},
    {"view": "organization-view", "label": "组织与岗位", "feature": "organization_management", "group": "组织管理"},
    {"view": "assistant-view", "label": "智能问数", "feature": "ask", "group": "智能助手"},
    {"view": "data-access-view", "label": "数据源", "feature": "data_access", "group": "平台运维"},
    {"view": "kb-list-view", "label": "问数知识库", "feature": "knowledge", "group": "平台运维"},
    {"view": "schema-console-view", "label": "Schema 画像", "feature": "schema", "group": "平台运维"},
    {"view": "governance-queue-view", "label": "质量治理", "feature": "governance", "group": "平台运维"},
    {"view": "assistant-quality-view", "label": "助手运营", "feature": "assistant_quality", "group": "平台运维"},
    {"view": "governance-settings-view", "label": "治理设置", "feature": "governance", "group": "平台运维"},
    {"view": "profile-view", "label": "个人中心", "feature": "personal_center", "group": "我的"},
)


def navigation_for(ctx: "AuthContext") -> list[dict[str, str]]:
    home_labels = {
        "student": "我的首页",
        "teacher": "教学首页",
        "counselor": "工作首页",
        "academic_office": "教务首页",
        "college_manager": "学院首页",
        "admin": "运维首页",
    }
    return [
        {"view": item["view"], "label": home_labels.get(ctx.role, item["label"]) if item["view"] == "dashboard-view" else item["label"], "group": item["group"]}
        for item in NAVIGATION_ITEMS
        if item["feature"] in ctx.features
    ]


def scope_label(ctx: "AuthContext") -> str:
    return {
        "student": "仅限本人学习数据",
        "teacher": "仅限本人授课班级",
        "counselor": "仅限本人所带行政班",
        "college_manager": "仅限本学院",
        "academic_office": "教务管理授权范围",
        "admin": "平台运维范围",
        "pending": "身份审核通过前不可访问业务数据",
        "staff": "已验证教职工基础身份",
        "identity_reviewer": "仅限授权学院身份审核",
        "self_service": "仅限本人账号与生命周期信息",
    }.get(ctx.role, "当前岗位授权范围")


DEMO_USERS: dict[str, dict[str, Any]] = {
    "admin": {"username": "admin", "display_name": "校级管理员", "role": "admin", "password": "123456", "scope": {}},
    "jwc": {"username": "jwc", "display_name": "教务处老师", "role": "academic_office", "password": "123456", "scope": {}},
    "college": {"username": "college", "display_name": "学院负责人", "role": "college_manager", "password": "123456", "scope": {"college_id": 1}},
    "teacher": {"username": "teacher", "display_name": "任课教师", "role": "teacher", "password": "123456", "scope": {"teacher_id": 37}},
    "student": {"username": "student", "display_name": "学生用户", "role": "student", "password": "123456", "scope": {"student_id": 1}},
    "stu_zhang": {"username": "stu_zhang", "display_name": "张同学", "role": "student", "password": "123456", "scope": {"student_id": 900001}},
    "stu_wang": {"username": "stu_wang", "display_name": "王同学", "role": "student", "password": "123456", "scope": {"student_id": 900002}},
    "stu_liu": {"username": "stu_liu", "display_name": "刘同学", "role": "student", "password": "123456", "scope": {"student_id": 900003}},
    "stu_chen": {"username": "stu_chen", "display_name": "陈同学", "role": "student", "password": "123456", "scope": {"student_id": 900004}},
    "stu_zhao": {"username": "stu_zhao", "display_name": "赵同学", "role": "student", "password": "123456", "scope": {"student_id": 900005}},
    "stu_sun": {"username": "stu_sun", "display_name": "孙同学", "role": "student", "password": "123456", "scope": {"student_id": 900006}},
    "tea_li": {"username": "tea_li", "display_name": "李老师", "role": "teacher", "password": "123456", "scope": {"teacher_id": 900001}},
    "tea_zhou": {"username": "tea_zhou", "display_name": "周老师", "role": "teacher", "password": "123456", "scope": {"teacher_id": 900002}},
    "counselor_chen": {"username": "counselor_chen", "display_name": "陈辅导员", "role": "counselor", "password": "123456", "scope": {"counselor_id": 900001, "college_id": 1}},
    "counselor_lin": {"username": "counselor_lin", "display_name": "林辅导员", "role": "counselor", "password": "123456", "scope": {"counselor_id": 900002, "college_id": 1}},
}

PASSWORD_FILE = ROOT_DIR / "data" / "auth_passwords.json"


class AuthenticationError(ValueError):
    """请求没有携带有效的演示登录令牌。"""


class AuthorizationError(PermissionError):
    """当前演示角色无权执行操作。"""


@dataclass(frozen=True)
class AuthContext:
    username: str
    display_name: str
    role: str
    role_label: str
    domains: tuple[str, ...]
    allowed_tables: frozenset[str]
    denied_columns: frozenset[str]
    denied_terms: tuple[str, ...]
    denied_resources: tuple[str, ...]
    row_scope: dict[str, Any]
    features: frozenset[str]
    user_id: int | None = None
    account_status: str = "active"
    role_binding_id: int | None = None
    available_roles: tuple[dict[str, Any], ...] = ()
    session_version: int = 0
    must_reset_password: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def public_role_options() -> list[dict[str, Any]]:
    return [
        {
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
            "role_label": ROLES[user["role"]]["label"],
            "description": ROLES[user["role"]]["description"],
        }
        for user in DEMO_USERS.values()
    ]


def role_settings() -> dict[str, Any]:
    return {
        "domains": list(BUSINESS_DOMAINS.values()),
        "protected_resources": list(PROTECTED_RESOURCES.values()),
        "roles": [
            {
                **role,
                "tables": sorted(tables_for_domains(role["domains"])),
                "domain_items": [BUSINESS_DOMAINS[d] for d in role["domains"]],
                "denied_resource_items": [
                    PROTECTED_RESOURCES[d] for d in role.get("denied_resources", []) if d in PROTECTED_RESOURCES
                ],
            }
            for role in ROLES.values()
        ],
    }


def tables_for_domains(domains: list[str] | tuple[str, ...]) -> set[str]:
    tables: set[str] = set()
    for name in domains:
        domain = BUSINESS_DOMAINS.get(name)
        if domain:
            tables.update(domain["tables"])
    return tables


def _database_user(username: str) -> dict[str, Any] | None:
    from app.core import teaching_migrations
    import sqlite3

    if not teaching_migrations.DB_PATH.exists():
        return None
    teaching_migrations.expire_due_position_assignments()
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT id, username, display_name, password_hash, active, status, session_version,
                       failed_login_count, locked_until, must_reset_password, last_login_at
                FROM app_user WHERE lower(username) = lower(?)
                """,
                (username,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        if not row:
            return None
        identity_scope: dict[str, Any] = {}
        identities = conn.execute(
            """
            SELECT id, person_type, entity_id FROM person_identity
            WHERE user_id = ? AND status = 'verified' ORDER BY id
            """,
            (row["id"],),
        ).fetchall()
        for identity in identities:
            identity_scope["person_identity_id"] = int(identity["id"])
            if identity["person_type"] == "student":
                identity_scope["student_id"] = int(identity["entity_id"])
            elif identity["person_type"] == "staff":
                identity_scope["staff_id"] = int(identity["entity_id"])
                staff = conn.execute(
                    "SELECT teacher_id, counselor_id, college_id FROM staff WHERE id = ?",
                    (identity["entity_id"],),
                ).fetchone()
                if staff:
                    for key in ("teacher_id", "counselor_id", "college_id"):
                        if staff[key] is not None:
                            identity_scope[key] = int(staff[key])
    return {
        "id": int(row["id"]),
        "username": str(row["username"]),
        "display_name": str(row["display_name"]),
        "password_hash": str(row["password_hash"]),
        "active": bool(row["active"]),
        "status": str(row["status"] or ("active" if row["active"] else "disabled")),
        "session_version": int(row["session_version"] or 0),
        "failed_login_count": int(row["failed_login_count"] or 0),
        "locked_until": row["locked_until"],
        "must_reset_password": bool(row["must_reset_password"]),
        "last_login_at": row["last_login_at"],
        "identity_scope": identity_scope,
    }


def _active_role_bindings(user: dict[str, Any]) -> list[dict[str, Any]]:
    from app.core import teaching_migrations
    import sqlite3

    if user.get("id") is None or not teaching_migrations.DB_PATH.exists():
        return []
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT urb.id, urb.role_code, urb.valid_from, urb.valid_until, urb.source,
                       urb.selectable,
                       pa.assignment_type, ops.title AS position_title, ou.name AS organization_name
                FROM user_role_binding urb
                LEFT JOIN position_assignment pa ON pa.id = urb.position_assignment_id
                LEFT JOIN organization_position_slot ops ON ops.id = pa.position_slot_id
                LEFT JOIN organization_unit ou ON ou.id = ops.organization_unit_id
                WHERE urb.user_id = ? AND urb.status = 'active'
                  AND datetime(urb.valid_from) <= datetime('now')
                  AND (urb.valid_until IS NULL OR datetime(urb.valid_until) > datetime('now'))
                  AND (pa.id IS NULL OR (pa.status = 'active'
                       AND (pa.valid_until IS NULL OR datetime(pa.valid_until) > datetime('now'))))
                ORDER BY CASE urb.role_code
                    WHEN 'college_manager' THEN 1 WHEN 'academic_office' THEN 2
                    WHEN 'admin' THEN 3 WHEN 'student' THEN 4
                    WHEN 'teacher' THEN 5 WHEN 'counselor' THEN 6
                    WHEN 'identity_reviewer' THEN 7 ELSE 8 END, urb.id
                """,
                (user["id"],),
            ).fetchall()
            bindings: list[dict[str, Any]] = []
            for row in rows:
                scopes = [
                    {"scope_type": scope[0], "scope_id": scope[1]}
                    for scope in conn.execute(
                        "SELECT scope_type, scope_id FROM role_scope_binding WHERE role_binding_id = ? ORDER BY id",
                        (row["id"],),
                    ).fetchall()
                ]
                role = ROLES.get(str(row["role_code"]), ROLES["staff"])
                bindings.append({
                    "id": int(row["id"]),
                    "role": str(row["role_code"]),
                    "role_label": role["label"],
                    "position_title": row["position_title"] or role["label"],
                    "organization_name": row["organization_name"],
                    "assignment_type": row["assignment_type"],
                    "valid_from": row["valid_from"],
                    "valid_until": row["valid_until"],
                    "source": row["source"],
                    "selectable": bool(row["selectable"]),
                    "scopes": scopes,
                })
            return bindings
        except sqlite3.OperationalError:
            return []


def _user_for_binding(user: dict[str, Any], binding: dict[str, Any] | None) -> dict[str, Any]:
    if not binding:
        scoped = dict(user)
        scoped["role"] = "pending"
        scoped["scope"] = {}
        scoped["role_binding_id"] = None
        return scoped
    scoped = dict(user)
    scoped["role"] = binding["role"]
    scoped["role_binding_id"] = binding["id"]
    role = binding["role"]
    identity = user.get("identity_scope") or {}
    scope: dict[str, Any] = {}
    for item in binding.get("scopes") or []:
        scope_type, scope_id = item["scope_type"], item["scope_id"]
        if scope_type == "self":
            scope["student_id"] = scope_id
        elif scope_type == "teacher":
            scope["teacher_id"] = scope_id
        elif scope_type == "college" and "college_id" not in scope:
            scope["college_id"] = scope_id
        elif scope_type == "person_identity":
            scope["person_identity_id"] = scope_id
    if role == "student" and "student_id" not in scope and identity.get("student_id"):
        scope["student_id"] = identity["student_id"]
    elif role == "teacher" and "teacher_id" not in scope and identity.get("teacher_id"):
        scope["teacher_id"] = identity["teacher_id"]
    elif role == "counselor" and identity.get("counselor_id"):
        scope["counselor_id"] = identity["counselor_id"]
        if identity.get("college_id"):
            scope["college_id"] = identity["college_id"]
    scoped["scope"] = scope
    return scoped


def _selectable_bindings(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the base self-service identity hidden while a business identity exists."""
    selectable = [item for item in bindings if item.get("selectable", True)]
    return selectable or bindings


def _user_record(username: str) -> dict[str, Any] | None:
    # Runtime authentication is database-backed.  DEMO_USERS only describes
    # optional login-page hints and is never an authorization fallback.
    return _database_user(username)


def user_from_token(token: str | None, *, allow_pending: bool = False) -> AuthContext:
    raw = (token or "").strip()
    if not raw or "." not in raw:
        raise AuthenticationError("请先登录")
    encoded, signature = raw.split(".", 1)
    expected = hmac.new(settings.auth_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise AuthenticationError("登录状态无效，请重新登录")
    try:
        padding = "=" * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
        try:
            payload = json.loads(decoded)
        except json.JSONDecodeError:
            payload = {"sub": decoded}
        username = str(payload.get("sub") or "")
        exp = int(payload.get("exp") or 0)
        requested_binding_id = int(payload.get("rb") or 0) or None
        token_session_version = int(payload.get("sv") or 0)
    except Exception as exc:
        raise AuthenticationError("登录状态无效，请重新登录") from exc
    if exp and exp < int(time.time()):
        raise AuthenticationError("登录状态已过期，请重新登录")
    user = _user_record(username)
    if not user:
        raise AuthenticationError("登录状态无效，请重新登录")
    if not user.get("active", True) or user.get("status") in {"disabled", "locked", "security_suspended", "archived", "closed"}:
        raise AuthenticationError("账号已停用、冻结或锁定")
    if int(user.get("session_version") or 0) != token_session_version:
        raise AuthenticationError("登录状态已失效，请重新登录")
    bindings = _selectable_bindings(_active_role_bindings(user))
    selected = None
    if requested_binding_id is not None:
        selected = next((item for item in bindings if item["id"] == requested_binding_id), None)
        if selected is None:
            raise AuthenticationError("当前工作身份已失效，请重新选择")
    elif bindings:
        selected = bindings[0]
    elif user.get("status") not in {"pending", "pending_approval"}:
        raise AuthenticationError("账号没有有效工作身份，请联系组织管理员")
    scoped_user = _user_for_binding(user, selected)
    scoped_user["available_roles"] = bindings
    ctx = auth_context(scoped_user)
    if ctx.account_status != "active" and not allow_pending:
        raise AuthorizationError("身份审核通过后才能访问教学业务")
    return ctx


def token_for(username: str, role_binding_id: int | None = None) -> str:
    user = _user_record(username)
    if not user:
        raise AuthenticationError("账号不存在")
    if not user.get("active", True) or user.get("status") in {"disabled", "locked", "security_suspended", "archived", "closed"}:
        raise AuthenticationError("账号已停用、冻结或锁定")
    bindings = _selectable_bindings(_active_role_bindings(user))
    if role_binding_id is None and bindings:
        role_binding_id = int(bindings[0]["id"])
    if not bindings and user.get("status") not in {"pending", "pending_approval"}:
        raise AuthorizationError("当前账号没有有效工作身份")
    if role_binding_id is not None and not any(item["id"] == role_binding_id for item in bindings):
        raise AuthorizationError("当前账号没有该工作身份")
    payload = {
        "sub": username,
        "rb": role_binding_id,
        "sv": int(user.get("session_version") or 0),
        "exp": int(time.time()) + 12 * 60 * 60,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii").rstrip("=")
    signature = hmac.new(settings.auth_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def require_admin(token: str | None) -> AuthContext:
    ctx = user_from_token(token)
    if not ctx.is_admin:
        raise AuthorizationError("只有管理员可以执行此操作")
    return ctx


def login(username: str, password: str) -> AuthContext:
    user = _user_record(username.strip().lower())
    now = datetime.now(timezone.utc)
    if user and user.get("locked_until"):
        try:
            if datetime.fromisoformat(str(user["locked_until"])) > now:
                raise ValueError("登录失败次数过多，请稍后再试")
        except ValueError as exc:
            if str(exc) == "登录失败次数过多，请稍后再试":
                raise
    stored_password = user.get("password_hash") if user else ""
    if not user or not _verify_password(password, str(stored_password or _password_for(username))):
        if user and user.get("id") is not None:
            from app.core import teaching_migrations
            import sqlite3
            failures = int(user.get("failed_login_count") or 0) + 1
            locked_until = (now + timedelta(minutes=15)).isoformat(timespec="seconds") if failures >= 5 else None
            with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
                conn.execute(
                    "UPDATE app_user SET failed_login_count = ?, locked_until = ?, updated_at = ? WHERE id = ?",
                    (failures, locked_until, now.isoformat(timespec="seconds"), user["id"]),
                )
                conn.commit()
        raise ValueError("用户名或密码错误")
    if not user.get("active", True) or user.get("status") in {"disabled", "locked", "security_suspended", "archived", "closed"}:
        raise ValueError("账号已停用、冻结或锁定")
    if user.get("id") is not None:
        from app.core import teaching_migrations
        import sqlite3
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            conn.execute(
                "UPDATE app_user SET failed_login_count = 0, locked_until = NULL, last_login_at = ?, updated_at = ? WHERE id = ?",
                (now.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"), user["id"]),
            )
            conn.commit()
        user = _user_record(username.strip().lower()) or user
    bindings = _selectable_bindings(_active_role_bindings(user))
    if not bindings and user.get("status") not in {"pending", "pending_approval"}:
        raise ValueError("账号没有有效工作身份，请联系组织管理员")
    selected = bindings[0] if bindings else None
    scoped = _user_for_binding(user, selected)
    scoped["available_roles"] = bindings
    return auth_context(scoped)


def switch_role(ctx: AuthContext, role_binding_id: int) -> tuple[AuthContext, str]:
    """Switch the current session to another active binding and revoke its old token."""
    from app.core import teaching_migrations
    import sqlite3

    user = _database_user(ctx.username)
    if not user or user.get("status") != "active" or not user.get("active", True):
        raise AuthenticationError("账号已停用或不存在")
    bindings = _selectable_bindings(_active_role_bindings(user))
    target = next((item for item in bindings if int(item["id"]) == int(role_binding_id)), None)
    if target is None:
        raise AuthorizationError("当前账号没有该工作身份，或该岗位已经失效")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE app_user SET session_version = session_version + 1, updated_at = ? WHERE id = ?",
            (now, user["id"]),
        )
        conn.execute(
            """
            INSERT INTO audit_log(actor_user, actor_role, resource_type, resource_id, action,
                                  before_state, after_state, created_at)
            VALUES (?, ?, 'role_session', ?, 'switched', ?, ?, ?)
            """,
            (
                ctx.username,
                ctx.role,
                int(role_binding_id),
                json.dumps({"role": ctx.role, "role_binding_id": ctx.role_binding_id}, ensure_ascii=False),
                json.dumps({"role": target["role"], "role_binding_id": target["id"]}, ensure_ascii=False),
                now,
            ),
        )
        conn.commit()
    refreshed = _database_user(ctx.username)
    if not refreshed:
        raise AuthenticationError("账号不存在")
    refreshed_bindings = _selectable_bindings(_active_role_bindings(refreshed))
    selected = next((item for item in refreshed_bindings if int(item["id"]) == int(role_binding_id)), None)
    if selected is None:
        raise AuthenticationError("目标工作身份已经失效，请重新登录")
    scoped = _user_for_binding(refreshed, selected)
    scoped["available_roles"] = refreshed_bindings
    switched_ctx = auth_context(scoped)
    return switched_ctx, token_for(ctx.username, role_binding_id)


def _load_passwords() -> dict[str, str]:
    if not PASSWORD_FILE.exists():
        return {}
    try:
        data = json.loads(PASSWORD_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(k): str(v) for k, v in data.items() if k in DEMO_USERS}


def _save_passwords(data: dict[str, str]) -> None:
    PASSWORD_FILE.parent.mkdir(parents=True, exist_ok=True)
    PASSWORD_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _password_for(username: str) -> str:
    user = DEMO_USERS.get(username)
    if not user:
        return ""
    return _load_passwords().get(username, user["password"])


def _hash_password(password: str) -> str:
    salt = secrets.token_urlsafe(12)
    iterations = 260000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${base64.b64encode(digest).decode('ascii')}"


def _verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if not stored.startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(stored, password)
    try:
        _algorithm, iterations, salt, digest = stored.split("$", 3)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
        return hmac.compare_digest(base64.b64decode(digest.encode("ascii")), actual)
    except Exception:
        return False


def change_password(username: str, old_password: str, new_password: str) -> AuthContext:
    user = _user_record(username)
    if not user:
        raise ValueError("账号不存在")
    stored_password = str(user.get("password_hash") or _password_for(username))
    if not _verify_password(old_password, stored_password):
        raise ValueError("原密码错误")
    clean = new_password.strip()
    if len(clean) < 6 or len(clean) > 32:
        raise ValueError("新密码长度需为 6-32 位")
    from app.core import teaching_migrations
    import sqlite3

    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.execute(
            """
            UPDATE app_user SET password_hash = ?, must_reset_password = 0,
                session_version = session_version + 1, updated_at = datetime('now')
            WHERE username = ?
            """,
            (_hash_password(clean), username),
        )
        if conn.total_changes == 0:
            raise ValueError("账号不存在")
        conn.commit()
    refreshed = _user_record(username) or user
    bindings = _selectable_bindings(_active_role_bindings(refreshed))
    if not bindings and refreshed.get("status") not in {"pending", "pending_approval"}:
        raise ValueError("账号没有有效工作身份，请联系组织管理员")
    scoped = _user_for_binding(refreshed, bindings[0] if bindings else None)
    scoped["available_roles"] = bindings
    return auth_context(scoped)


def auth_context(user: dict[str, Any]) -> AuthContext:
    role = ROLES.get(user["role"], ROLES["pending"])
    domains = tuple(role["domains"])
    denied_resources = tuple(role.get("denied_resources") or [])
    denied_columns = set(role.get("denied_columns") or [])
    denied_terms = list(role.get("denied_terms") or [])
    for resource_name in denied_resources:
        resource = PROTECTED_RESOURCES.get(resource_name)
        if not resource:
            continue
        denied_columns.update(resource.get("columns") or [])
        denied_terms.extend(resource.get("aliases") or [])
    return AuthContext(
        username=user["username"],
        display_name=user["display_name"],
        role=role["name"],
        role_label=role["label"],
        domains=domains,
        allowed_tables=frozenset(tables_for_domains(domains)),
        denied_columns=frozenset(denied_columns),
        denied_terms=tuple(dict.fromkeys(denied_terms)),
        denied_resources=denied_resources,
        row_scope=dict(user.get("scope") or {}),
        features=frozenset(role["features"]),
        user_id=int(user["id"]) if user.get("id") is not None else None,
        account_status=str(user.get("status") or "active"),
        role_binding_id=int(user["role_binding_id"]) if user.get("role_binding_id") is not None else None,
        available_roles=tuple(user.get("available_roles") or ()),
        session_version=int(user.get("session_version") or 0),
        must_reset_password=bool(user.get("must_reset_password")),
    )


def auth_payload(ctx: AuthContext, token: str | None = None) -> dict[str, Any]:
    return {
        "token": token or token_for(ctx.username),
        "user": {
            "username": ctx.username,
            "display_name": ctx.display_name,
            "role": ctx.role,
            "role_label": ctx.role_label,
            "domains": list(ctx.domains),
            "domain_items": [BUSINESS_DOMAINS[d] for d in ctx.domains],
            "scope_label": scope_label(ctx),
            "features": sorted(ctx.features),
            "navigation": navigation_for(ctx),
            "account_status": ctx.account_status,
            "role_binding_id": ctx.role_binding_id,
            "available_roles": list(ctx.available_roles),
            "must_reset_password": ctx.must_reset_password,
        },
    }


def row_scope_context(ctx: AuthContext) -> str:
    if ctx.role == "student" and ctx.row_scope.get("student_id"):
        return (
            f"当前登录账号绑定 student_id = {ctx.row_scope['student_id']}。"
            "用户说“我/我的/本人/my”时，必须限定 enrollment.student_id 为该值；"
            "询问“选了哪些课程/我的课程”时优先 SELECT DISTINCT course.name 去重。"
        )
    if ctx.role == "teacher" and ctx.row_scope.get("teacher_id"):
        return (
            f"当前登录账号绑定 teacher_id = {ctx.row_scope['teacher_id']}。"
            "用户说“我负责/我的课程/本人授课/my classes”时，必须限定 teaching_class.teacher_id 为该值；"
            "可以展示本人授课班学生姓名，但必须通过 teaching_class 与 enrollment/assignment 关系验证课程归属；"
            "不得输出数据库内部 student_id，也不得查询其他教师课程的学生。"
        )
    if ctx.role == "college_manager" and ctx.row_scope.get("college_id"):
        cid = ctx.row_scope["college_id"]
        return (
            f"当前登录账号绑定 college_id = {cid}。"
            "用户说“本学院/我院/our college”时，课程按 course.college_id 限定，"
            "学生按 student.college_id 限定，教师按 teacher.college_id 限定。"
        )
    if ctx.role == "counselor" and ctx.row_scope.get("counselor_id"):
        return (
            f"当前登录账号绑定 counselor_id = {ctx.row_scope['counselor_id']}。"
            "查询支持个案/请求时必须限定对应表的 counselor_id；查询学生、预警、考勤或作业事实时，"
            "必须连接 counselor_class_group，并限定 counselor_class_group.counselor_id 为该值，"
            "从而只分析本人所带行政班。"
        )
    return ""


def normalize_policy_text(value: str) -> str:
    return re.sub(r"[\s_\-./,，。？?！!：:；;（）()【】\\[\\]{}]+", "", value.lower())


def denied_question_hit(question: str, denied_terms: list[str] | tuple[str, ...]) -> str | None:
    raw = question.lower()
    normalized = normalize_policy_text(question)
    for term in denied_terms:
        if not term:
            continue
        t_raw = term.lower()
        t_norm = normalize_policy_text(term)
        if t_raw in raw or (t_norm and t_norm in normalized):
            return term
    return None


def filter_schema_info(
    info: SchemaInfo,
    allowed_tables: set[str] | frozenset[str],
    denied_columns: set[str] | frozenset[str] | None = None,
) -> SchemaInfo:
    allowed = set(allowed_tables)
    denied = set(denied_columns or []) | set(info.blocked_columns)
    if allowed >= set(info.tables):
        tables = dict(info.tables)
        columns = dict(info.columns)
        pure_ddl = info.pure_ddl
    else:
        tables = {name: cols for name, cols in info.tables.items() if name in allowed}
        columns = {name: cols for name, cols in info.columns.items() if name in allowed}
        pure_ddl = filter_ddl(info.pure_ddl, allowed)
    if denied:
        # 外键/主键可能是安全落实 JOIN 和行级范围所必需的。它们继续出现在
        # 授权 Schema 中，但 blocked_columns 会禁止作为结果输出；姓名、原文、
        # 工号等非关联敏感字段仍从 Schema 中彻底移除。
        join_only = {
            full for full in denied
            if "." in full and (full.rsplit(".", 1)[1] == "id" or full.rsplit(".", 1)[1].endswith("_id"))
        }
        hidden = denied - join_only
        tables = {
            table: [col for col in cols if f"{table}.{col}" not in hidden]
            for table, cols in tables.items()
        }
        columns = {
            table: [col for col in cols if f"{table}.{col.get('column_name')}" not in hidden]
            for table, cols in columns.items()
        }
        pure_ddl = filter_ddl_columns(pure_ddl, hidden, set(tables))
        if join_only:
            pure_ddl += (
                "\n\n-- 以下字段仅允许用于 JOIN/WHERE 与服务端行级范围校验，严禁 SELECT 输出：\n-- "
                + ", ".join(sorted(join_only))
            )
    ddl_text = pure_ddl
    return SchemaInfo(
        ddl_text=ddl_text,
        tables=tables,
        pure_ddl=pure_ddl,
        columns=columns,
        blocked_columns=set(info.blocked_columns) | denied,
    )


def filter_ddl(ddl: str, allowed_tables: set[str]) -> str:
    statements = [s.strip() for s in ddl.split(";") if s.strip()]
    kept: list[str] = []
    for stmt in statements:
        match = re.search(r"CREATE\s+TABLE\s+[`\"\[]?([A-Za-z_][A-Za-z0-9_]*)", stmt, re.IGNORECASE)
        if match and match.group(1) in allowed_tables:
            kept.append(stmt + ";")
    return "\n\n".join(kept)


def filter_ddl_columns(ddl: str, denied_columns: set[str], allowed_tables: set[str] | None = None) -> str:
    current_table = ""
    out: list[str] = []
    denied_by_table: dict[str, set[str]] = {}
    for full in denied_columns:
        if "." in full:
            table, column = full.split(".", 1)
            denied_by_table.setdefault(table, set()).add(column)
    for line in ddl.splitlines():
        table_match = re.search(r"CREATE\s+TABLE\s+[`\"\[]?([A-Za-z_][A-Za-z0-9_]*)", line, re.IGNORECASE)
        if table_match:
            current_table = table_match.group(1)
        col_match = re.match(r"\s*[`\"\[]?([A-Za-z_][A-Za-z0-9_]*)[`\"\]]?\s+", line)
        if current_table and col_match:
            full = f"{current_table}.{col_match.group(1)}"
            if full in denied_columns:
                continue
        if current_table:
            denied_here = denied_by_table.get(current_table, set())
            if any(re.search(rf"\b{re.escape(col)}\b", line) for col in denied_here):
                continue
        if allowed_tables:
            ref_match = re.search(r"REFERENCES\s+[`\"\[]?([A-Za-z_][A-Za-z0-9_]*)", line, re.IGNORECASE)
            if ref_match and ref_match.group(1) not in allowed_tables:
                continue
        out.append(line)
    return "\n".join(out)
