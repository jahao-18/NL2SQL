"""LangChain 链:Qwen 生成 SQL + 失败回修。

generate_sql 走 ChatPromptTemplate 支持多轮对话;
repair_sql 保留单轮 PromptTemplate,因为回修只需要"上次 SQL + error",不需要历史上下文。
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate

from app.core.config import PROMPTS_DIR, settings
from app.models.schemas import Turn


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


def _history_to_messages(history: list[Turn]) -> list[BaseMessage]:
    """把 Turn 列表展平成 [HumanMessage, AIMessage, HumanMessage, AIMessage, ...]。"""
    msgs: list[BaseMessage] = []
    for t in history:
        msgs.append(HumanMessage(content=t.question))
        msgs.append(AIMessage(content=t.sql))
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


def generate_sql(schema: str, question: str, history: list[Turn] | None = None) -> str:
    chain = _chat_prompt() | _llm() | StrOutputParser()
    raw = chain.invoke(
        {
            "schema": schema,
            "question": question,
            "history": _history_to_messages(history or []),
            "current_date": date.today().isoformat(),
        }
    )
    return _strip_sql(raw)


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
