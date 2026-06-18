"""DashScope text-embedding-v3 封装。批量编码文本,返回 numpy 矩阵(已 L2 归一化)。

归一化后,向量检索的余弦相似度退化成点积,查询更快。
"""
from __future__ import annotations

import logging
import time

import numpy as np

from app.core.config import settings

logger = logging.getLogger("nl2sql.retrieval.embedding")

_BATCH = 10  # text-embedding-v3 单次最多 10 条


def _call(texts: list[str]) -> list[list[float]]:
    import dashscope

    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置,无法做向量检索")
    resp = None
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = dashscope.TextEmbedding.call(
                model=settings.embedding_model,
                input=texts,
                api_key=settings.dashscope_api_key,
            )
            if resp.status_code == 200:
                break
            last_error = RuntimeError(f"{resp.code} {resp.message}")
        except Exception as e:
            last_error = e
        if attempt < 2:
            time.sleep(0.4 * (2 ** attempt))
    if resp is None:
        raise RuntimeError(f"embedding call failed: {last_error}")
    if resp.status_code != 200:
        raise RuntimeError(f"embedding 调用失败: {resp.code} {resp.message}")
    embs = sorted(resp.output["embeddings"], key=lambda e: e["text_index"])
    return [e["embedding"] for e in embs]


def embed(texts: list[str]) -> np.ndarray:
    """编码并 L2 归一化,返回 shape=(len(texts), dim) 的 float32 矩阵。"""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    vectors: list[list[float]] = []
    for i in range(0, len(texts), _BATCH):
        vectors.extend(_call(texts[i:i + _BATCH]))
    mat = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms
