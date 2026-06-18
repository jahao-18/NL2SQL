"""知识库检索(schema linking):针对问题多路召回相关表/列/JOIN 路径,拼精简上下文。

对外只暴露 retrieve_context;具体检索器(向量/关键字/图谱)走 base.Retriever 接口,可插拔。
"""
from __future__ import annotations

from app.core.retrieval.base import RetrievedContext
from app.core.retrieval.pipeline import retrieve_context

__all__ = ["retrieve_context", "RetrievedContext"]
