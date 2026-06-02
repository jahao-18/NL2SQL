"""结果格式化:把执行结果 + 元数据组装成 API 返回结构。"""
from __future__ import annotations

from typing import Any


def format_success(
    sql: str,
    columns: list[str],
    rows: list[list],
    elapsed_ms: int,
    truncated: bool = False,
    column_sources: list[str] | None = None,
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
    }


def format_error(error: str, sql: str | None = None) -> dict[str, Any]:
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
    }


def format_clarify(question: str) -> dict[str, Any]:
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
    }
