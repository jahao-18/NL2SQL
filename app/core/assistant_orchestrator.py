"""Unified V3 assistant routing across deterministic and legacy NL2SQL paths."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.assistant_context import AssistantPageContext, resolve_assistant_context
from app.core.action_drafts import create_suggested_action_drafts
from app.core.assignment_workflow import teacher_missing_assignment_roster
from app.core.answer_evidence import (
    enrich_answer,
    persist_execution_trace,
    public_trace,
)
from app.core.assistant_sessions import (
    AssistantSessionCreate,
    AssistantTurnCreate,
    append_turn,
    create_session,
    get_session,
    recent_turns,
)
from app.core.business_domains import AuthContext, navigation_for, row_scope_context
from app.core.config import settings
from app.core.semantic_metrics import (
    evaluate_semantic_metric,
    match_semantic_metric,
    metric_answer_payload,
)
from app.core.support_workflow import counselor_appointment_queue, counselor_review_queue
from app.core.stage_e import assistant_issue_queue
from app.core.workbench import build_workbench
from app.models.schemas import Turn
from app.service import ask as ask_service


logger = logging.getLogger("nl2sql.assistant")
_NL2SQL_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="assistant-nl2sql")
_SESSION_HISTORY_TURNS = 5

PreferredAnswerType = Literal[
    "metric", "business_state", "nl2sql", "navigation", "unsupported"
]


class AssistantQueryOptions(BaseModel):
    preferred_answer_type: PreferredAnswerType | None = None
    include_sql: bool = True
    include_trace: bool = False
    max_rows: int | None = Field(None, ge=1, le=200)


class AssistantQueryRequest(BaseModel):
    session_id: int | None = Field(None, gt=0)
    question: str = Field(..., min_length=1, max_length=500)
    context: AssistantPageContext
    options: AssistantQueryOptions = Field(default_factory=AssistantQueryOptions)

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class AssistantQueryResponse(BaseModel):
    session_id: int
    turn_id: int
    status: Literal["success", "clarify", "rejected", "failed", "degraded"]
    answer_type: Literal[
        "metric",
        "business_state",
        "nl2sql",
        "navigation",
        "knowledge",
        "hybrid",
        "unsupported",
    ]
    answer: str = ""
    data: dict[str, Any] | None = None
    sql: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    time_range: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    metric_definitions: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    confidence: dict[str, Any] | None = None
    trace_summary: dict[str, Any] = Field(default_factory=dict)
    suggested_questions: list[str] = Field(default_factory=list)
    suggested_actions: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    clarify: str | None = None


def query_assistant(
    auth: AuthContext, payload: AssistantQueryRequest | dict[str, Any]
) -> AssistantQueryResponse:
    request = (
        payload
        if isinstance(payload, AssistantQueryRequest)
        else AssistantQueryRequest.model_validate(payload)
    )
    context_started = time.perf_counter()
    resolution = resolve_assistant_context(auth, request.context)
    context_elapsed_ms = max(0, round((time.perf_counter() - context_started) * 1000))
    if request.session_id is None:
        session = create_session(
            auth,
            AssistantSessionCreate(
                title=_default_title(request.question), context=request.context
            ),
        )
        session_id = int(session["id"])
        history: list[Turn] = []
    else:
        detail = get_session(auth, request.session_id, turn_page=1, turn_page_size=1)
        if detail["item"]["page"] != resolution.effective_context["page"]:
            from app.core.assistant_sessions import AssistantSessionConflictError

            raise AssistantSessionConflictError("请求页面与会话页面不一致")
        saved_source = (detail["item"].get("context") or {}).get("source") or "teaching"
        current_source = resolution.effective_context.get("source") or "teaching"
        if saved_source != current_source:
            from app.core.assistant_sessions import AssistantSessionConflictError

            raise AssistantSessionConflictError("请求数据源与会话数据源不一致")
        session_id = request.session_id
        history = _legacy_history(
            recent_turns(auth, session_id, limit=_SESSION_HISTORY_TURNS)
        )

    started = time.perf_counter()
    try:
        result = _dispatch(auth, request, resolution.effective_context, history)
    except Exception as exc:
        logger.exception("统一助手编排失败")
        result = _failure("ASSISTANT_INTERNAL_ERROR", "智能助手暂时不可用，请稍后重试。")
        result["trace_summary"] = {"route": "failed", "failed_stage": "orchestrator"}
    elapsed_ms = max(0, round((time.perf_counter() - started) * 1000))
    result.setdefault("trace_summary", {})["elapsed_ms"] = elapsed_ms
    if resolution.ignored_fields:
        result.setdefault("warnings", []).append(
            "部分与当前页面无关的上下文字段已忽略。"
        )
    if not request.options.include_sql:
        result["sql"] = None
    _apply_max_rows(result, request.options.max_rows)
    result, internal_trace = enrich_answer(
        auth,
        resolution.effective_context,
        result,
        context_elapsed_ms=context_elapsed_ms,
        orchestration_elapsed_ms=elapsed_ms,
    )
    result["trace_summary"] = public_trace(
        internal_trace,
        is_admin=auth.is_admin,
        include_trace=request.options.include_trace,
    )

    safe_summary = result.get("answer") or result.get("clarify") or ""
    if result.get("error"):
        safe_summary = str(result["error"].get("message") or "")
    turn = append_turn(
        auth,
        session_id,
        AssistantTurnCreate(
            question=request.question,
            answer_type=result["answer_type"],
            status=result["status"],
            context=request.context,
            safe_answer_summary=safe_summary[:1000],
            error_code=(result.get("error") or {}).get("code"),
        ),
    )
    try:
        persist_execution_trace(int(turn["id"]), result, internal_trace)
    except Exception:
        # Trace persistence is operational telemetry and must not break a valid answer.
        logger.exception("统一助手执行轨迹写入失败")
    result["suggested_actions"] = create_suggested_action_drafts(
        auth,
        session_id=session_id,
        turn_id=int(turn["id"]),
        question=request.question,
        context=resolution.effective_context,
        result=result,
    )
    return AssistantQueryResponse(session_id=session_id, turn_id=turn["id"], **result)


def _dispatch(
    auth: AuthContext,
    request: AssistantQueryRequest,
    context: dict[str, Any],
    history: list[Turn],
) -> dict[str, Any]:
    question = request.question
    if context.get("source") not in {None, "teaching"}:
        return _nl2sql(auth, question, context, history)
    missing_roster = _teacher_missing_assignment_roster_request(auth, question, context)
    if missing_roster is not None:
        return missing_roster
    support_queue = _counselor_support_queue_request(auth, question, context)
    if support_queue is not None:
        return support_queue
    teaching_issue_queue = _teaching_issue_queue_request(auth, question, context)
    if teaching_issue_queue is not None:
        return teaching_issue_queue
    notification_draft = _notification_draft_request(auth, question, context)
    if notification_draft is not None:
        return notification_draft
    semantic_metric = match_semantic_metric(auth, question, context)
    if semantic_metric is not None:
        return metric_answer_payload(
            evaluate_semantic_metric(auth, semantic_metric, context)
        )
    route = _classify(
        question,
        request.options.preferred_answer_type,
        context,
        history,
    )
    if route == "navigation":
        return _navigation(auth, question)
    if route in {"metric", "business_state"}:
        return _workbench_answer(auth, question, route)
    if route == "unsupported":
        return _unsupported()
    return _nl2sql(auth, question, context, history)


def _legacy_history(items: list[dict[str, Any]]) -> list[Turn]:
    history: list[Turn] = []
    for item in items:
        summary = str(item.get("answer_summary") or "").strip()
        if not summary:
            summary = f"上一轮回答类型：{item.get('answer_type') or 'unknown'}"
        history.append(
            Turn(
                question=str(item["question"])[:500],
                sql=summary[:2000],
                kind="clarify" if item.get("status") == "clarify" else "sql",
            )
        )
    return history


def _teaching_issue_queue_request(
    auth: AuthContext, question: str, context: dict[str, Any]
) -> dict[str, Any] | None:
    """Serve college/academic issue queues without asking an LLM to infer scope."""
    if auth.role not in {"college_manager", "academic_office"}:
        return None
    text = question.strip().lower()
    asks_issue = "异常" in text and any(
        token in text for token in ("逾期", "待处理", "未解决", "哪些", "课程", "待办")
    )
    if not asks_issue:
        return None
    overdue_only = "逾期" in text
    items = assistant_issue_queue(
        auth,
        overdue_only=overdue_only,
        college_id=context.get("college_id"),
        academic_year=context.get("academic_year"),
        semester=context.get("semester"),
    )
    rows = [
        [
            item["course_name"],
            item["college_name"],
            item["teacher_name"],
            item["evidence"],
            item["queue_state"],
            item["age_hours"],
        ]
        for item in items
    ]
    actions: list[dict[str, Any]] = []
    if items:
        actions.append({
            "type": "open_teaching_issue",
            "label": f"打开最优先异常：{items[0]['course_name']}",
            "parameters": {"teaching_issue_id": int(items[0]["id"])},
        })
    filter_parameters: dict[str, Any] = {
        "page": "teaching_operations",
        "filters": {"issue_status": "overdue" if overdue_only else "unresolved"},
    }
    for key in ("college_id", "academic_year", "semester"):
        if context.get(key) is not None:
            filter_parameters[key] = context[key]
    actions.append({
        "type": "apply_safe_filter",
        "label": "在教学异常页应用逾期筛选" if overdue_only else "在教学异常页应用待处理筛选",
        "parameters": filter_parameters,
    })
    scope_label = "本学院" if auth.role == "college_manager" else "教务授权范围"
    state_label = "逾期" if overdue_only else "未解决"
    return {
        **_base("success", "business_state"),
        "answer": f"{scope_label}共有 {len(items)} 项{state_label}教学异常。" if items else f"{scope_label}当前没有{state_label}教学异常。",
        "data": {
            "columns": ["课程", "学院", "教师", "异常依据", "处理状态", "停留小时"],
            "rows": rows,
            "row_count": len(rows),
            "truncated": len(rows) >= 200,
        },
        "evidence": [{"kind": "business_state", "label": "确定性教学异常及处理状态", "source": "teaching"}],
        "confidence": {"score": 100, "status": "done", "reason": "服务端按当前工作身份和 72 小时处理时限固定查询"},
        "suggested_actions": actions,
        "suggested_questions": ["有哪些待处理教学异常？" if overdue_only else "有哪些逾期异常？"],
        "trace_summary": {"route": "teaching_issue_queue"},
    }


def _counselor_support_queue_request(
    auth: AuthContext, question: str, context: dict[str, Any]
) -> dict[str, Any] | None:
    if auth.role != "counselor":
        return None
    text = question.strip().lower()
    asks_review = "复查" in text and any(token in text for token in ("哪些", "什么", "事项", "学生", "待办", "本周", "逾期"))
    asks_appointments = "预约" in text and any(token in text for token in ("哪些", "什么", "学生", "待处理", "待办", "本周"))
    student_id = context.get("student_id")
    if asks_review:
        items = counselor_review_queue(auth, student_id)
        rows = [[item["student_name"], item["class_name"], item["title"], item["evidence_summary"], item["review_at"], item["review_state"]] for item in items]
        overdue = sum(1 for item in items if item["review_state"] == "已逾期")
        actions = []
        if items:
            actions.append({
                "type": "open_support_case",
                "label": f"打开最优先个案：{items[0]['student_name']}",
                "parameters": {"support_case_id": int(items[0]["support_case_id"])},
            })
        return {
            **_base("success", "business_state"),
            "answer": f"本周应复查及已逾期事项共 {len(items)} 项，其中已逾期 {overdue} 项。" if items else "当前范围内没有本周应复查或已逾期事项。",
            "data": {"columns": ["学生姓名", "行政班", "支持事项", "事实依据", "复查时间", "复查状态"], "rows": rows, "row_count": len(rows), "truncated": len(rows) >= 200},
            "evidence": [{"kind": "business_state", "label": "本人负责个案、复查计划及事实依据", "source": "teaching"}],
            "confidence": {"score": 100, "status": "done", "reason": "服务端按辅导员负责范围固定查询"},
            "suggested_actions": actions,
            "suggested_questions": ["有哪些待处理学生预约？"],
            "trace_summary": {"route": "counselor_review_queue"},
        }
    if asks_appointments:
        items = counselor_appointment_queue(auth, student_id)
        rows = [[item["student_name"], item["class_name"], item["message"], item["preferred_time"], "待受理" if item["status"] == "submitted" else "已受理"] for item in items]
        return {
            **_base("success", "business_state"),
            "answer": f"当前有 {len(items)} 条待处理学生预约。" if items else "当前范围内没有待处理学生预约。",
            "data": {"columns": ["学生姓名", "行政班", "预约说明", "希望时间", "状态"], "rows": rows, "row_count": len(rows), "truncated": len(rows) >= 200},
            "evidence": [{"kind": "business_state", "label": "本人所带行政班学生预约", "source": "teaching"}],
            "confidence": {"score": 100, "status": "done", "reason": "服务端按辅导员带班范围固定查询"},
            "suggested_actions": [{"type": "open_page", "label": "打开学生预约列表", "target_view": "support-workbench-view"}] if items else [],
            "suggested_questions": ["本周有哪些待复查事项？"],
            "trace_summary": {"route": "counselor_appointment_queue"},
        }
    return None


def _teacher_missing_assignment_roster_request(
    auth: AuthContext, question: str, context: dict[str, Any]
) -> dict[str, Any] | None:
    """Route high-frequency teacher roster questions to a scoped deterministic query."""
    if auth.role != "teacher":
        return None
    text = question.strip().lower()
    asks_for_people = any(token in text for token in ("哪些", "名单", "同学", "学生", "谁", "人员"))
    asks_about_assignment = any(token in text for token in ("作业", "任务"))
    asks_about_missing = any(token in text for token in ("未交", "没交", "未提交", "没提交", "未完成", "没完成", "缺交"))
    if not (asks_for_people and asks_about_assignment and asks_about_missing):
        return None
    rows = teacher_missing_assignment_roster(auth, context.get("teaching_class_id"))
    return {
        **_base("success", "business_state"),
        "answer": f"已找到 {len(rows)} 条未交作业记录。" if rows else "当前范围内没有未交作业记录。",
        "data": {
            "columns": ["学生姓名", "课程", "作业", "截止时间"],
            "rows": [[row["student_name"], row["course_name"], row["assignment_title"], row["due_time"]] for row in rows],
            "row_count": len(rows),
            "truncated": len(rows) >= 200,
        },
        "evidence": [{"kind": "business_state", "label": "本人授课班作业提交记录", "source": "teaching"}],
        "confidence": {"score": 100, "status": "done", "reason": "服务端按任课教师范围固定查询"},
        "trace_summary": {"route": "assignment_missing_roster"},
    }


def _notification_draft_request(
    auth: AuthContext, question: str, context: dict[str, Any]
) -> dict[str, Any] | None:
    """Offer a non-sending course reminder draft only from a teacher's course page."""
    wants_draft = any(token in question for token in ("提醒草稿", "生成提醒", "通知草稿"))
    class_id = context.get("teaching_class_id")
    if not wants_draft or auth.role != "teacher" or context.get("page") != "course_space" or not class_id:
        return None
    return {
        **_base("success", "business_state"),
        "answer": "已根据当前课程生成提醒草稿预览。确认后只会保存为课程公告草稿，不会发送通知；请在课程空间显式发布。",
        "data": {"columns": [], "rows": [], "row_count": 0, "truncated": False},
        "evidence": [{"kind": "page_context", "label": "当前课程空间", "source": "teaching"}],
        "confidence": {"score": 100, "status": "done", "reason": "仅使用当前课程上下文生成草稿"},
        "suggested_actions": [{
            "type": "draft_course_notification",
            "label": "保存全班课程提醒草稿（未发送）",
            "parameters": {
                "teaching_class_id": int(class_id),
                "title": "课程学习提醒",
                "body": "请及时查看当前课程的作业与考勤情况，并按课程要求完成相关学习任务。",
            },
        }],
        "trace_summary": {"route": "course_notification_draft"},
    }


def _classify(
    question: str,
    preferred: PreferredAnswerType | None,
    context: dict[str, Any],
    history: list[Turn] | None = None,
) -> PreferredAnswerType:
    text = question.lower()
    contextual_text = "\n".join(
        [*(turn.question for turn in (history or [])), question]
    )
    has_object_scope = any(
        key in context for key in ("teaching_class_id", "student_id", "college_id")
    )
    if preferred and preferred != "unsupported":
        if preferred in {"metric", "business_state"} and has_object_scope:
            return "nl2sql"
        return preferred
    if any(word in text for word in ("怎么进入", "在哪里", "在哪", "打开", "跳转", "进入页面")):
        return "navigation"
    if not has_object_scope and any(
        word in text for word in ("待办", "待处理", "需要处理", "什么状态", "进度")
    ):
        return "business_state"
    # Explicit workbench counters keep the deterministic route. Generic quantity
    # words are evaluated after concrete data subjects so “教师数量”等业务查询
    # do not accidentally return the current role's workbench summary.
    if not has_object_scope and any(
        word in text for word in ("未读", "待批阅")
    ):
        return "metric"
    data_terms = (
        "课程",
        "学生",
        "成绩",
        "作业",
        "考勤",
        "学院",
        "教师",
        "专业",
        "班级",
        "选课",
        "评教",
        "异常",
        "支持",
        "数据",
        "统计",
    )
    if any(term in contextual_text for term in data_terms):
        return "nl2sql"
    if not has_object_scope and any(
        word in text for word in ("多少", "几个", "数量", "总数")
    ):
        return "metric"
    return "unsupported"


def _navigation(auth: AuthContext, question: str) -> dict[str, Any]:
    items = navigation_for(auth)
    aliases = {
        "课程分析": "course-analytics-view",
        "我的课程": "course-space-view",
        "作业": "assignment-workflow-view",
        "考勤": "attendance-view",
        "答疑": "course-questions-view",
        "学习支持": "support-workbench-view",
        "教学运行": "teaching-operations-view",
        "通知": "notifications-view",
        "个人中心": "profile-view",
        "数据源": "data-access-view",
        "治理": "governance-queue-view",
        "知识库": "kb-list-view",
        "智能问数": "assistant-view",
        "首页": "dashboard-view",
    }
    allowed = {item["view"]: item for item in items}
    target = next(
        (
            allowed[view]
            for label, view in aliases.items()
            if label in question and view in allowed
        ),
        None,
    )
    if target is None:
        return {
            **_base("clarify", "navigation"),
            "clarify": "请说明想进入哪个业务页面。",
            "trace_summary": {"route": "navigation"},
        }
    return {
        **_base("success", "navigation"),
        "answer": f"可以进入“{target['label']}”页面。",
        "data": {
            "columns": ["label", "target_view"],
            "rows": [[target["label"], target["view"]]],
            "row_count": 1,
            "truncated": False,
        },
        "suggested_actions": [
            {
                "type": "open_page",
                "label": f"打开{target['label']}",
                "target_view": target["view"],
                "requires_confirmation": False,
            }
        ],
        "trace_summary": {"route": "navigation"},
    }


def _workbench_answer(
    auth: AuthContext, question: str, answer_type: Literal["metric", "business_state"]
) -> dict[str, Any]:
    workbench = build_workbench(auth)
    summary = list(workbench.get("summary") or [])
    matched = [item for item in summary if str(item.get("label") or "") in question]
    selected = matched or summary
    rows = [[item.get("label"), item.get("value")] for item in selected]
    if answer_type == "metric" and selected:
        answer = "；".join(f"{item['label']}：{item['value']}" for item in selected)
    else:
        answer = "当前工作台状态为：" + "；".join(
            f"{item['label']} {item['value']}" for item in selected
        )
    return {
        **_base("success", answer_type),
        "answer": answer,
        "data": {
            "columns": ["label", "value"],
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
        },
        "evidence": [
            {
                "kind": "business_state",
                "label": "当前身份工作台固定统计",
                "source": "teaching",
                "updated_at": workbench.get("generated_at"),
            }
        ],
        "confidence": {
            "score": 100,
            "status": "done",
            "reason": "服务端固定规则计算",
        },
        "trace_summary": {"route": f"deterministic_{answer_type}"},
    }


def _nl2sql(
    auth: AuthContext,
    question: str,
    context: dict[str, Any],
    history: list[Turn] | None = None,
) -> dict[str, Any]:
    selected_source = str(context.get("source") or "teaching")
    teaching_source = selected_source == "teaching"
    glossary: list[str] = []
    row_scope: dict[str, Any] = {}
    if teaching_source:
        scope_hint = row_scope_context(auth)
        if scope_hint:
            glossary.append(scope_hint)
        glossary.append(
            "“本学期”默认指 teaching_class.year = 2025 AND teaching_class.semester = 'spring'。"
        )
        row_scope = dict(auth.row_scope)
        for key in ("teaching_class_id", "student_id", "college_id"):
            if key in context:
                row_scope[key] = context[key]
    future = _NL2SQL_EXECUTOR.submit(
        ask_service,
        question,
        history=history or [],
        source=selected_source,
        current_source=selected_source,
        user_glossary=glossary,
        allowed_tables=auth.allowed_tables if teaching_source else None,
        denied_columns=auth.denied_columns if teaching_source else None,
        denied_terms=auth.denied_terms if teaching_source else None,
        role_label=auth.role_label,
        row_scope=row_scope,
    )
    try:
        legacy = future.result(timeout=max(0.05, float(settings.llm_timeout_seconds)))
    except FutureTimeoutError:
        future.cancel()
        result = _failure(
            "ASSISTANT_NL2SQL_TIMEOUT",
            "智能问数处理超时，外部模型或检索服务暂未及时返回，请稍后重试。",
        )
        result["answer_type"] = "nl2sql"
        result["trace_summary"] = {
            "route": "nl2sql",
            "failed_stage": "model",
            "timeout_seconds": settings.llm_timeout_seconds,
        }
        return result
    if legacy.get("clarify"):
        return {
            **_base("clarify", "unsupported"),
            "clarify": legacy["clarify"],
            "trace_summary": {"route": "nl2sql", **(legacy.get("trace") or {})},
        }
    if legacy.get("error"):
        legacy_trace = legacy.get("trace") or {}
        if legacy_trace.get("result_kind") == "unsupported":
            return {
                **_base("success", "unsupported"),
                "answer": str(legacy["error"]),
                "suggested_questions": ["换一个现有字段继续查询", "查看当前可查询的数据范围"],
                "trace_summary": {"route": "nl2sql", **legacy_trace},
            }
        rejected = any(
            marker in str(legacy["error"])
            for marker in ("无权", "未授权", "不可用于问数", "没有可用于")
        )
        status = "rejected" if rejected else "failed"
        code = "ASSISTANT_QUERY_REJECTED" if rejected else "ASSISTANT_NL2SQL_FAILED"
        result = _failure(code, str(legacy["error"]), status=status)
        result["answer_type"] = "nl2sql"
        result["sql"] = legacy.get("sql")
        trace = {"route": "nl2sql", **legacy_trace}
        if not trace.get("failed_stage"):
            message = str(legacy["error"])
            trace["failed_stage"] = (
                "model" if "LLM" in message or "模型" in message
                else "validation" if rejected or "校验" in message or "未授权" in message
                else "execution" if "执行" in message or "超时" in message
                else "orchestrator"
            )
        result["trace_summary"] = trace
        return result
    rows = list(legacy.get("rows") or [])
    confidence = None
    if legacy.get("confidence") is not None:
        confidence = {
            "score": legacy["confidence"],
            "status": "done",
            "reason": (legacy.get("confidence_detail") or {}).get("reason", ""),
        }
    elif legacy.get("judge_id"):
        confidence = {"score": None, "status": "pending", "reason": "等待异步评估"}
    return {
        **_base("success", "nl2sql"),
        "answer": f"查询完成，共返回 {legacy.get('row_count', len(rows))} 行。",
        "data": {
            "columns": list(legacy.get("columns") or []),
            "rows": rows,
            "row_count": int(legacy.get("row_count") or 0),
            "truncated": bool(legacy.get("truncated")),
            "column_sources": list(legacy.get("column_sources") or []),
        },
        "sql": legacy.get("sql"),
        "evidence": [
            {
                "kind": "data",
                "label": legacy.get("source_label") or "教学业务数据",
                "source": legacy.get("source") or "teaching",
            }
        ],
        "warnings": ["结果已达到返回上限。"] if legacy.get("truncated") else [],
        "confidence": confidence,
        "trace_summary": {"route": "nl2sql", **(legacy.get("trace") or {})},
    }


def _unsupported() -> dict[str, Any]:
    return {
        **_base("success", "unsupported"),
        "answer": "当前助手主要处理高校教学数据、业务状态和页面导航问题。",
        "trace_summary": {"route": "unsupported"},
        "suggested_questions": ["我有哪些待办？", "本学期我有多少门课程？"],
    }


def _failure(
    code: str,
    message: str,
    *,
    status: Literal["rejected", "failed"] = "failed",
) -> dict[str, Any]:
    return {
        **_base(status, "unsupported"),
        "error": {"code": code, "message": message, "retryable": status == "failed"},
    }


def _base(status: str, answer_type: str) -> dict[str, Any]:
    return {
        "status": status,
        "answer_type": answer_type,
        "answer": "",
        "data": None,
        "sql": None,
        "scope": {},
        "time_range": None,
        "evidence": [],
        "metric_definitions": [],
        "warnings": [],
        "confidence": None,
        "trace_summary": {},
        "suggested_questions": [],
        "suggested_actions": [],
        "error": None,
        "clarify": None,
    }


def _scope(auth: AuthContext, context: dict[str, Any]) -> dict[str, Any]:
    scope = {
        "role": auth.role,
        "role_binding_id": auth.role_binding_id,
        "description": auth.role_label,
    }
    for key in ("teaching_class_id", "student_id", "college_id"):
        if key in context:
            scope[key] = context[key]
    return scope


def _safe_trace(trace: dict[str, Any]) -> dict[str, Any]:
    allowed = {"route", "failed_stage", "retrieval_used", "retrievers_used", "elapsed_ms"}
    return {key: value for key, value in trace.items() if key in allowed}


def _apply_max_rows(result: dict[str, Any], max_rows: int | None) -> None:
    if max_rows is None or not result.get("data"):
        return
    data = result["data"]
    rows = list(data.get("rows") or [])
    if len(rows) > max_rows:
        data["rows"] = rows[:max_rows]
        data["row_count"] = len(data["rows"])
        data["truncated"] = True
        result.setdefault("warnings", []).append("结果已按本次请求的最大行数收紧。")


def _default_title(question: str) -> str:
    return question if len(question) <= 40 else question[:39] + "…"
