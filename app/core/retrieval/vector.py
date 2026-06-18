"""向量检索器:对 schema 原子做 embedding,按余弦相似召回。

实现的是 base.Retriever 接口——以后换成 Milvus 只要再写一个同接口的类,流水线不用动。
embedding 落盘缓存,按原子文本签名校验;schema 没变就直接加载,不重复调用 API。
"""
from __future__ import annotations

import hashlib
import json
import logging

import numpy as np

from app.core.config import ROOT_DIR
from app.core.retrieval.base import Hit, Retriever, SchemaAtom
from app.core.retrieval.embedding import embed

logger = logging.getLogger("nl2sql.retrieval.vector")

_INDEX_DIR = ROOT_DIR / "data" / "retrieval_index"


class VectorRetriever(Retriever):
    name = "vector"

    def __init__(self, source: str) -> None:
        self.source = source
        self.atom_ids: list[str] = []
        self.matrix: np.ndarray = np.zeros((0, 0), dtype=np.float32)
        self._ok = False

    def _paths(self) -> tuple:
        d = _INDEX_DIR / self.source
        return d, d / "vectors.npy", d / "vector_meta.json"

    @staticmethod
    def _signature(texts: list[str]) -> str:
        h = hashlib.sha256()
        for t in texts:
            h.update(t.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    def build(self, atoms: list[SchemaAtom]) -> None:
        texts = [a.index_text() for a in atoms]
        ids = [a.id for a in atoms]
        sig = self._signature(texts)
        d, vec_path, meta_path = self._paths()

        # 缓存命中:签名一致直接加载
        if vec_path.exists() and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("signature") == sig:
                    self.matrix = np.load(vec_path)
                    self.atom_ids = meta["atom_ids"]
                    self._ok = self.matrix.shape[0] == len(self.atom_ids)
                    if self._ok:
                        logger.info("向量索引命中缓存 | source=%s | %d 原子", self.source, len(ids))
                        return
            except Exception as e:
                logger.warning("向量缓存加载失败,重建 | %s", e)

        # 重建:调用 embedding API 并落盘
        self.matrix = embed(texts)
        self.atom_ids = ids
        self._ok = self.matrix.shape[0] == len(ids) and self.matrix.shape[0] > 0
        if self._ok:
            d.mkdir(parents=True, exist_ok=True)
            np.save(vec_path, self.matrix)
            meta_path.write_text(
                json.dumps({"signature": sig, "atom_ids": ids}, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("向量索引已重建 | source=%s | %d 原子", self.source, len(ids))

    def available(self) -> bool:
        return self._ok

    def query(self, question: str, top_k: int) -> list[Hit]:
        if not self._ok:
            return []
        qvec = embed([question])[0]                 # 已归一化
        scores = self.matrix @ qvec                  # 归一化向量点积 = 余弦
        k = min(top_k, scores.shape[0])
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [Hit(self.atom_ids[i], float(scores[i]), self.name) for i in top]
