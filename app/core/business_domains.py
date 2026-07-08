"""Demo role and business-domain permissions for the teaching platform."""
from __future__ import annotations


import json
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import ROOT_DIR
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
            "assignment_submission.student_id", "attendance.student_id",
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
        "tables": ["college", "major", "student", "course", "teaching_class", "enrollment", "score", "assignment_submission", "attendance", "learning_activity", "academic_warning"],
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
}


ROLES: dict[str, dict[str, Any]] = {
    "admin": {
        "name": "admin",
        "label": "校级管理员",
        "description": "可查看全部教学业务域和治理配置。",
        "domains": list(BUSINESS_DOMAINS),
        "features": ["dashboard", "ask", "knowledge", "schema", "governance", "domain_settings", "role_management"],
    },
    "academic_office": {
        "name": "academic_office",
        "label": "教务处老师",
        "description": "关注学籍、教学运行和成绩质量。",
        "domains": ["student_affairs", "teaching_operation", "grade_quality"],
        "features": ["dashboard", "ask", "knowledge", "schema", "domain_settings", "role_management"],
        "denied_resources": ["evaluation_raw", "teacher_private_id"],
    },
    "college_manager": {
        "name": "college_manager",
        "label": "学院负责人",
        "description": "关注本学院教学运行、成绩质量和评教反馈。",
        "domains": ["teaching_operation", "grade_quality", "evaluation_feedback"],
        "features": ["dashboard", "ask", "knowledge", "domain_settings", "role_management"],
        "denied_resources": ["schoolwide_scope", "evaluation_raw", "teacher_private_id"],
    },
    "teacher": {
        "name": "teacher",
        "label": "任课教师",
        "description": "关注授课班级、成绩质量和评教反馈。",
        "domains": ["teaching_operation", "grade_quality", "evaluation_feedback"],
        "features": ["dashboard", "ask", "domain_settings", "role_management"],
        "denied_resources": ["schoolwide_scope", "student_identity", "evaluation_raw", "teacher_private_id"],
    },
    "student": {
        "name": "student",
        "label": "学生",
        "description": "关注个人学习相关的课程、选课、成绩和评教。",
        "domains": ["personal_learning"],
        "features": ["ask", "domain_settings", "role_management"],
        "denied_resources": ["teacher_identity", "student_identity", "schoolwide_scope"],
    },
}


DEMO_USERS: dict[str, dict[str, Any]] = {
    "admin": {"username": "admin", "display_name": "校级管理员", "role": "admin", "password": "123456", "scope": {}},
    "jwc": {"username": "jwc", "display_name": "教务处老师", "role": "academic_office", "password": "123456", "scope": {}},
    "college": {"username": "college", "display_name": "学院负责人", "role": "college_manager", "password": "123456", "scope": {"college_id": 1}},
    "teacher": {"username": "teacher", "display_name": "任课教师", "role": "teacher", "password": "123456", "scope": {"teacher_id": 37}},
    "student": {"username": "student", "display_name": "学生用户", "role": "student", "password": "123456", "scope": {"student_id": 1}},
}

PASSWORD_FILE = ROOT_DIR / "data" / "auth_passwords.json"


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


def user_from_token(token: str | None) -> AuthContext:
    username = (token or "admin").strip() or "admin"
    user = DEMO_USERS.get(username)
    if not user:
        user = DEMO_USERS["admin"]
    return auth_context(user)


def login(username: str, password: str) -> AuthContext:
    user = DEMO_USERS.get(username)
    if not user or _password_for(username) != password:
        raise ValueError("用户名或密码错误")
    return auth_context(user)


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


def change_password(username: str, old_password: str, new_password: str) -> AuthContext:
    user = DEMO_USERS.get(username)
    if not user:
        raise ValueError("账号不存在")
    if _password_for(username) != old_password:
        raise ValueError("原密码错误")
    clean = new_password.strip()
    if len(clean) < 6 or len(clean) > 32:
        raise ValueError("新密码长度需为 6-32 位")
    data = _load_passwords()
    data[username] = clean
    _save_passwords(data)
    return auth_context(user)


def auth_context(user: dict[str, Any]) -> AuthContext:
    role = ROLES[user["role"]]
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
    )


def auth_payload(ctx: AuthContext) -> dict[str, Any]:
    return {
        "token": ctx.username,
        "user": {
            "username": ctx.username,
            "display_name": ctx.display_name,
            "role": ctx.role,
            "role_label": ctx.role_label,
            "domains": list(ctx.domains),
            "domain_items": [BUSINESS_DOMAINS[d] for d in ctx.domains],
            "allowed_tables": sorted(ctx.allowed_tables),
            "denied_columns": sorted(ctx.denied_columns),
            "denied_terms": list(ctx.denied_terms),
            "denied_resources": list(ctx.denied_resources),
            "row_scope": dict(ctx.row_scope),
            "features": sorted(ctx.features),
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
            "只做统计或课程层面分析，不展示学生身份字段。"
        )
    if ctx.role == "college_manager" and ctx.row_scope.get("college_id"):
        cid = ctx.row_scope["college_id"]
        return (
            f"当前登录账号绑定 college_id = {cid}。"
            "用户说“本学院/我院/our college”时，课程按 course.college_id 限定，"
            "学生按 student.college_id 限定，教师按 teacher.college_id 限定。"
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
    if not allowed or allowed >= set(info.tables):
        tables = dict(info.tables)
        columns = dict(info.columns)
        pure_ddl = info.pure_ddl
    else:
        tables = {name: cols for name, cols in info.tables.items() if name in allowed}
        columns = {name: cols for name, cols in info.columns.items() if name in allowed}
        pure_ddl = filter_ddl(info.pure_ddl, allowed)
    if denied:
        tables = {
            table: [col for col in cols if f"{table}.{col}" not in denied]
            for table, cols in tables.items()
        }
        columns = {
            table: [col for col in cols if f"{table}.{col.get('column_name')}" not in denied]
            for table, cols in columns.items()
        }
        pure_ddl = filter_ddl_columns(pure_ddl, denied, set(tables))
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
