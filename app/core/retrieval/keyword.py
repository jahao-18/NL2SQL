"""关键字检索器:BM25 词频召回,擅长精确词命中(列名、枚举值如 'paid'、自然名)。

进程内用 rank_bm25 实现 base.Retriever 接口;以后想接真 Elasticsearch,只要再写一个
同接口的类(build 时 bulk 写入索引,query 时发 match 查询),pipeline 不用动。
"""
from __future__ import annotations

import logging
import re

import numpy as np
from rank_bm25 import BM25Okapi

from app.core.retrieval.base import Hit, Retriever, SchemaAtom

logger = logging.getLogger("nl2sql.retrieval.keyword")

# 英文/数字按词切;中文按单字切(让中文问题也有少量重叠信号,语义匹配主要靠向量路)
_TOKEN = re.compile(r"[a-z0-9_]+|[一-鿿]")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class KeywordRetriever(Retriever):
    name = "keyword"

    def __init__(self, source: str) -> None:
        self.source = source
        self.atom_ids: list[str] = []
        self.bm25: BM25Okapi | None = None

    def build(self, atoms: list[SchemaAtom]) -> None:
        self.atom_ids = [a.id for a in atoms]
        corpus = [_tokenize(a.index_text()) for a in atoms]
        if any(corpus):
            self.bm25 = BM25Okapi(corpus)
            logger.info("BM25 索引已建 | source=%s | %d 原子", self.source, len(atoms))

    def available(self) -> bool:
        return self.bm25 is not None

    def query(self, question: str, top_k: int) -> list[Hit]:
        if self.bm25 is None:
            return []
        toks = _tokenize(question)
        if not toks:
            return []
        scores = self.bm25.get_scores(toks)
        k = min(top_k, len(scores))
        top = np.argsort(-scores)[:k]
        return [Hit(self.atom_ids[i], float(scores[i]), self.name)
                for i in top if scores[i] > 0]
