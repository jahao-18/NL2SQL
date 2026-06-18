"""检索层的公共数据结构与检索器接口。

新增检索后端(ES 关键字库 / Milvus 向量库 / 关系图谱库)只需实现 Retriever:
build(atoms) 离线建索引,query(question, top_k) 在线召回 Hit 列表。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SchemaAtom:
    """schema 的最小可检索单元:一列(column 非空)或一张表(column 为空)。"""
    source: str
    table: str
    column: str = ""          # 空字符串表示表级原子
    col_type: str = ""
    natural_name: str = ""    # 自然语言名(如 BIRD 的 column_names)
    description: str = ""     # 业务含义(来自 database_description / 注释 / 词表)
    value_hints: str = ""     # 低基数取值示例
    is_pk: bool = False

    @property
    def id(self) -> str:
        return f"{self.table}.{self.column}" if self.column else self.table

    def index_text(self) -> str:
        """用于关键字/向量索引与 embedding 的文本表示。"""
        parts = [self.table]
        if self.column:
            parts.append(self.column)
        if self.natural_name and self.natural_name.lower() != self.column.lower():
            parts.append(self.natural_name)
        if self.description:
            parts.append(self.description)
        if self.value_hints:
            parts.append(f"取值: {self.value_hints}")
        return " | ".join(p for p in parts if p)


@dataclass
class Hit:
    """一次召回命中:某个原子 + 该检索器给的分数。"""
    atom_id: str
    score: float
    retriever: str


@dataclass
class RetrievedContext:
    """检索最终产物:喂给 LLM 的精简 schema 文本 + 命中的表集合(供日志/调试)。"""
    context_text: str
    tables: list[str] = field(default_factory=list)
    retrievers_used: list[str] = field(default_factory=list)
    fell_back: bool = False   # True 表示退回了整库 DDL


class Retriever(ABC):
    """检索器接口。name 用于日志与融合时标注来源。"""
    name: str = "base"

    @abstractmethod
    def build(self, atoms: list[SchemaAtom]) -> None:
        """用 schema 原子建立(或加载)索引。"""

    @abstractmethod
    def query(self, question: str, top_k: int) -> list[Hit]:
        """召回与问题最相关的若干原子。"""

    def available(self) -> bool:
        """后端是否就绪(如外部服务连不上 / 依赖缺失则返回 False,流水线会跳过它)。"""
        return True
