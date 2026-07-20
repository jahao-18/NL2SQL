"""Unified V3 assistant routing across deterministic and legacy NL2SQL paths."""
from __future__ import annotations

import logging
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.assistant_context import AssistantPageContext, resolve_assistant_context
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
)
from app.core.business_domains import AuthContext, navigation_for, row_scope_context
from app.core.semantic_metrics import (
    evaluate_semantic_metric,
    match_semantic_metric,
    metric_answer_payload,
)
from app.core.workbench import build_workbench
from app.service import ask as ask_service


logger = logging.getLogger("nl2sql.assistant")

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
    else:
        detail = get_session(auth, request.session_id, turn_page=1, turn_page_size=1)
        if detail["item"]["page"] != resolution.effective_context["page"]:
            from app.core.assistant_sessions import AssistantSessionConflictError

            raise AssistantSessionConflictError("请求页面与会话页面不一致")
        session_id = request.session_id

    started = time.perf_counter()
    try:
        result = _dispatch(auth, request, resolution.effective_context)
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
    return AssistantQueryResponse(session_id=session_id, turn_id=turn["id"], **result)


def _dispatch(
    auth: AuthContext, request: AssistantQueryRequest, context: dict[str, Any]
) -> dict[str, Any]:
    question = request.question
    semantic_metric = match_semantic_metric(auth, question, context)
    if semantic_metric is not None:
        return metric_answer_payload(
            evaluate_semantic_metric(auth, semantic_metric, context)
        )
    route = _classify(question, request.options.preferred_answer_type, context)
    if route == "navigation":
        return _navigation(auth, question)
    if route in {"metric", "business_state"}:
        return _workbench_answer(auth, question, route)
    if route == "unsupported":
        return _unsupported()
    return _nl2sql(auth, question, context)


def _classify(
    question: str,
    preferred: PreferredAnswerType | None,
    context: dict[str, Any],
) -> PreferredAnswerType:
    text = question.lower()
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
    if not has_object_scope and any(
        word in text for word in ("多少", "几个", "数量", "总数", "未读", "待批阅")
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
        "选课",
        "评教",
        "异常",
        "支持",
        "数据",
        "统计",
    )
    if any(term in question for term in data_terms):
        return "nl2sql"
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
    auth: AuthContext, question: str, context: dict[str, Any]
) -> dict[str, Any]:
    glossary: list[str] = []
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
    legacy = ask_service(
        question,
        source="teaching",
        current_source="teaching",
        user_glossary=glossary,
        allowed_tables=auth.allowed_tables,
        denied_columns=auth.denied_columns,
        denied_terms=auth.denied_terms,
        role_label=auth.role_label,
        row_scope=row_scope,
    )
    if legacy.get("clarify"):
        return {
            **_base("clarify", "unsupported"),
            "clarify": legacy["clarify"],
            "trace_summary": {"route": "nl2sql", **(legacy.get("trace") or {})},
        }
    if legacy.get("error"):
        rejected = any(
            marker in str(legacy["error"])
            for marker in ("无权", "未授权", "不可用于问数", "没有可用于")
        )
        status = "rejected" if rejected else "failed"
        code = "ASSISTANT_QUERY_REJECTED" if rejected else "ASSISTANT_NL2SQL_FAILED"
        result = _failure(code, str(legacy["error"]), status=status)
        result["answer_type"] = "nl2sql"
        result["sql"] = legacy.get("sql")
        trace = {"route": "nl2sql", **(legacy.get("trace") or {})}
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
