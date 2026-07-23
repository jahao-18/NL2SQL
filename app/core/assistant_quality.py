"""Privacy-safe aggregate operations metrics for the administrator dashboard."""
from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core import teaching_migrations
from app.core.business_domains import AuthContext
from app.core.feedback import list_feedback
from app.core.governance import list_review_items, load_settings


PAGE_LABELS = {
    "dashboard": "角色首页",
    "assistant": "智能问数",
    "course_space": "课程空间",
    "assignment_workflow": "作业中心",
    "attendance": "课程考勤",
    "course_analytics": "课程分析",
    "support_workbench": "学习支持",
    "teaching_operations": "教学运行",
    "notifications": "通知中心",
    "governance": "质量治理",
    "data_access": "数据接入",
    "profile": "个人中心",
}
ANSWER_LABELS = {
    "metric": "认证指标",
    "business_state": "业务状态",
    "nl2sql": "自然语言问数",
    "navigation": "页面导航",
    "unsupported": "不支持问题",
    "knowledge": "制度知识",
    "hybrid": "混合问答",
}
FAILURE_LABELS = {
    "routing": "路由",
    "retrieval": "检索",
    "model": "模型",
    "validation": "SQL 校验",
    "execution": "执行",
    "other": "其他",
}
SAFE_FEEDBACK_CATEGORIES = {
    "wrong_sql": "SQL 不正确",
    "wrong_scope": "数据范围不正确",
    "missing_filter": "筛选条件缺失",
    "wrong_aggregation": "聚合口径不正确",
    "incomplete_result": "结果不完整",
    "misunderstood_question": "问题理解偏差",
    "low_confidence": "低置信度",
    "confirmed_example": "已确认示例",
}
SAFE_GOVERNANCE_CATEGORIES = {
    "feedback_fix": "反馈修复",
    "low_confidence": "低置信度复核",
    "example_review": "示例审核",
    "metric_review": "指标审核",
    "permission_review": "权限审核",
}


def quality_operations(auth: AuthContext, days: int = 30) -> dict[str, Any]:
    if not auth.is_admin:
        from app.core.authorization import forbidden

        forbidden()
    days = max(1, min(int(days), 90))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT t.status,t.answer_type,t.context_summary,t.error_code,t.created_at,
                   q.route,q.retrieval_status,q.retrieval_backend,q.degraded,
                   q.total_elapsed_ms,q.confidence_score,q.failed_stage
            FROM assistant_turn t
            LEFT JOIN query_execution_trace q ON q.turn_id=t.id
            WHERE datetime(t.created_at) >= datetime(?)
            ORDER BY t.created_at DESC,t.id DESC
            """,
            (cutoff.isoformat(),),
        ).fetchall()

    settings = load_settings()
    confidence_threshold = int(settings.get("low_confidence_threshold") or 70)
    total = len(rows)
    completed = sum(1 for row in rows if row["status"] in {"success", "degraded"})
    elapsed = sorted(
        int(row["total_elapsed_ms"])
        for row in rows
        if row["total_elapsed_ms"] is not None
    )
    failures = Counter()
    retrieval = Counter()
    frequent = Counter()
    low_confidence = Counter()
    daily: dict[str, Counter] = defaultdict(Counter)
    unauthorized = 0
    for row in rows:
        page = _page(row["context_summary"])
        route = str(row["route"] or row["answer_type"] or "unknown")
        answer_type = str(row["answer_type"] or "unsupported")
        category = (page, answer_type, route)
        frequent[category] += 1
        if row["confidence_score"] is not None and float(row["confidence_score"]) < confidence_threshold:
            low_confidence[category] += 1
        if row["status"] == "rejected" or row["error_code"] == "ASSISTANT_QUERY_REJECTED":
            unauthorized += 1
        if row["status"] == "failed":
            failures[_failure_stage(row["failed_stage"])] += 1
        backend = str(row["retrieval_backend"] or "none")
        if backend in {"local", "server"}:
            retrieval[backend] += 1
        if row["retrieval_status"] == "degraded" or bool(row["degraded"]):
            retrieval["degraded"] += 1
        if row["retrieval_status"] == "not_used":
            retrieval["not_used"] += 1
        day = str(row["created_at"] or "")[:10]
        if day:
            daily[day]["total"] += 1
            if row["status"] in {"success", "degraded"}:
                daily[day]["completed"] += 1

    feedback = [item for item in list_feedback(limit=500) if _after(item.get("created_at"), cutoff)]
    negative = [item for item in feedback if item.get("kind") == "incorrect"]
    negative_categories = Counter(_safe_feedback_category(item) for item in negative)
    reviews = [item for item in list_review_items(limit=500) if _after(item.get("created_at"), cutoff)]
    pending = [item for item in reviews if item.get("status") in {"open", "in_progress"}]
    governance_categories = Counter(_safe_governance_category(item) for item in pending)
    traced = sum(1 for row in rows if row["total_elapsed_ms"] is not None)
    retrieval_total = retrieval["local"] + retrieval["server"]
    return {
        "window": {
            "days": days,
            "start": cutoff.isoformat(),
            "end": datetime.now(timezone.utc).isoformat(),
            "confidence_threshold": confidence_threshold,
        },
        "summary": {
            "total_queries": total,
            "success_rate": _pct(completed, total),
            "p50_ms": _percentile(elapsed, 0.50),
            "p95_ms": _percentile(elapsed, 0.95),
            "trace_coverage_rate": _pct(traced, total),
            "unauthorized_rejections": unauthorized,
            "low_confidence_queries": sum(low_confidence.values()),
            "negative_feedback": len(negative),
            "pending_governance": len(pending),
        },
        "failure_distribution": [
            {"stage": key, "label": FAILURE_LABELS[key], "count": failures[key]}
            for key in ("routing", "retrieval", "model", "validation", "execution", "other")
        ],
        "retrieval": {
            "local_count": retrieval["local"],
            "server_count": retrieval["server"],
            "not_used_count": retrieval["not_used"],
            "degraded_count": retrieval["degraded"],
            "local_share": _pct(retrieval["local"], retrieval_total),
            "server_share": _pct(retrieval["server"], retrieval_total),
            "degraded_rate": _pct(retrieval["degraded"], traced),
        },
        "daily": [
            {
                "date": day,
                "total": values["total"],
                "success_rate": _pct(values["completed"], values["total"]),
            }
            for day, values in sorted(daily.items())
        ],
        "frequent_categories": _category_rows(frequent, 10),
        "low_confidence_categories": _category_rows(low_confidence, 10),
        "negative_feedback_categories": [
            {"source": source, "category": category, "count": count}
            for (source, category), count in negative_categories.most_common(10)
        ],
        "governance_categories": [
            {"category": category, "count": count}
            for category, count in governance_categories.most_common(10)
        ],
        "privacy": {
            "raw_question_exposed": False,
            "sql_exposed": False,
            "result_rows_exposed": False,
            "feedback_reason_exposed": False,
            "description": "仅展示页面、问答类型、路由和治理分类聚合，不返回问题正文或私密内容。",
        },
    }


def _page(raw: str | None) -> str:
    try:
        loaded = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return "unknown"
    value = str(loaded.get("page") or "unknown") if isinstance(loaded, dict) else "unknown"
    return value if value in PAGE_LABELS else "unknown"


def _failure_stage(value: str | None) -> str:
    stage = str(value or "other").lower()
    if stage in {"context", "routing", "orchestrator"}:
        return "routing"
    return stage if stage in {"retrieval", "model", "validation", "execution"} else "other"


def _category_rows(counter: Counter, limit: int) -> list[dict[str, Any]]:
    return [
        {
            "page": page,
            "page_label": PAGE_LABELS.get(page, "其他页面"),
            "answer_type": answer_type,
            "answer_label": ANSWER_LABELS.get(answer_type, "其他问答"),
            "route": _safe_route(route),
            "count": count,
        }
        for (page, answer_type, route), count in counter.most_common(limit)
    ]


def _safe_route(value: Any) -> str:
    route = str(value or "unknown")
    allowed = {
        "nl2sql", "metric", "business_state", "navigation", "unsupported",
        "knowledge", "hybrid", "deterministic", "unknown",
    }
    if route in allowed or route.startswith("deterministic_"):
        return route
    return "other"


def _safe_feedback_category(item: dict[str, Any]) -> tuple[str, str]:
    source = str(item.get("source") or "")
    source_label = "教学业务库" if source in {"teaching", "teaching_db"} else "其他数据源"
    category = str(item.get("category") or "")
    return source_label, SAFE_FEEDBACK_CATEGORIES.get(category, "其他反馈")


def _safe_governance_category(item: dict[str, Any]) -> str:
    category = str(item.get("kind") or item.get("type") or "")
    return SAFE_GOVERNANCE_CATEGORIES.get(category, "其他治理事项")


def _after(value: Any, cutoff: datetime) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc) >= cutoff
    except (TypeError, ValueError):
        return False


def _percentile(values: list[int], quantile: float) -> int | None:
    if not values:
        return None
    index = max(0, min(len(values) - 1, math.ceil(len(values) * quantile) - 1))
    return int(values[index])


def _pct(numerator: int, denominator: int) -> float | None:
    return round(numerator * 100 / denominator, 2) if denominator else None
