"""业务编排:schema -> LLM 生成(可带历史) -> 校验 -> 执行 -> (失败回修一轮) -> 格式化。

支持澄清流程:LLM 可输出 CLARIFY 暂停一次,等用户回答后续轮重新生成 SQL。
每个查询最多 1 次 CLARIFY,二次模糊由 prompt 约束 + 后端兜底降级为错误返回。
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.chain import generate_sql, repair_sql
from app.core.executor import SQLExecutionError, execute
from app.core.formatter import format_clarify, format_error, format_success
from app.core.schema import load_schema
from app.core.sql_meta import extract_column_sources
from app.core.validator import SQLValidationError, validate_and_fix
from app.models.schemas import Turn

logger = logging.getLogger("nl2sql")

MAX_REPAIR_ROUNDS = 2
MAX_HISTORY_TURNS = 5  # 后端兜底截断,防止前端发太多


def ask(question: str, history: list[Turn] | None = None) -> dict[str, Any]:
    try:
        schema_info = load_schema()
    except FileNotFoundError as e:
        return format_error(str(e))

    trimmed_history = (history or [])[-MAX_HISTORY_TURNS:]
    # 上一轮就是 clarify => 本轮是用户的回答,禁止再次 clarify
    last_turn_was_clarify = bool(trimmed_history) and trimmed_history[-1].kind == "clarify"

    last_sql: str | None = None
    last_err: str | None = None

    for attempt in range(MAX_REPAIR_ROUNDS + 1):
        try:
            if attempt == 0:
                kind, content = generate_sql(schema_info.ddl_text, question, trimmed_history)
            else:
                # 失败回修走单轮 prompt,不带历史,只允许返回 SQL
                kind, content = "sql", repair_sql(
                    schema_info.ddl_text, question, last_sql or "", last_err or ""
                )
        except Exception as e:
            logger.exception("LLM 调用失败")
            return format_error(f"LLM 调用失败: {e}")

        if kind == "clarify":
            if last_turn_was_clarify:
                # 用户已回答过一次澄清,模型仍然请求澄清 => prompt 没生效,降级为错误返回
                logger.warning("已澄清一次仍触发 CLARIFY,降级为错误 | q=%s | clarify=%s", question, content)
                return format_error(
                    "经过澄清后仍无法生成 SQL,请尝试更具体地描述需求。"
                )
            logger.info("ask clarify | q=%s | history=%d | clarify=%s",
                        question, len(trimmed_history), content)
            return format_clarify(content)

        raw_sql = content
        try:
            safe_sql, truncated = validate_and_fix(raw_sql, schema_info.tables)
        except SQLValidationError as e:
            last_sql, last_err = raw_sql, str(e)
            logger.warning("SQL 校验失败 attempt=%s err=%s sql=%s", attempt, e, raw_sql)
            continue

        try:
            columns, rows, elapsed_ms = execute(safe_sql)
        except SQLExecutionError as e:
            last_sql, last_err = safe_sql, str(e)
            logger.warning("SQL 执行失败 attempt=%s err=%s sql=%s", attempt, e, safe_sql)
            continue

        column_sources = extract_column_sources(safe_sql)
        # 长度对齐兜底:解析结果数量与实际列对不上时,丢弃源信息,避免前端错位
        if len(column_sources) != len(columns):
            column_sources = []

        logger.info(
            "ask ok | q=%s | history=%d | sql=%s | rows=%d | %dms | truncated=%s",
            question, len(trimmed_history), safe_sql, len(rows), elapsed_ms, truncated,
        )
        return format_success(
            safe_sql, columns, rows, elapsed_ms,
            truncated=truncated, column_sources=column_sources,
        )

    return format_error(f"经过 {MAX_REPAIR_ROUNDS + 1} 次尝试仍失败: {last_err}", sql=last_sql)
