"""查询侧术语扩展:用快模型(router_model)把中文问题的关键实体/属性抽出来,
并补上最可能的英文列名别名,拼回查询文本,缓解"中文问题 vs 英文列名"的跨语言召回短板。

向量路:英文别名让中文问题更易命中英文列名的语义。
关键字路(BM25):中英文 token 本来零重叠,补了英文词后才有精确命中的机会。

best-effort:关闭 / 失败 / 空结果时原样返回问题,不影响检索可用性。
按问题文本 LRU 缓存,重复问题不重复调用模型。
"""
from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import PROMPTS_DIR, settings

logger = logging.getLogger("nl2sql.retrieval.qexpand")

_MAX_EXTRA_CHARS = 300  # 扩展词整体长度上限,防异常长输出污染查询


@lru_cache(maxsize=1)
def _prompt() -> str:
    return (PROMPTS_DIR / "query_expand_prompt.txt").read_text(encoding="utf-8")


@lru_cache(maxsize=512)
def _expand_cached(question: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.core.chain import _router_llm

    resp = _router_llm().invoke(
        [SystemMessage(content=_prompt()), HumanMessage(content=question)]
    )
    text = resp.content if hasattr(resp, "content") else str(resp)
    return (text if isinstance(text, str) else str(text)).strip()


def expand_query(question: str) -> str:
    """返回"原问题 + 扩展关键词"。关闭/失败/空则返回原问题。"""
    if not settings.retrieval_query_expansion:
        return question
    q = question.strip()
    if not q:
        return question
    try:
        extra = _expand_cached(q)
    except Exception:
        logger.exception("查询扩展失败,用原问题")
        return question
    extra = " ".join(extra.replace("\n", " ").split())[:_MAX_EXTRA_CHARS]
    if not extra:
        return question
    logger.info("查询扩展 | q=%s | +%s", q[:60], extra[:120])
    return f"{question} {extra}"
