"""LangChain 链:Qwen 生成 SQL + 失败回修。

generate_sql 走 ChatPromptTemplate 支持多轮对话;
repair_sql 保留单轮 PromptTemplate,因为回修只需要"上次 SQL + error",不需要历史上下文。
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Literal

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate

from app.core.config import PROMPTS_DIR, settings
from app.models.schemas import Turn

CLARIFY_PREFIX = "CLARIFY:"


def _read(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _llm() -> ChatTongyi:
    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置,请在 .env 中填入")
    return ChatTongyi(
        model=settings.qwen_model,
        dashscope_api_key=settings.dashscope_api_key,
        temperature=0,
    )


def _strip_sql(raw: str) -> str:
    """去掉模型可能加的 markdown 围栏或解释。"""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if "\n" in s:
            first, rest = s.split("\n", 1)
            if first.strip().lower() in {"sql", "sqlite"}:
                s = rest
    return s.strip().rstrip(";").strip()


def _parse_output(raw: str) -> tuple[Literal["sql", "clarify"], str]:
    """识别 LLM 输出是 SQL 还是 CLARIFY 澄清请求。

    CLARIFY 形如 'CLARIFY: <一句话问题>',大小写不敏感,允许半/全角冒号。
    其它一律按 SQL 处理(再走 _strip_sql)。
    """
    s = raw.strip()
    if s.startswith("```"):
        stripped = s.strip("`")
        if "\n" in stripped:
            first, rest = stripped.split("\n", 1)
            s = rest.strip() if first.strip().lower() in {"sql", "sqlite", "text"} else stripped.strip()
        else:
            s = stripped.strip()

    if s[:8].upper().startswith("CLARIFY"):
        rest = s[len("CLARIFY"):].lstrip()
        # 半角 ':' (U+003A) 或全角 '：' (U+FF1A) 都接受
        if rest and rest[0] in {":", "："}:
            question = rest[1:].strip().splitlines()[0].strip() if rest[1:].strip() else ""
            if question:
                return "clarify", question

    return "sql", _strip_sql(raw)


def _history_to_messages(history: list[Turn]) -> list[BaseMessage]:
    """把 Turn 列表展平成 [HumanMessage, AIMessage, HumanMessage, AIMessage, ...]。

    clarify 轮的 AIMessage 内容会带上 'CLARIFY: ' 前缀(若未带),
    以便下一轮 LLM 看到自己之前问过澄清,从而避免重复发问。
    """
    msgs: list[BaseMessage] = []
    for t in history:
        msgs.append(HumanMessage(content=t.question))
        content = t.sql
        if t.kind == "clarify" and not content.upper().startswith("CLARIFY"):
            content = f"{CLARIFY_PREFIX} {content}"
        msgs.append(AIMessage(content=content))
    return msgs


@lru_cache(maxsize=1)
def _chat_prompt() -> ChatPromptTemplate:
    system_text = _read("sql_prompt.txt")
    return ChatPromptTemplate.from_messages(
        [
            ("system", system_text),
            MessagesPlaceholder("history"),
            ("human", "{question}"),
        ]
    )


def generate_sql(
    schema: str, question: str, history: list[Turn] | None = None
) -> tuple[Literal["sql", "clarify"], str]:
    """返回 (kind, content):kind=sql 时 content 是 SQL,kind=clarify 时 content 是要问用户的问题。"""
    chain = _chat_prompt() | _llm() | StrOutputParser()
    raw = chain.invoke(
        {
            "schema": schema,
            "question": question,
            "history": _history_to_messages(history or []),
            "current_date": date.today().isoformat(),
        }
    )
    return _parse_output(raw)


@lru_cache(maxsize=1)
def _repair_prompt() -> PromptTemplate:
    return PromptTemplate.from_template(_read("sql_repair_prompt.txt"))


def repair_sql(schema: str, question: str, previous_sql: str, error: str) -> str:
    chain = _repair_prompt() | _llm() | StrOutputParser()
    raw = chain.invoke(
        {
            "schema": schema,
            "question": question,
            "previous_sql": previous_sql,
            "error": error,
            "current_date": date.today().isoformat(),
        }
    )
    return _strip_sql(raw)
