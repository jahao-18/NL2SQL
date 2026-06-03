"""结果格式化:把执行结果 + 元数据组装成 API 返回结构。"""
from __future__ import annotations

from typing import Any


def _source_fields(
    source: str | None, source_label: str | None, auto_routed: bool
) -> dict[str, Any]:
    """本次实际使用的数据源信息,所有响应都带上,供前端透明展示。"""
    return {
        "source": source,
        "source_label": source_label,
        "auto_routed": auto_routed,
    }


def format_success(
    sql: str,
    columns: list[str],
    rows: list[list],
    elapsed_ms: int,
    truncated: bool = False,
    column_sources: list[str] | None = None,
    source: str | None = None,
    source_label: str | None = None,
    auto_routed: bool = False,
    confidence: int | None = None,
    confidence_detail: dict[str, Any] | None = None,
    judge_id: str | None = None,
) -> dict[str, Any]:
    return {
        "sql": sql,
        "columns": columns,
        "column_sources": column_sources or [],
        "rows": rows,
        "row_count": len(rows),
        "elapsed_ms": elapsed_ms,
        "truncated": truncated,
        "error": None,
        "clarify": None,
        "confidence": confidence,
        "confidence_detail": confidence_detail,
        "judge_id": judge_id,
        **_source_fields(source, source_label, auto_routed),
    }


def format_error(
    error: str,
    sql: str | None = None,
    source: str | None = None,
    source_label: str | None = None,
    auto_routed: bool = False,
) -> dict[str, Any]:
    return {
        "sql": sql,
        "columns": [],
        "column_sources": [],
        "rows": [],
        "row_count": 0,
        "elapsed_ms": 0,
        "truncated": False,
        "error": error,
        "clarify": None,
        **_source_fields(source, source_label, auto_routed),
    }


def format_clarify(
    question: str,
    source: str | None = None,
    source_label: str | None = None,
    auto_routed: bool = False,
) -> dict[str, Any]:
    """LLM 需要用户先回答澄清问题再生成 SQL。不走 validator/executor。"""
    return {
        "sql": None,
        "columns": [],
        "column_sources": [],
        "rows": [],
        "row_count": 0,
        "elapsed_ms": 0,
        "truncated": False,
        "error": None,
        "clarify": question,
        **_source_fields(source, source_label, auto_routed),
    }
