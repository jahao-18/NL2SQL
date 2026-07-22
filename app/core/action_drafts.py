"""V3-2.3 allowlisted assistant action drafts with confirm-time authorization."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.core import teaching_migrations
from app.core.assistant_context import AssistantPage, AssistantPageContext, resolve_assistant_context, validate_assistant_identity
from app.core.authorization import forbidden
from app.core.business_domains import AuthContext, navigation_for
from app.core.feedback import add_feedback
from app.core.governance import create_feedback_review


ActionType = Literal[
    "open_assignment_roster",
    "open_course",
    "open_support_case",
    "open_teaching_issue",
    "apply_safe_filter",
    "draft_course_notification",
    "submit_governance_feedback",
    "export_current_result",
]
ACTION_TYPES = frozenset(ActionType.__args__)
DEFAULT_TTL_SECONDS = 15 * 60


class ActionDraftError(ValueError):
    pass


class ActionDraftNotFoundError(ActionDraftError):
    pass


class ActionDraftConflictError(ActionDraftError):
    pass


class ActionDraftExpiredError(ActionDraftError):
    pass


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpenAssignmentRoster(_StrictModel):
    assignment_id: int = Field(gt=0)


class OpenCourse(_StrictModel):
    teaching_class_id: int = Field(gt=0)


class OpenSupportCase(_StrictModel):
    support_case_id: int = Field(gt=0)


class OpenTeachingIssue(_StrictModel):
    teaching_issue_id: int = Field(gt=0)


class ApplySafeFilter(_StrictModel):
    page: AssistantPage
    filters: dict[str, Any] = Field(default_factory=dict)
    teaching_class_id: int | None = Field(None, gt=0)
    student_id: int | None = Field(None, gt=0)
    college_id: int | None = Field(None, gt=0)
    academic_year: int | None = Field(None, ge=2000, le=2200)
    semester: str | None = Field(None, min_length=1, max_length=40)


class DraftCourseNotification(_StrictModel):
    teaching_class_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=4000)


class SubmitGovernanceFeedback(_StrictModel):
    source: Literal["teaching"] = "teaching"
    kind: Literal["correct", "incorrect"]
    category: str = Field(default="", max_length=80)
    reason: str = Field(default="", max_length=1000)
    question: str = Field(default="", max_length=500)


class ExportCurrentResult(_StrictModel):
    turn_id: int = Field(gt=0)
    format: Literal["csv"] = "csv"


PARAMETER_MODELS: dict[str, type[BaseModel]] = {
    "open_assignment_roster": OpenAssignmentRoster,
    "open_course": OpenCourse,
    "open_support_case": OpenSupportCase,
    "open_teaching_issue": OpenTeachingIssue,
    "apply_safe_filter": ApplySafeFilter,
    "draft_course_notification": DraftCourseNotification,
    "submit_governance_feedback": SubmitGovernanceFeedback,
    "export_current_result": ExportCurrentResult,
}


class ActionDraftCreate(BaseModel):
    action_type: ActionType
    parameters: dict[str, Any]
    session_id: int | None = Field(None, gt=0)
    turn_id: int | None = Field(None, gt=0)
    client_request_id: str | None = Field(None, min_length=8, max_length=100)


def create_action_draft(
    auth: AuthContext, payload: ActionDraftCreate | dict[str, Any]
) -> dict[str, Any]:
    request = payload if isinstance(payload, ActionDraftCreate) else ActionDraftCreate.model_validate(payload)
    validate_assistant_identity(auth)
    parameters = _normalize_parameters(request.action_type, request.parameters)
    with _connect() as conn:
        _validate_links(conn, auth, request.session_id, request.turn_id)
        preview = _authorize_and_preview(conn, auth, request.action_type, parameters)
        if request.client_request_id:
            existing = conn.execute(
                "SELECT * FROM assistant_action_draft WHERE user_id=? AND role_binding_id=? AND client_request_id=?",
                (auth.user_id, auth.role_binding_id, request.client_request_id),
            ).fetchone()
            if existing:
                if existing["action_type"] != request.action_type or json.loads(existing["parameters_json"]) != parameters:
                    raise ActionDraftConflictError("client_request_id 已用于其他动作草稿")
                return _public(existing)
        now = _now()
        draft_id = uuid4().hex
        expires_at = now + timedelta(seconds=DEFAULT_TTL_SECONDS)
        conn.execute(
            """INSERT INTO assistant_action_draft
               (id,user_id,role_binding_id,session_id,turn_id,action_type,parameters_json,
                preview_json,status,client_request_id,expires_at,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?, 'pending', ?,?,?,?)""",
            (
                draft_id, auth.user_id, auth.role_binding_id, request.session_id, request.turn_id,
                request.action_type, _json(parameters), _json(preview), request.client_request_id,
                _iso(expires_at), _iso(now), _iso(now),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM assistant_action_draft WHERE id=?", (draft_id,)).fetchone()
    return _public(row)


def get_action_draft(auth: AuthContext, draft_id: str) -> dict[str, Any]:
    validate_assistant_identity(auth)
    with _connect() as conn:
        row = _owned_row(conn, auth, draft_id)
        if row["status"] == "pending" and _parse(row["expires_at"]) <= _now():
            conn.execute(
                "UPDATE assistant_action_draft SET status='expired', updated_at=? WHERE id=? AND status='pending'",
                (_iso(_now()), draft_id),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM assistant_action_draft WHERE id=?", (draft_id,)).fetchone()
    return _public(row)


def confirm_action_draft(auth: AuthContext, draft_id: str) -> dict[str, Any]:
    validate_assistant_identity(auth)
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = _owned_row(conn, auth, draft_id)
        if row["status"] == "confirmed":
            raise ActionDraftConflictError("动作草稿已经确认，不能重复执行")
        if row["status"] != "pending":
            raise ActionDraftConflictError("动作草稿当前状态不可确认")
        now = _now()
        if _parse(row["expires_at"]) <= now:
            conn.execute(
                "UPDATE assistant_action_draft SET status='expired', updated_at=? WHERE id=?",
                (_iso(now), draft_id),
            )
            conn.commit()
            raise ActionDraftExpiredError("动作草稿已过期，请重新生成")
        parameters = json.loads(row["parameters_json"])
        _authorize_and_preview(conn, auth, row["action_type"], parameters)
        result = _execute(conn, auth, row["action_type"], parameters)
        changed = conn.execute(
            """UPDATE assistant_action_draft
               SET status='confirmed', confirmed_at=?, result_json=?, updated_at=?
               WHERE id=? AND status='pending'""",
            (_iso(now), _json(result), _iso(now), draft_id),
        ).rowcount
        if changed != 1:
            raise ActionDraftConflictError("动作草稿已经被处理")
        conn.commit()
        confirmed = conn.execute("SELECT * FROM assistant_action_draft WHERE id=?", (draft_id,)).fetchone()
        return _public(confirmed)
    except ActionDraftExpiredError:
        raise
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def create_suggested_action_drafts(
    auth: AuthContext,
    *,
    session_id: int,
    turn_id: int,
    question: str | None = None,
    context: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Materialize only server-generated, allowlisted suggestions."""
    proposals: list[tuple[str, dict[str, Any], str]] = []
    has_notification_proposal = False
    for item in list(result.get("suggested_actions") or []):
        if item.get("type") == "open_page":
            page = _page_for_view(str(item.get("target_view") or ""))
            if page:
                proposals.append(("apply_safe_filter", {"page": page, "filters": {}}, str(item.get("label") or "打开页面")))
        elif item.get("type") == "draft_course_notification":
            parameters = item.get("parameters")
            if isinstance(parameters, dict):
                has_notification_proposal = True
                proposals.append(("draft_course_notification", parameters, str(item.get("label") or "保存课程提醒草稿")))
        elif item.get("type") == "open_support_case":
            parameters = item.get("parameters")
            if isinstance(parameters, dict):
                proposals.append(("open_support_case", parameters, str(item.get("label") or "打开学习支持个案")))
        elif item.get("type") == "open_teaching_issue":
            parameters = item.get("parameters")
            if isinstance(parameters, dict):
                proposals.append(("open_teaching_issue", parameters, str(item.get("label") or "打开教学异常")))
        elif item.get("type") == "apply_safe_filter":
            parameters = item.get("parameters")
            if isinstance(parameters, dict):
                proposals.append(("apply_safe_filter", parameters, str(item.get("label") or "应用安全筛选")))
    if not has_notification_proposal:
        reminder = _course_reminder_proposal(auth, question or "", context, result)
        if reminder is not None:
            proposals.append(reminder)
    data = result.get("data") or {}
    if result.get("answer_type") in {"metric", "business_state", "nl2sql"} and result.get("status") == "success" and int(data.get("row_count") or 0) > 0:
        proposals.append(("export_current_result", {"turn_id": turn_id, "format": "csv"}, "导出当前结果"))
    created: list[dict[str, Any]] = []
    for index, (action_type, parameters, label) in enumerate(proposals):
        try:
            draft = create_action_draft(
                auth,
                ActionDraftCreate(
                    action_type=TypeAdapter(ActionType).validate_python(action_type),
                    parameters=parameters,
                    session_id=session_id,
                    turn_id=turn_id,
                    client_request_id=f"turn-{turn_id}-{action_type}-suggestion-{index}",
                ),
            )
        except Exception:
            continue
        created.append(
            {
                "type": draft["action_type"],
                "label": label,
                "draft_id": draft["id"],
                "preview": draft["preview"],
                "expires_at": draft["expires_at"],
                "requires_confirmation": True,
            }
        )
    return created


def _course_reminder_proposal(
    auth: AuthContext,
    question: str,
    context: dict[str, Any],
    result: dict[str, Any],
) -> tuple[str, dict[str, Any], str] | None:
    """Suggest a course-wide, non-sending draft after a scoped risk-roster answer."""
    class_id = context.get("teaching_class_id")
    if (
        auth.role != "teacher"
        or not class_id
        or context.get("page") not in {
            "course_space",
            "assignment_workflow",
            "attendance",
            "course_analytics",
        }
        or result.get("status") != "success"
        or result.get("answer_type") not in {"metric", "business_state", "nl2sql"}
        or int((result.get("data") or {}).get("row_count") or 0) <= 0
    ):
        return None

    text = question.strip().lower()
    asks_for_people = any(token in text for token in ("哪些", "名单", "同学", "学生", "谁"))
    describes_attention = any(
        token in text
        for token in (
            "未交",
            "没交",
            "未提交",
            "没提交",
            "未完成",
            "没完成",
            "缺勤",
            "旷课",
            "连续缺勤",
        )
    )
    if not asks_for_people or not describes_attention:
        return None

    return (
        "draft_course_notification",
        {
            "teaching_class_id": int(class_id),
            "title": "课程学习任务提醒",
            "body": "请及时查看当前课程的作业提交与考勤情况，并按课程要求完成相关学习任务。如有特殊情况，请及时联系任课教师。",
        },
        "保存全班课程提醒草稿（未发送）",
    )


def _normalize_parameters(action_type: str, raw: dict[str, Any]) -> dict[str, Any]:
    model = PARAMETER_MODELS.get(action_type)
    if model is None:
        raise ActionDraftError("动作类型不在服务端白名单中")
    try:
        value = model.model_validate(raw)
    except ValidationError as exc:
        raise ActionDraftError("动作参数不符合服务端白名单定义") from exc
    if isinstance(value, DraftCourseNotification):
        value.title = value.title.strip()
        value.body = value.body.strip()
        if not value.title or not value.body:
            raise ActionDraftError("通知标题和正文不能为空")
    return value.model_dump(mode="json", exclude_none=True)


def _authorize_and_preview(
    conn: sqlite3.Connection, auth: AuthContext, action_type: str, p: dict[str, Any]
) -> dict[str, Any]:
    if action_type == "open_assignment_roster":
        row = conn.execute(
            """SELECT a.id,a.title,a.teaching_class_id,tc.teacher_id
               FROM assignment a JOIN teaching_class tc ON tc.id=a.teaching_class_id WHERE a.id=?""",
            (p["assignment_id"],),
        ).fetchone()
        if not row or auth.role != "teacher" or row["teacher_id"] != auth.row_scope.get("teacher_id"):
            forbidden()
        return {"label": f"打开作业名单：{row['title']}", "mutates_data": False}
    if action_type == "open_course":
        resolved = resolve_assistant_context(auth, {"page": "course_space", "teaching_class_id": p["teaching_class_id"]})
        row = conn.execute(
            "SELECT c.name FROM teaching_class tc JOIN course c ON c.id=tc.course_id WHERE tc.id=?",
            (resolved.effective_context["teaching_class_id"],),
        ).fetchone()
        return {"label": f"打开课程：{row['name']}", "mutates_data": False}
    if action_type == "open_support_case":
        row = _support_case(conn, auth, p["support_case_id"])
        return {"label": f"打开学习支持事项：{row['title']}", "mutates_data": False}
    if action_type == "open_teaching_issue":
        row = _teaching_issue(conn, auth, p["teaching_issue_id"])
        return {"label": f"打开教学异常：{row['evidence']}", "mutates_data": False}
    if action_type == "apply_safe_filter":
        context = resolve_assistant_context(auth, AssistantPageContext.model_validate(p)).effective_context
        return {"label": "应用筛选并打开页面", "page": context["page"], "filters": context.get("filters", {}), "mutates_data": False}
    if action_type == "draft_course_notification":
        row = _teacher_class(conn, auth, p["teaching_class_id"])
        return {"label": f"为课程“{row['course_name']}”保存通知草稿", "title": p["title"], "recipient_scope": "当前课程已选学生", "mutates_data": True, "sends_notification": False}
    if action_type == "submit_governance_feedback":
        if "ask" not in auth.features:
            forbidden()
        return {"label": "提交问数治理反馈", "kind": p["kind"], "category": p.get("category", ""), "mutates_data": True}
    if action_type == "export_current_result":
        _owned_turn(conn, auth, p["turn_id"])
        return {"label": "导出当前结果为 CSV", "format": "csv", "mutates_data": False}
    raise ActionDraftError("动作类型不在服务端白名单中")


def _execute(conn: sqlite3.Connection, auth: AuthContext, action_type: str, p: dict[str, Any]) -> dict[str, Any]:
    if action_type == "open_assignment_roster":
        return _navigation_result("assignment-workflow-view", {"assignment_id": p["assignment_id"]})
    if action_type == "open_course":
        return _navigation_result("course-space-view", {"teaching_class_id": p["teaching_class_id"]})
    if action_type == "open_support_case":
        return _navigation_result("support-workbench-view", {"support_case_id": p["support_case_id"]})
    if action_type == "open_teaching_issue":
        return _navigation_result("teaching-operations-view", {"teaching_issue_id": p["teaching_issue_id"]})
    if action_type == "apply_safe_filter":
        page = p["page"]
        return _navigation_result(_view_for_page(auth, page), {k: v for k, v in p.items() if k != "page"})
    if action_type == "draft_course_notification":
        now = _iso(_now())
        cursor = conn.execute(
            """INSERT INTO course_announcement
               (teaching_class_id,publisher_user_id,title,body,status,published_at,created_at,updated_at)
               VALUES (?,?,?,?, 'draft', NULL,?,?)""",
            (p["teaching_class_id"], auth.user_id, p["title"], p["body"], now, now),
        )
        return {"kind": "business_draft", "resource_type": "course_announcement", "resource_id": int(cursor.lastrowid), "status": "draft", "sent": False, "target_view": "course-space-view", "teaching_class_id": p["teaching_class_id"]}
    if action_type == "submit_governance_feedback":
        feedback = add_feedback({**p, "source_label": "教学业务库", "sql": "", "explanation": {"submitted_by": auth.username, "role": auth.role}})
        create_feedback_review(feedback)
        return {"kind": "governance_feedback", "feedback_id": feedback["id"], "status": feedback["status"]}
    if action_type == "export_current_result":
        return {"kind": "client_export", "turn_id": p["turn_id"], "format": "csv", "target": "current_assistant_result"}
    raise ActionDraftError("动作类型不在服务端白名单中")


def _validate_links(conn: sqlite3.Connection, auth: AuthContext, session_id: int | None, turn_id: int | None) -> None:
    if session_id is not None:
        row = conn.execute("SELECT id FROM assistant_session WHERE id=? AND user_id=? AND role_binding_id=? AND deleted_at IS NULL", (session_id, auth.user_id, auth.role_binding_id)).fetchone()
        if not row:
            raise ActionDraftNotFoundError("助手会话不存在")
    if turn_id is not None:
        row = _owned_turn(conn, auth, turn_id)
        if session_id is not None and int(row["session_id"]) != session_id:
            raise ActionDraftConflictError("助手轮次不属于指定会话")


def _owned_turn(conn: sqlite3.Connection, auth: AuthContext, turn_id: int) -> sqlite3.Row:
    row = conn.execute(
        """SELECT t.id,t.session_id,t.status FROM assistant_turn t JOIN assistant_session s ON s.id=t.session_id
           WHERE t.id=? AND s.user_id=? AND s.role_binding_id=? AND s.deleted_at IS NULL""",
        (turn_id, auth.user_id, auth.role_binding_id),
    ).fetchone()
    if not row:
        raise ActionDraftNotFoundError("助手轮次不存在")
    return row


def _teacher_class(conn: sqlite3.Connection, auth: AuthContext, class_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT tc.id,tc.teacher_id,c.name course_name FROM teaching_class tc JOIN course c ON c.id=tc.course_id WHERE tc.id=?", (class_id,)).fetchone()
    if not row or auth.role != "teacher" or row["teacher_id"] != auth.row_scope.get("teacher_id"):
        forbidden()
    return row


def _support_case(conn: sqlite3.Connection, auth: AuthContext, case_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT sc.*,s.class_id FROM support_case sc JOIN student s ON s.id=sc.student_id WHERE sc.id=?", (case_id,)).fetchone()
    allowed = bool(row) and (
        (auth.role == "counselor" and row["counselor_id"] == auth.row_scope.get("counselor_id"))
        or (auth.role == "student" and row["student_id"] == auth.row_scope.get("student_id") and bool(row["visible_to_student"]))
    )
    if not allowed:
        forbidden()
    return row


def _teaching_issue(conn: sqlite3.Connection, auth: AuthContext, issue_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM teaching_issue WHERE id=?", (issue_id,)).fetchone()
    allowed = bool(row) and (auth.role == "academic_office" or (auth.role == "college_manager" and row["college_id"] == auth.row_scope.get("college_id")))
    if not allowed:
        forbidden()
    return row


def _owned_row(conn: sqlite3.Connection, auth: AuthContext, draft_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM assistant_action_draft WHERE id=? AND user_id=? AND role_binding_id=?", (draft_id, auth.user_id, auth.role_binding_id)).fetchone()
    if not row:
        raise ActionDraftNotFoundError("动作草稿不存在")
    return row


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"], "action_type": row["action_type"], "parameters": json.loads(row["parameters_json"]),
        "preview": json.loads(row["preview_json"]), "status": row["status"], "session_id": row["session_id"],
        "turn_id": row["turn_id"], "expires_at": row["expires_at"], "confirmed_at": row["confirmed_at"],
        "result": json.loads(row["result_json"]) if row["result_json"] else None, "created_at": row["created_at"],
    }


def _navigation_result(target_view: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "navigation", "target_view": target_view, "parameters": parameters}


PAGE_VIEWS = {
    "dashboard": "dashboard-view", "assistant": "assistant-view", "course_space": "course-space-view",
    "assignment_workflow": "assignment-workflow-view", "attendance": "attendance-view",
    "course_analytics": "course-analytics-view", "support_workbench": "support-workbench-view",
    "teaching_operations": "teaching-operations-view", "notifications": "notifications-view",
    "governance": "governance-queue-view", "data_access": "data-access-view", "profile": "profile-view",
}


def _page_for_view(view: str) -> str | None:
    return next((page for page, candidate in PAGE_VIEWS.items() if candidate == view), None)


def _view_for_page(auth: AuthContext, page: str) -> str:
    target = PAGE_VIEWS[page]
    if target not in {item["view"] for item in navigation_for(auth)}:
        forbidden()
    return target


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(teaching_migrations.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
