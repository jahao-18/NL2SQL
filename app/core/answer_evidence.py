"""Safe evidence, quality flags, trace summaries, and trace persistence."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.core import teaching_migrations
from app.core.business_domains import AuthContext
from app.core.config import settings
from app.core.governance import load_settings


def enrich_answer(
    auth: AuthContext,
    effective_context: dict[str, Any],
    result: dict[str, Any],
    *,
    context_elapsed_ms: int,
    orchestration_elapsed_ms: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Add user-facing provenance and return a separate persistence-safe trace."""
    result["scope"] = scope_summary(auth, effective_context)
    result["time_range"] = time_range_summary(effective_context.get("time_range"))
    _complete_evidence(result)

    raw_trace = dict(result.get("trace_summary") or {})
    internal_trace = _internal_trace(
        result,
        raw_trace,
        context_elapsed_ms=context_elapsed_ms,
        orchestration_elapsed_ms=orchestration_elapsed_ms,
    )
    flags = _quality_flags(result, internal_trace)
    result["warnings"] = flags
    if internal_trace["degraded"] and result.get("status") == "success":
        result["status"] = "degraded"
    return result, internal_trace


def scope_summary(auth: AuthContext, context: dict[str, Any]) -> dict[str, Any]:
    labels = {
        "student": "仅本人数据",
        "teacher": "仅本人授课范围",
        "counselor": "仅本人负责行政班与个案范围",
        "college_manager": "仅当前负责学院范围",
        "academic_office": "当前教务工作身份授权范围",
        "admin": "平台管理范围",
    }
    scope: dict[str, Any] = {
        "role": auth.role,
        "role_label": auth.role_label,
        "page": context["page"],
        "description": labels.get(auth.role, auth.role_label),
    }
    for key in ("teaching_class_id", "student_id", "college_id", "academic_year", "semester"):
        if key in context:
            scope[key] = context[key]
    if context.get("filters"):
        scope["filter_keys"] = sorted(context["filters"])
    return scope


def time_range_summary(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    return {
        "start": value.get("start"),
        "end": value.get("end"),
        "description": "按当前页面指定时间范围统计",
    }


def public_trace(
    internal_trace: dict[str, Any], *, is_admin: bool, include_trace: bool
) -> dict[str, Any]:
    public = {
        "route": internal_trace["route"],
        "stages": {
            name: {"status": item["status"]}
            for name, item in internal_trace["stages"].items()
        },
        "degraded": internal_trace["degraded"],
        "failed_stage": internal_trace.get("failed_stage"),
        "elapsed_ms": internal_trace["total_elapsed_ms"],
    }
    if internal_trace.get("metric_code"):
        public["metric_code"] = internal_trace["metric_code"]
    if is_admin and include_trace:
        public.update(
            retrieval_status=internal_trace["retrieval_status"],
            retrievers_used=internal_trace["retrievers_used"],
            stages=internal_trace["stages"],
            degradation_reason=internal_trace.get("degradation_reason"),
            attempts=internal_trace.get("attempts", 1),
        )
    return public


def persist_execution_trace(turn_id: int, result: dict[str, Any], trace: dict[str, Any]) -> None:
    """Persist only aggregate execution metadata; never persist question, SQL, or rows."""
    confidence = result.get("confidence") or {}
    score = confidence.get("score")
    if not isinstance(score, (int, float)):
        score = None
    data = result.get("data") or {}
    row_count = data.get("row_count")
    if not isinstance(row_count, int):
        row_count = 1 if data.get("metric") is not None else 0
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO query_execution_trace(
                turn_id,route,retrieval_status,retrievers_json,stages_json,degraded,
                degradation_reason,total_elapsed_ms,confidence_score,confidence_status,
                result_row_count,truncated,failed_stage,retrieval_backend,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(turn_id) DO UPDATE SET
                route=excluded.route,retrieval_status=excluded.retrieval_status,
                retrievers_json=excluded.retrievers_json,stages_json=excluded.stages_json,
                degraded=excluded.degraded,degradation_reason=excluded.degradation_reason,
                total_elapsed_ms=excluded.total_elapsed_ms,confidence_score=excluded.confidence_score,
                confidence_status=excluded.confidence_status,result_row_count=excluded.result_row_count,
                truncated=excluded.truncated,failed_stage=excluded.failed_stage,
                retrieval_backend=excluded.retrieval_backend
            """,
            (
                turn_id,
                trace["route"],
                trace["retrieval_status"],
                json.dumps(trace["retrievers_used"], ensure_ascii=False, separators=(",", ":")),
                json.dumps(trace["stages"], ensure_ascii=False, separators=(",", ":")),
                1 if trace["degraded"] else 0,
                trace.get("degradation_reason"),
                trace["total_elapsed_ms"],
                score,
                confidence.get("status") or confidence.get("level"),
                max(0, row_count),
                1 if data.get("truncated") else 0,
                trace.get("failed_stage"),
                settings.retrieval_backend if trace["retrieval_status"] in {"used", "degraded"} else "none",
            ),
        )
        conn.commit()


def _complete_evidence(result: dict[str, Any]) -> None:
    evidence = [dict(item) for item in result.get("evidence") or []]
    metric = (result.get("data") or {}).get("metric")
    if metric:
        definition = metric.get("definition") or {}
        if evidence:
            evidence[0].update(
                updated_at=metric.get("data_updated_at"),
                metric_code=definition.get("code"),
                time_semantics=definition.get("time_semantics"),
            )
    elif evidence:
        for item in evidence:
            item.setdefault("queried_at", datetime.now(timezone.utc).isoformat())
    result["evidence"] = evidence


def _internal_trace(
    result: dict[str, Any],
    raw: dict[str, Any],
    *,
    context_elapsed_ms: int,
    orchestration_elapsed_ms: int,
) -> dict[str, Any]:
    route = str(raw.get("route") or result.get("answer_type") or "unsupported")
    raw_stages = raw.get("stage_timings") or {}
    retrieval_status = str(raw.get("retrieval_status") or "not_applicable")
    if route == "nl2sql" and retrieval_status == "not_applicable":
        retrieval_status = "used" if raw.get("retrieval_used") else "not_used"
    failed_stage = raw.get("failed_stage")
    stages: dict[str, dict[str, Any]] = {
        "context": {"status": "success", "elapsed_ms": max(0, context_elapsed_ms)},
        "routing": {"status": "success", "elapsed_ms": max(0, orchestration_elapsed_ms)},
    }
    if route == "nl2sql":
        for name in ("retrieval", "model", "validation", "execution"):
            elapsed = raw_stages.get(f"{name}_ms")
            status = "failed" if failed_stage == name else "skipped"
            if elapsed is not None or (name == "retrieval" and retrieval_status in {"used", "degraded"}):
                status = "degraded" if name == "retrieval" and retrieval_status == "degraded" else "success"
            stages[name] = {"status": status}
            if isinstance(elapsed, (int, float)):
                stages[name]["elapsed_ms"] = max(0, round(elapsed))
    elif route == "semantic_metric":
        stages["metric"] = {
            "status": "failed" if result.get("status") == "failed" else "success",
            "elapsed_ms": max(0, orchestration_elapsed_ms),
        }
    else:
        stages["deterministic"] = {
            "status": "failed" if result.get("status") == "failed" else "success",
            "elapsed_ms": max(0, orchestration_elapsed_ms),
        }
    degraded = bool(raw.get("degraded")) or retrieval_status == "degraded"
    return {
        "route": route,
        "retrieval_status": retrieval_status,
        "retrievers_used": [str(item) for item in raw.get("retrievers_used") or []],
        "stages": stages,
        "degraded": degraded,
        "degradation_reason": raw.get("degradation_reason") or ("Schema 检索不可用，已使用安全回退路径" if degraded else None),
        "failed_stage": failed_stage,
        "total_elapsed_ms": max(0, context_elapsed_ms + orchestration_elapsed_ms),
        "attempts": int(raw.get("attempts") or 1),
        "metric_code": raw.get("metric_code"),
    }


def _quality_flags(result: dict[str, Any], trace: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for warning in result.get("warnings") or []:
        if isinstance(warning, dict):
            flags.append(warning)
            continue
        message = str(warning)
        code = "SMALL_SAMPLE" if "样本量" in message else "TRUNCATED" if "上限" in message or "最大行数" in message else "CONTEXT_IGNORED" if "上下文" in message else "NOTICE"
        flags.append({"code": code, "severity": "warning", "message": message})
    data = result.get("data") or {}
    metric = data.get("metric")
    is_empty = data.get("row_count") == 0 or (metric and metric.get("status") == "available" and metric.get("value") is None)
    if result.get("status") in {"success", "degraded"} and is_empty:
        _append_flag(flags, "EMPTY_RESULT", "info", "当前范围内没有可返回的数据。")
    if data.get("truncated"):
        _append_flag(flags, "TRUNCATED", "warning", "结果已截断，仅展示允许范围内的部分记录。")
    confidence = result.get("confidence") or {}
    score = confidence.get("score")
    threshold = int(load_settings().get("low_confidence_threshold") or 70)
    if isinstance(score, (int, float)) and score < threshold:
        _append_flag(flags, "LOW_CONFIDENCE", "warning", f"当前可信度 {score} 低于治理阈值 {threshold}，建议复核口径和结果。")
    if trace["degraded"]:
        _append_flag(flags, "RETRIEVAL_DEGRADED", "warning", trace["degradation_reason"] or "检索已降级。")
    return flags


def _append_flag(flags: list[dict[str, Any]], code: str, severity: str, message: str) -> None:
    if not any(item.get("code") == code for item in flags):
        flags.append({"code": code, "severity": severity, "message": message})
