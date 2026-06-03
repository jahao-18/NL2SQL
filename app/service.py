"""业务编排:schema -> LLM 生成(可带历史) -> 校验 -> 执行 -> (失败回修一轮) -> 格式化。

支持澄清流程:LLM 可输出 CLARIFY 暂停一次,等用户回答后续轮重新生成 SQL。
每个查询最多 1 次 CLARIFY,二次模糊由 prompt 约束 + 后端兜底降级为错误返回。
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.chain import generate_sql, repair_sql
from app.core.data_sources import get_source
from app.core.executor import SQLExecutionError, execute
from app.core.formatter import format_clarify, format_error, format_success
from app.core.judge import stash as stash_judge
from app.core.retrieval import retrieve_context
from app.core.schema import load_schema
from app.core.source_router import route
from app.core.sql_meta import extract_column_sources
from app.core.validator import SQLValidationError, validate_and_fix
from app.models.schemas import Turn

logger = logging.getLogger("nl2sql")

MAX_REPAIR_ROUNDS = 2
MAX_HISTORY_TURNS = 5  # 后端兜底截断,防止前端发太多


def ask(
    question: str,
    history: list[Turn] | None = None,
    source: str | None = None,
    current_source: str | None = None,
    user_glossary: list[str] | None = None,
) -> dict[str, Any]:
    trimmed_history = (history or [])[-MAX_HISTORY_TURNS:]
    # 上一轮就是 clarify => 本轮是用户的回答,禁止再次 clarify(兼顾路由反问与生成澄清)
    last_turn_was_clarify = bool(trimmed_history) and trimmed_history[-1].kind == "clarify"

    # source 给了 => 用户手动锁库,跳过路由。
    # source 为空 => 自动模式:**每轮**都按"问题 + 历史 + 当前库"重新路由,
    #   让追问留在原库、换话题切到新库(修复了过去"首轮路由后整会话粘死一个库"的问题)。
    auto_routed = False
    if not source:
        try:
            routed = route(question, trimmed_history, current_source)
        except Exception as e:
            logger.exception("数据源路由失败")
            return format_error(f"数据源路由失败: {e}")

        if routed is None:
            # 路由拿不准:若会话已在某个库里,保持不动(别把追问踢飞);否则反问/引导手动选库。
            if current_source:
                logger.info("路由无匹配,保持当前会话库 | q=%s | current=%s", question, current_source)
                source = current_source
                auto_routed = True
            elif last_turn_was_clarify:
                logger.warning("路由反问后仍无法判断数据源 | q=%s", question)
                return format_error(
                    "仍无法确定要查询哪个数据库,请在上方「数据源」下拉中手动选择后再试。"
                )
            else:
                logger.info("路由无匹配,反问用户 | q=%s", question)
                return format_clarify(
                    "没能判断这个问题该查哪个数据库。请补充说明你要查的数据涉及哪类业务或实体,"
                    "或在上方「数据源」下拉中手动选择数据源。"
                )
        else:
            source = routed
            auto_routed = True

    try:
        ds = get_source(source)
    except KeyError as e:
        return format_error(str(e))

    # 之后所有响应都带上实际使用的数据源信息(透明展示给用户)
    src_kw = {"source": ds.name, "source_label": ds.label, "auto_routed": auto_routed}

    try:
        schema_info = load_schema(ds.name)
    except (FileNotFoundError, RuntimeError) as e:
        return format_error(str(e), **src_kw)

    # 知识库检索:针对问题召回精简 schema 上下文(替代整库 DDL 喂给模型)。
    # 检索 query 带上历史问题,让"按城市拆分"这类追问也能召回上一轮涉及的表。
    # 失败/库太小返回 None,此处回退整库 DDL;validator 仍用全量 schema_info.tables。
    schema_text = schema_info.ddl_text
    retrieval_used = False
    try:
        retrieval_query = " ".join([t.question for t in trimmed_history] + [question])
        rc = retrieve_context(retrieval_query, ds.name, schema_info.ddl_text)
        if rc is not None:
            schema_text = rc.context_text
            retrieval_used = True
    except Exception:
        logger.exception("schema 检索异常,回退整库 DDL")

    # 用户为该库补充的术语/取值映射:拼在 schema 末尾(放在检索替换之后,保证一定喂到模型)。
    # 专治"加密取值"——如"交易后出账 = frequency 的 POPLATEK PO OBRATU",模型就不用猜了。
    clean_glossary = [g.strip() for g in (user_glossary or []) if g and g.strip()][:50]
    if clean_glossary:
        schema_text += ("\n\n【用户补充术语 / 取值映射(用户提供,写 SQL 时请优先采用)】\n"
                        + "\n".join(f"- {g[:200]}" for g in clean_glossary))

    last_sql: str | None = None
    last_err: str | None = None

    for attempt in range(MAX_REPAIR_ROUNDS + 1):
        try:
            if attempt == 0:
                kind, content = generate_sql(
                    schema_text, question, trimmed_history, dialect=ds.dialect,
                )
            else:
                # 失败回修走单轮 prompt,不带历史,只允许返回 SQL
                kind, content = "sql", repair_sql(
                    schema_text, question, last_sql or "", last_err or "",
                    dialect=ds.dialect,
                )
        except Exception as e:
            logger.exception("LLM 调用失败")
            return format_error(f"LLM 调用失败: {e}", **src_kw)

        if kind == "clarify":
            if last_turn_was_clarify:
                logger.warning("已澄清一次仍触发 CLARIFY,降级为错误 | q=%s | clarify=%s", question, content)
                return format_error(
                    "经过澄清后仍无法生成 SQL,请尝试更具体地描述需求。", **src_kw
                )
            logger.info("ask clarify | source=%s | q=%s | history=%d | clarify=%s",
                        ds.name, question, len(trimmed_history), content)
            return format_clarify(content, **src_kw)

        raw_sql = content
        try:
            safe_sql, truncated = validate_and_fix(raw_sql, schema_info.tables)
        except SQLValidationError as e:
            last_sql, last_err = raw_sql, str(e)
            logger.warning("SQL 校验失败 attempt=%s err=%s sql=%s", attempt, e, raw_sql)
            continue

        try:
            columns, rows, elapsed_ms = execute(safe_sql, source_name=ds.name)
        except SQLExecutionError as e:
            last_sql, last_err = safe_sql, str(e)
            logger.warning("SQL 执行失败 attempt=%s err=%s sql=%s", attempt, e, safe_sql)
            continue

        column_sources = extract_column_sources(safe_sql)
        if len(column_sources) != len(columns):
            column_sources = []

        logger.info(
            "ask ok | source=%s | q=%s | history=%d | sql=%s | rows=%d | %dms | truncated=%s",
            ds.name, question, len(trimmed_history), safe_sql, len(rows), elapsed_ms, truncated,
        )

        # 答案准确率评估(另一个 LLM 当裁判)异步化:此处只把输入暂存,返回 judge_id,
        # 让结果先返回;前端拿到结果后再用 judge_id 请求 /api/judge 补上勋章(省一次往返的等待)。
        # 「无法回答」占位结果(单列名为 error)是模型主动声明答不了,不评分。
        is_placeholder = columns == ["error"]
        judge_id = None if is_placeholder else stash_judge(
            question, schema_text, safe_sql, columns, rows, len(rows), ds.dialect, retrieval_used)
        return format_success(
            safe_sql, columns, rows, elapsed_ms,
            truncated=truncated, column_sources=column_sources,
            judge_id=judge_id, **src_kw,
        )

    return format_error(f"经过 {MAX_REPAIR_ROUNDS + 1} 次尝试仍失败: {last_err}", sql=last_sql, **src_kw)
