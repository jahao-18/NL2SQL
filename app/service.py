"""业务编排:schema -> LLM 生成(可带历史) -> 校验 -> 执行 -> (失败回修一轮) -> 格式化。

支持澄清流程:LLM 可输出 CLARIFY 暂停一次,等用户回答后续轮重新生成 SQL。
每个查询最多 1 次 CLARIFY,二次模糊由 prompt 约束 + 后端兜底降级为错误返回。
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.core.chain import generate_sql, repair_sql
from app.core.business_domains import denied_question_hit, filter_schema_info
from app.core.config import settings
from app.core.data_sources import get_source
from app.core.explain import explain_query
from app.core.executor import SQLExecutionError, execute
from app.core.formatter import format_clarify, format_error, format_success
from app.core.judge import stash as stash_judge
from app.core.retrieval import retrieve_context
from app.core.schema import list_table_names, load_schema
from app.core.source_router import route
from app.core.sql_meta import extract_column_sources
from app.core.validator import SQLValidationError, validate_and_fix
from app.models.schemas import FewShotExample, Turn

logger = logging.getLogger("nl2sql")

MAX_REPAIR_ROUNDS = 2
MAX_HISTORY_TURNS = 5  # 后端兜底截断,防止前端发太多


def _retrieval_context_is_authorized(
    context_text: str, retrieved_tables: list[str], schema_info: Any
) -> bool:
    """Prevent the global retrieval index from widening a role-filtered Schema."""
    if not set(retrieved_tables).issubset(set(schema_info.tables)):
        return False
    for full in schema_info.blocked_columns:
        if "." not in full:
            continue
        table, column = full.split(".", 1)
        # Relationship keys may be present for JOIN/WHERE; output validation still blocks them.
        if column == "id" or column.endswith("_id"):
            continue
        if re.search(rf"\b{re.escape(table)}\s*\.\s*{re.escape(column)}\b", context_text, re.IGNORECASE):
            return False
        block = re.search(
            rf"(?ms)^表\s+{re.escape(table)}\s*:\s*(.*?)(?=^表\s+|\Z)",
            context_text,
        )
        if block and re.search(rf"(?m)^\s*-\s*{re.escape(column)}\b", block.group(1), re.IGNORECASE):
            return False
    return True


def _route_reason(question: str, source: str, auto_routed: bool, current_source: str | None) -> str:
    try:
        tables = list_table_names(source)
    except Exception:
        tables = []
    q = question.lower()
    matched = [t for t in tables if t.lower() in q][:5]
    if auto_routed:
        parts = ["自动模式根据当前问题、最近对话和数据源目录选择该库"]
        if current_source == source:
            parts.append("并沿用当前会话数据源")
        if matched:
            parts.append("问题中命中表名: " + ", ".join(matched))
        return "；".join(parts)
    return "用户手动选择并锁定该数据源"


def ask(
    question: str,
    history: list[Turn] | None = None,
    source: str | None = None,
    current_source: str | None = None,
    user_glossary: list[str] | None = None,
    few_shots: list[FewShotExample] | None = None,
    allowed_tables: set[str] | frozenset[str] | None = None,
    denied_columns: set[str] | frozenset[str] | None = None,
    denied_terms: list[str] | tuple[str, ...] | None = None,
    role_label: str | None = None,
    row_scope: dict[str, Any] | None = None,
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
    src_kw = {
        "source": ds.name,
        "source_label": ds.label,
        "auto_routed": auto_routed,
        "route_reason": _route_reason(question, ds.name, auto_routed, current_source),
    }
    enforce_teaching_policy = ds.name == "teaching"

    denied_hit = denied_question_hit(question, denied_terms or []) if enforce_teaching_policy else None
    if denied_hit:
        return format_error(f"当前身份「{role_label or '未登录'}」无权查询“{denied_hit}”相关数据。", **src_kw)

    try:
        schema_info = load_schema(ds.name)
        if enforce_teaching_policy and allowed_tables is not None:
            schema_info = filter_schema_info(schema_info, set(allowed_tables), set(denied_columns or []))
    except (FileNotFoundError, RuntimeError) as e:
        return format_error(str(e), **src_kw)

    if not schema_info.tables:
        return format_error(
            f"当前身份「{role_label or '未登录'}」没有可用于该数据源的业务表权限。",
            **src_kw,
        )

    # 知识库检索:针对问题召回精简 schema 上下文(替代整库 DDL 喂给模型)。
    # 检索 query 以当前问题为主,只带最近 N 条历史提问(让"按城市拆分"这类追问能召回上一轮的表,
    # 同时避免 5 轮老话题稀释当前语义)。失败/库太小返回 None,回退整库 DDL;validator 仍用全量表。
    schema_text = schema_info.ddl_text
    retrieval_used = False
    retrieval_started = time.perf_counter()
    retrieval_trace: dict[str, Any] = {
        "retrieval_used": False,
        "retrieval_status": "not_used",
        "stage_timings": {},
    }
    try:
        n_hist = max(0, settings.retrieval_history_turns)
        recent_q = [t.question for t in trimmed_history][-n_hist:] if n_hist else []
        retrieval_query = " ".join([question] + recent_q)   # 当前问题前置主导
        rc = retrieve_context(retrieval_query, ds.name, schema_info)
        if rc is not None and _retrieval_context_is_authorized(rc.context_text, rc.tables, schema_info):
            schema_text = rc.context_text
            retrieval_used = True
            retrieval_trace = {
                "retrieval_used": True,
                "retrieval_status": "used",
                "tables": rc.tables,
                "retrievers_used": rc.retrievers_used,
                "context_preview": rc.context_text[:1200],
                "stage_timings": {},
            }
        elif rc is not None:
            retrieval_trace.update(
                retrieval_status="authorization_fallback",
                degraded=True,
                degradation_reason="检索候选超出当前授权 Schema，已回退到完整授权结构",
            )
    except Exception:
        logger.exception("schema 检索异常,回退整库 DDL")
        retrieval_trace.update(
            retrieval_status="degraded",
            degraded=True,
            degradation_reason="Schema 检索不可用，已回退到完整授权结构",
        )
    retrieval_trace["stage_timings"]["retrieval_ms"] = max(
        0, round((time.perf_counter() - retrieval_started) * 1000)
    )

    if enforce_teaching_policy and schema_info.blocked_columns:
        schema_text += (
            "\n\n【受限字段规则】以下字段可在授权 Schema 中作为 JOIN/WHERE 或范围校验键出现，"
            "但严禁放入 SELECT 结果；如果用户需要人员名单，应选择当前角色可见的姓名等业务字段：\n- "
            + "\n- ".join(sorted(schema_info.blocked_columns))
        )

    # 用户为该库补充的术语/取值映射:拼在 schema 末尾(放在检索替换之后,保证一定喂到模型)。
    # 专治"加密取值"——如"交易后出账 = frequency 的 POPLATEK PO OBRATU",模型就不用猜了。
    clean_glossary = [g.strip() for g in (user_glossary or []) if g and g.strip()][:50]
    if clean_glossary:
        schema_text += ("\n\n【用户补充术语 / 取值映射(用户提供,写 SQL 时请优先采用)】\n"
                        + "\n".join(f"- {g[:200]}" for g in clean_glossary))

    examples = [
        ex for ex in (few_shots or [])
        if ex.question.strip() and ex.sql.strip() and (not ex.source or ex.source == ds.name)
    ][:8]
    if examples:
        schema_text += "\n\n【用户收藏的参考样例(few-shot,同类问题优先参考写法,不要照抄不相关条件)】\n"
        for i, ex in enumerate(examples, 1):
            schema_text += (
                f"示例 {i} 问题:{ex.question.strip()[:300]}\n"
                f"示例 {i} SQL:{ex.sql.strip()[:1200]}\n"
            )

    last_sql: str | None = None
    last_err: str | None = None
    model_elapsed_ms = 0
    validation_elapsed_ms = 0
    execution_elapsed_ms = 0

    for attempt in range(MAX_REPAIR_ROUNDS + 1):
        retrieval_trace["attempts"] = attempt + 1
        model_started = time.perf_counter()
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
            model_elapsed_ms += max(0, round((time.perf_counter() - model_started) * 1000))
            retrieval_trace["stage_timings"]["model_ms"] = model_elapsed_ms
            retrieval_trace["failed_stage"] = "model"
            logger.exception("LLM 调用失败")
            return format_error(f"LLM 调用失败: {e}", trace=retrieval_trace, **src_kw)
        model_elapsed_ms += max(0, round((time.perf_counter() - model_started) * 1000))
        retrieval_trace["stage_timings"]["model_ms"] = model_elapsed_ms

        if kind == "clarify":
            if last_turn_was_clarify:
                logger.warning("已澄清一次仍触发 CLARIFY,降级为错误 | q=%s | clarify=%s", question, content)
                retrieval_trace["failed_stage"] = "model"
                return format_error(
                    "经过澄清后仍无法生成 SQL,请尝试更具体地描述需求。",
                    trace=retrieval_trace,
                    **src_kw,
                )
            logger.info("ask clarify | source=%s | q=%s | history=%d | clarify=%s",
                        ds.name, question, len(trimmed_history), content)
            return format_clarify(content, trace=retrieval_trace, **src_kw)

        raw_sql = content
        validation_started = time.perf_counter()
        try:
            safe_sql, truncated = validate_and_fix(
                raw_sql, schema_info.tables, schema_info.blocked_columns,
                row_scope=row_scope if enforce_teaching_policy else None,
            )
        except SQLValidationError as e:
            validation_elapsed_ms += max(0, round((time.perf_counter() - validation_started) * 1000))
            retrieval_trace["stage_timings"]["validation_ms"] = validation_elapsed_ms
            last_sql, last_err = raw_sql, str(e)
            logger.warning("SQL 校验失败 attempt=%s err=%s sql=%s", attempt, e, raw_sql)
            continue
        validation_elapsed_ms += max(0, round((time.perf_counter() - validation_started) * 1000))
        retrieval_trace["stage_timings"]["validation_ms"] = validation_elapsed_ms

        execution_started = time.perf_counter()
        try:
            columns, rows, elapsed_ms, capped = execute(safe_sql, source_name=ds.name)
        except SQLExecutionError as e:
            execution_elapsed_ms += max(0, round((time.perf_counter() - execution_started) * 1000))
            retrieval_trace["stage_timings"]["execution_ms"] = execution_elapsed_ms
            last_sql, last_err = safe_sql, str(e)
            logger.warning("SQL 执行失败 attempt=%s err=%s sql=%s", attempt, e, safe_sql)
            continue
        execution_elapsed_ms += max(0, round((time.perf_counter() - execution_started) * 1000))
        retrieval_trace["stage_timings"]["execution_ms"] = execution_elapsed_ms
        # 兜底:实际结果撞到行上限就算截断,不依赖 LLM 是否守规矩(它可能擅自写了 LIMIT MAX_ROWS,
        # 校验器看不出超限 → truncated 漏标。这里以真实行数为准,补上提示)。
        truncated = truncated or capped

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
        explanation = explain_query(
            question, ds.name, ds.label, safe_sql, auto_routed,
            src_kw.get("route_reason"), retrieval_trace,
        )
        return format_success(
            safe_sql, columns, rows, elapsed_ms,
            truncated=truncated, column_sources=column_sources,
            judge_id=judge_id, explanation=explanation, trace=retrieval_trace, **src_kw,
        )

    retrieval_trace["failed_stage"] = "execution" if execution_elapsed_ms else "validation"
    return format_error(
        f"经过 {MAX_REPAIR_ROUNDS + 1} 次尝试仍失败: {last_err}",
        sql=last_sql,
        trace=retrieval_trace,
        **src_kw,
    )
