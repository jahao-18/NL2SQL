"""数据源路由:根据用户问题自动判断该查哪个数据源。

构建一份各数据源的目录(标识 + 显示名 + 表名),让 Qwen 选最匹配的一个。
**每轮**(非手动锁库时)都调用,且历史感知:把当前会话所在库 + 最近提问一并喂给模型,
让追问("再按城市拆分")留在原库,而换话题的新问题("超级英雄…")能切到对应库。
"""
from __future__ import annotations

import logging
from functools import lru_cache

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from app.core.chain import _router_llm  # 路由专用快模型(temperature=0),与主生成分开
from app.core.config import PROMPTS_DIR
from app.core.data_sources import load_sources
from app.core.schema import list_table_names
from app.models.schemas import Turn

logger = logging.getLogger("nl2sql.router")

_RECENT_Q = 3  # 喂给路由器的最近提问条数


def _conversation_block(history: list[Turn] | None, current_source: str | None) -> str:
    """拼"当前会话上下文"段:当前库 + 最近几条提问。首轮(无当前库)返回空提示。"""
    sources = load_sources()
    if not current_source or current_source not in sources:
        return "(这是会话首轮,暂无当前数据库;仅按问题本身判断。)"
    label = sources[current_source].label
    lines = [f"当前数据库: {current_source}({label})"]
    recent = [t.question for t in (history or [])][-_RECENT_Q:]
    if recent:
        lines.append("最近的提问(从旧到新):")
        lines += [f"  - {q}" for q in recent]
    return "\n".join(lines)


@lru_cache(maxsize=1)
def _build_catalog() -> str:
    """各数据源一行:标识 | 显示名 | 表名清单。结果缓存(数据源变了需 clear_cache)。"""
    lines: list[str] = []
    for name, ds in load_sources().items():
        tables = list_table_names(name)
        table_str = ", ".join(tables) if tables else "(无法读取表)"
        lines.append(f"- {name} | {ds.label} | 表: {table_str}")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def _router_prompt() -> PromptTemplate:
    return PromptTemplate.from_template(
        (PROMPTS_DIR / "router_prompt.txt").read_text(encoding="utf-8")
    )


def route(question: str, history: list[Turn] | None = None,
          current_source: str | None = None) -> str | None:
    """返回最匹配的数据源 name;无法匹配(模型给 NONE 或解析不出)时返回 None,交上层处理。

    单一数据源时直接返回它(无需路由)。history + current_source 提供会话上下文,
    让模型对追问保持原库、对换话题切到新库。
    """
    sources = load_sources()
    names = list(sources.keys())
    if len(names) == 1:
        return names[0]

    chain = _router_prompt() | _router_llm() | StrOutputParser()
    raw = chain.invoke({
        "catalog": _build_catalog(),
        "question": question,
        "conversation": _conversation_block(history, current_source),
    })
    picked = raw.splitlines()[0].strip().strip("`'\" .") if raw.strip() else ""

    # 模型明确表示无匹配
    if picked.upper() == "NONE" or not picked:
        logger.info("路由无匹配 | q=%s | raw=%r", question, raw)
        return None

    if picked in sources:
        logger.info("路由命中 | q=%s -> %s", question, picked)
        return picked

    # 容错:大小写精确 / 包含匹配
    low = picked.lower()
    for n in names:
        if n.lower() == low:
            return n
    for n in names:
        if n.lower() in low or low in n.lower():
            logger.info("路由模糊命中 | q=%s | raw=%r -> %s", question, picked, n)
            return n

    # 解析不出任何已知库 => 当作无匹配,交上层反问
    logger.warning("路由结果无法识别为已知库,按无匹配处理 | q=%s | raw=%r", question, raw)
    return None


def clear_cache() -> None:
    _build_catalog.cache_clear()
