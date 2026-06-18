"""关系图谱:把外键建成表关系图,既做"图结构检索"又做"JOIN 路径渲染"。

两个职能:
1. 检索(rank):以前几路融合出的 top 表为**种子**,跑 Personalized PageRank 沿 FK 边扩散,
   把结构上靠近种子的表(桥接表 / 中心表)打分产出,作为第 4 路并入 RRF 再融合。
   ——这是内容路(向量/关键字/术语)给不出的**结构信号**:某张表本身没被问题提到、
   描述也不匹配,但它是连接多张相关表的枢纽,PPR 能把它捞上来。
   需要种子,所以是二阶段(跑在前三路并行召回 + 首次融合之后),不与前三路并行。
2. 渲染(connect):选表定下后,用 FK 最短路径补桥接表 + 输出 JOIN 条件行喂给 LLM。

边来自 SQLAlchemy inspect.get_foreign_keys(BIRD sqlite 已声明外键),跨方言通用。
"""
from __future__ import annotations

import logging

import networkx as nx
import numpy as np
from sqlalchemy import inspect

from app.core.data_sources import get_engine, get_source
from app.core.schema_profile import manual_relations

logger = logging.getLogger("nl2sql.retrieval.graph")


class RelationGraph:
    def __init__(self, source: str) -> None:
        self.source = source
        self.g = nx.Graph()
        # 每条外键: (table1, col1, table2, col2),用于渲染 JOIN 条件
        self.fks: list[tuple[str, str, str, str]] = []

    def build(self) -> None:
        insp = inspect(get_engine(get_source(self.source)))
        for table in insp.get_table_names():
            self.g.add_node(table)
            try:
                fks = insp.get_foreign_keys(table)
            except Exception:
                continue
            for fk in fks:
                rt = fk.get("referred_table")
                cc = fk.get("constrained_columns") or []
                rc = fk.get("referred_columns") or []
                if not rt:
                    continue
                for c1, c2 in zip(cc, rc):
                    self.fks.append((table, c1, rt, c2))
                    self.g.add_edge(table, rt)
        for table, column, ref_table, ref_column in manual_relations(self.source):
            self.g.add_node(table)
            self.g.add_node(ref_table)
            edge = (table, column, ref_table, ref_column)
            reverse_edge = (ref_table, ref_column, table, column)
            if edge not in self.fks and reverse_edge not in self.fks:
                self.fks.append(edge)
            self.g.add_edge(table, ref_table)
        logger.info("关系图已建 | source=%s | %d 表 %d 外键边",
                    self.source, self.g.number_of_nodes(), len(self.fks))

    def available(self) -> bool:
        return len(self.fks) > 0

    def rank(self, seeds: dict[str, float], top_k: int) -> list[tuple[str, float]]:
        """图结构检索:以 seeds(表 -> 权重)为重启分布跑 Personalized PageRank,沿 FK 边扩散,
        返回按 PPR 分降序的 (表, 分数) 列表(最多 top_k)。

        PPR 把种子的"相关度质量"沿外键传播:种子自身分高,与种子 FK 相连的桥接/中心表也获得
        可观分数。这样结构上关键、但内容路没捞到的表能进入候选。无边/无有效种子时返回空。
        """
        if self.g.number_of_edges() == 0:
            return []
        pers = {t: w for t, w in seeds.items() if t in self.g and w > 0}
        if not pers:
            return []
        try:
            pr = self._ppr(pers)
        except Exception:
            logger.exception("PageRank 失败 | source=%s", self.source)
            return []
        ranked = sorted(pr.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:top_k]

    def _ppr(self, pers: dict[str, float], alpha: float = 0.85,
             max_iter: int = 100, tol: float = 1e-9) -> dict[str, float]:
        """Personalized PageRank 的 numpy 幂迭代(图小,避免引入 scipy)。
        无向 FK 图 -> 对称邻接;列归一化得转移矩阵;无外键的孤立表是 dangling,质量回灌 personalization。"""
        nodes = list(self.g.nodes())
        idx = {n: i for i, n in enumerate(nodes)}
        n = len(nodes)
        adj = np.zeros((n, n), dtype=float)
        for u, v in self.g.edges():
            adj[idx[u], idx[v]] = 1.0
            adj[idx[v], idx[u]] = 1.0
        colsum = adj.sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            trans = np.where(colsum > 0, adj / colsum, 0.0)   # 转移矩阵 M[:,j]=A[:,j]/deg(j)
        dangling_mask = colsum == 0

        p = np.zeros(n)
        total = sum(pers.values())
        for t, w in pers.items():
            p[idx[t]] = w / total
        r = p.copy()
        for _ in range(max_iter):
            dangling = r[dangling_mask].sum()                 # 孤立节点质量按 personalization 重分布
            r_new = alpha * (trans @ r + dangling * p) + (1 - alpha) * p
            if np.abs(r_new - r).sum() < tol:
                r = r_new
                break
            r = r_new
        return {nodes[i]: float(r[i]) for i in range(n)}

    def connect(self, selected: list[str], max_extra: int = 3) -> tuple[list[str], list[str]]:
        """把召回到的表用最短外键路径连通,补少量桥接表;返回(最终表序, JOIN 条件行)。

        近似 Steiner 树:对每对选中表取最短路径,把路径上的中间表并进来(总量受 max_extra 限制),
        这样模型能拿到完成多表 JOIN 所需的中间表。
        """
        final = list(dict.fromkeys(selected))  # 保序去重
        present = [t for t in final if t in self.g]
        extra: list[str] = []

        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                try:
                    path = nx.shortest_path(self.g, present[i], present[j])
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue
                for node in path:
                    if node not in final and node not in extra:
                        extra.append(node)
                        if len(extra) >= max_extra:
                            break
                if len(extra) >= max_extra:
                    break
            if len(extra) >= max_extra:
                break

        final += extra
        final_set = set(final)
        join_lines = [
            f"{t1}.{c1} = {t2}.{c2}"
            for (t1, c1, t2, c2) in self.fks
            if t1 in final_set and t2 in final_set
        ]
        # 去重保序
        join_lines = list(dict.fromkeys(join_lines))
        return final, join_lines
