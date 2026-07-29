"""Server-side validation for V3 assistant page context."""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core import teaching_migrations
from app.core.business_domains import AuthContext, AuthorizationError
from app.core.data_sources import get_source


AssistantPage = Literal[
    "dashboard",
    "assistant",
    "course_space",
    "assignment_workflow",
    "attendance",
    "course_analytics",
    "support_workbench",
    "teaching_operations",
    "notifications",
    "governance",
    "data_access",
    "profile",
]

PAGE_FEATURES: dict[str, str] = {
    "dashboard": "dashboard",
    "assistant": "ask",
    "course_space": "course_space",
    "assignment_workflow": "assignments",
    "attendance": "attendance",
    "course_analytics": "course_analytics",
    "support_workbench": "student_support",
    "teaching_operations": "teaching_operations",
    "notifications": "notifications",
    "governance": "governance",
    "data_access": "data_access",
    "profile": "personal_center",
}

PAGE_CONTEXT_FIELDS: dict[str, frozenset[str]] = {
    "dashboard": frozenset({"academic_year", "semester", "time_range", "filters"}),
    "assistant": frozenset({"source", "teaching_class_id", "student_id", "college_id", "academic_year", "semester", "time_range", "filters"}),
    "course_space": frozenset({"teaching_class_id", "academic_year", "semester", "filters"}),
    "assignment_workflow": frozenset({"teaching_class_id", "student_id", "academic_year", "semester", "filters"}),
    "attendance": frozenset({"teaching_class_id", "student_id", "academic_year", "semester", "time_range", "filters"}),
    "course_analytics": frozenset({"teaching_class_id", "academic_year", "semester", "time_range", "filters"}),
    "support_workbench": frozenset({"student_id", "college_id", "time_range", "filters"}),
    "teaching_operations": frozenset({"teaching_class_id", "college_id", "academic_year", "semester", "time_range", "filters"}),
    "notifications": frozenset({"filters"}),
    "governance": frozenset({"time_range", "filters"}),
    "data_access": frozenset({"filters"}),
    "profile": frozenset(),
}

_RESERVED_FILTER_KEYS = frozenset(
    {
        "allowed_tables",
        "denied_columns",
        "domains",
        "role",
        "role_binding_id",
        "session_version",
        "teacher_id",
        "counselor_id",
        "student_id",
        "college_id",
        "teaching_class_id",
        "user_id",
        "username",
    }
)
_FILTER_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")


class AssistantTimeRange(BaseModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_range(self) -> "AssistantTimeRange":
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("时间范围必须包含时区")
        if self.start > self.end:
            raise ValueError("时间范围开始时间不能晚于结束时间")
        return self


class AssistantPageContext(BaseModel):
    page: AssistantPage
    source: str | None = Field(
        None,
        min_length=2,
        max_length=49,
        pattern=r"^[A-Za-z][A-Za-z0-9_]{1,48}$",
    )
    teaching_class_id: int | None = Field(None, gt=0)
    student_id: int | None = Field(None, gt=0)
    college_id: int | None = Field(None, gt=0)
    academic_year: int | None = Field(None, ge=2000, le=2200)
    semester: str | None = Field(None, min_length=1, max_length=40)
    time_range: AssistantTimeRange | None = None
    filters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("semester", mode="before")
    @classmethod
    def normalize_semester(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("filters")
    @classmethod
    def validate_filters(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("filters 必须是可序列化的 JSON 对象") from exc
        if len(encoded.encode("utf-8")) > 4096:
            raise ValueError("filters 序列化后不能超过 4 KB")
        if len(value) > 50:
            raise ValueError("filters 最多包含 50 个字段")
        for key in value:
            if not _FILTER_KEY_PATTERN.fullmatch(key):
                raise ValueError(f"非法筛选字段：{key}")
        return value


@dataclass(frozen=True)
class AssistantContextResolution:
    auth_context: AuthContext
    effective_context: dict[str, Any]
    ignored_fields: dict[str, Any]
    rejected_fields: dict[str, Any]


class AssistantContextAuthorizationError(AuthorizationError):
    """Authorization failure carrying the client context fields that were rejected."""

    def __init__(self, message: str, rejected_fields: dict[str, Any]):
        super().__init__(message)
        self.rejected_fields = rejected_fields


def resolve_assistant_context(
    auth: AuthContext,
    request_context: AssistantPageContext | dict[str, Any],
) -> AssistantContextResolution:
    """Intersect untrusted page context with the current server authorization."""
    context = (
        request_context
        if isinstance(request_context, AssistantPageContext)
        else AssistantPageContext.model_validate(request_context)
    )
    validate_assistant_identity(auth)
    required_feature = PAGE_FEATURES[context.page]
    if required_feature not in auth.features:
        _reject("page", context.page, "当前工作身份无权使用该页面上下文")

    raw = context.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    raw.pop("page", None)
    allowed_fields = PAGE_CONTEXT_FIELDS[context.page]
    effective: dict[str, Any] = {"page": context.page}
    ignored: dict[str, Any] = {}
    for field, value in raw.items():
        if field not in allowed_fields:
            ignored[field] = value

    if context.source is not None and "source" in allowed_fields:
        if context.source != "teaching" and not auth.is_admin:
            _reject("source", context.source, "当前工作身份只能查询教学业务数据源")
        try:
            selected_source = get_source(context.source)
        except KeyError:
            _reject("source", context.source, "数据源不存在或当前身份无权访问")
        effective["source"] = selected_source.name

    filters = raw.get("filters") or {}
    reserved = _reserved_filter_paths(filters)
    if reserved:
        _reject("filters", reserved, "筛选条件不能声明权限或身份范围")

    class_row: dict[str, Any] | None = None
    student_row: dict[str, Any] | None = None
    with _connect() as conn:
        if context.teaching_class_id is not None and "teaching_class_id" in allowed_fields:
            class_row = _resolve_teaching_class(conn, auth, context.teaching_class_id)
            effective["teaching_class_id"] = context.teaching_class_id
        if context.student_id is not None and "student_id" in allowed_fields:
            student_row = _resolve_student(conn, auth, context.student_id)
            effective["student_id"] = context.student_id
        if context.college_id is not None and "college_id" in allowed_fields:
            _resolve_college(conn, auth, context.college_id)
            effective["college_id"] = context.college_id
        _validate_context_intersection(
            conn, class_row, student_row, effective.get("college_id")
        )

    for field in ("academic_year", "semester", "time_range", "filters"):
        if field in allowed_fields and field in raw:
            effective[field] = raw[field]
    return AssistantContextResolution(
        auth_context=auth,
        effective_context=effective,
        ignored_fields=ignored,
        rejected_fields={},
    )


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(teaching_migrations.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def validate_assistant_identity(auth: AuthContext) -> None:
    """Revalidate the account, session version, role binding, and appointment."""
    if auth.user_id is None or auth.role_binding_id is None:
        _reject("auth", None, "当前助手请求缺少有效工作身份")
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT au.status AS account_status, au.active, au.session_version,
                   urb.role_code, urb.status AS binding_status,
                   datetime(urb.valid_from) <= datetime('now') AS binding_started,
                   (urb.valid_until IS NULL OR datetime(urb.valid_until) > datetime('now')) AS binding_current,
                   (pa.id IS NULL OR (pa.status = 'active' AND
                       (pa.valid_until IS NULL OR datetime(pa.valid_until) > datetime('now'))))
                       AS assignment_current
            FROM app_user au
            JOIN user_role_binding urb ON urb.user_id = au.id AND urb.id = ?
            LEFT JOIN position_assignment pa ON pa.id = urb.position_assignment_id
            WHERE au.id = ?
            """,
            (auth.role_binding_id, auth.user_id),
        ).fetchone()
    invalid = (
        row is None
        or not int(row["active"])
        or row["account_status"] != "active"
        or int(row["session_version"]) != auth.session_version
        or row["role_code"] != auth.role
        or row["binding_status"] != "active"
        or not bool(row["binding_started"])
        or not bool(row["binding_current"])
        or not bool(row["assignment_current"])
    )
    if invalid:
        _reject("auth", auth.role_binding_id, "当前工作身份或会话已经失效")


def _resolve_teaching_class(
    conn: sqlite3.Connection, auth: AuthContext, teaching_class_id: int
) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT tc.id, tc.teacher_id, tc.year AS academic_year, tc.semester,
               c.college_id, c.name AS course_name
        FROM teaching_class tc JOIN course c ON c.id = tc.course_id
        WHERE tc.id = ?
        """,
        (teaching_class_id,),
    ).fetchone()
    if row is None:
        _reject("teaching_class_id", teaching_class_id, "课程不存在或当前身份无权访问")
    allowed = False
    if auth.role == "teacher":
        allowed = int(row["teacher_id"]) == int(auth.row_scope.get("teacher_id") or -1)
    elif auth.role == "student":
        allowed = conn.execute(
            "SELECT 1 FROM enrollment WHERE teaching_class_id = ? AND student_id = ?",
            (teaching_class_id, auth.row_scope.get("student_id")),
        ).fetchone() is not None
    elif auth.role == "college_manager":
        allowed = int(row["college_id"]) == int(auth.row_scope.get("college_id") or -1)
    elif auth.role in {"academic_office", "admin"}:
        allowed = True
    if not allowed:
        _reject("teaching_class_id", teaching_class_id, "课程不存在或当前身份无权访问")
    return dict(row)


def _resolve_student(
    conn: sqlite3.Connection, auth: AuthContext, student_id: int
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, college_id, class_id FROM student WHERE id = ?", (student_id,)
    ).fetchone()
    if row is None:
        _reject("student_id", student_id, "学生不存在或当前身份无权访问")
    allowed = False
    if auth.role == "student":
        allowed = int(row["id"]) == int(auth.row_scope.get("student_id") or -1)
    elif auth.role == "counselor":
        allowed = conn.execute(
            """
            SELECT 1 FROM counselor_class_group
            WHERE counselor_id = ? AND class_group_id = ?
            """,
            (auth.row_scope.get("counselor_id"), row["class_id"]),
        ).fetchone() is not None
    elif auth.role == "admin":
        allowed = True
    if not allowed:
        _reject("student_id", student_id, "学生不存在或当前身份无权访问")
    return dict(row)


def _resolve_college(conn: sqlite3.Connection, auth: AuthContext, college_id: int) -> None:
    if conn.execute("SELECT 1 FROM college WHERE id = ?", (college_id,)).fetchone() is None:
        _reject("college_id", college_id, "学院不存在或当前身份无权访问")
    allowed = auth.role in {"academic_office", "admin"}
    if auth.role == "college_manager":
        allowed = int(auth.row_scope.get("college_id") or -1) == college_id
    elif auth.role == "teacher":
        allowed = conn.execute(
            "SELECT 1 FROM teacher WHERE id = ? AND college_id = ?",
            (auth.row_scope.get("teacher_id"), college_id),
        ).fetchone() is not None
    elif auth.role == "student":
        allowed = conn.execute(
            "SELECT 1 FROM student WHERE id = ? AND college_id = ?",
            (auth.row_scope.get("student_id"), college_id),
        ).fetchone() is not None
    elif auth.role == "counselor":
        allowed = int(auth.row_scope.get("college_id") or -1) == college_id
    if not allowed:
        _reject("college_id", college_id, "学院不存在或当前身份无权访问")


def _validate_context_intersection(
    conn: sqlite3.Connection,
    class_row: dict[str, Any] | None,
    student_row: dict[str, Any] | None,
    college_id: int | None,
) -> None:
    if class_row and college_id and int(class_row["college_id"]) != int(college_id):
        _reject("college_id", college_id, "学院与课程上下文不一致")
    if student_row and college_id and int(student_row["college_id"]) != int(college_id):
        _reject("college_id", college_id, "学院与学生上下文不一致")
    if class_row and student_row:
        enrolled = conn.execute(
            "SELECT 1 FROM enrollment WHERE teaching_class_id = ? AND student_id = ?",
            (class_row["id"], student_row["id"]),
        ).fetchone()
        if enrolled is None:
            _reject("student_id", student_row["id"], "学生不属于指定课程")


def _reserved_filter_paths(filters: dict[str, Any], prefix: str = "") -> list[str]:
    paths: list[str] = []
    for key, value in filters.items():
        path = f"{prefix}.{key}" if prefix else key
        if key in _RESERVED_FILTER_KEYS:
            paths.append(path)
        if isinstance(value, dict):
            paths.extend(_reserved_filter_paths(value, path))
    return sorted(paths)


def _reject(field: str, value: Any, message: str) -> None:
    raise AssistantContextAuthorizationError(message, {field: value})
