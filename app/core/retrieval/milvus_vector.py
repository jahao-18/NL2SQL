"""Milvus 向量检索器:与 VectorRetriever 同接口(name='vector'),把"存向量+搜向量"交给 Milvus。

embedding 仍由 DashScope text-embedding-v3 生成(Milvus 不产向量,只存/搜),所以 server
模式同样需要 DASHSCOPE_API_KEY。每源一个 collection(nl2sql_<source>),主键就是 atom.id。
按原子文本签名做缓存:collection 已存在且签名一致就跳过重建,不重复嵌入。
连不上 / 依赖缺失时 available() 返回 False,pipeline 自动跳过 -> 回退整库 DDL。
"""
from __future__ import annotations

import hashlib
import json
import logging

from app.core.config import ROOT_DIR, settings
from app.core.retrieval.base import Hit, Retriever, SchemaAtom
from app.core.retrieval.embedding import embed

logger = logging.getLogger("nl2sql.retrieval.milvus")

_META_DIR = ROOT_DIR / "data" / "retrieval_index"


class MilvusRetriever(Retriever):
    name = "vector"   # 名字与本地向量路一致,日志/RRF 融合无感

    def __init__(self, source: str) -> None:
        self.source = source
        self.collection = f"nl2sql_{source}"
        self._client = None
        self._ok = False

    def _meta_path(self):
        return _META_DIR / self.source / "milvus_meta.json"

    @staticmethod
    def _signature(texts: list[str]) -> str:
        h = hashlib.sha256()
        for t in texts:
            h.update(t.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    def _load_meta_sig(self) -> str | None:
        p = self._meta_path()
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("signature")
        except Exception:
            return None

    def _save_meta_sig(self, sig: str) -> None:
        p = self._meta_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"signature": sig}, ensure_ascii=False), encoding="utf-8")

    def build(self, atoms: list[SchemaAtom]) -> None:
        from pymilvus import MilvusClient

        texts = [a.index_text() for a in atoms]
        if not texts:
            return
        sig = self._signature(texts)

        try:
            self._client = MilvusClient(uri=settings.milvus_uri)

            # 缓存命中:collection 在 + 签名一致 -> 不重嵌入、不重建
            if self._client.has_collection(self.collection) and self._load_meta_sig() == sig:
                self._ok = True
                logger.info("Milvus 索引命中缓存 | source=%s | %d 原子", self.source, len(atoms))
                return

            mat = embed(texts)                       # 调 DashScope,已 L2 归一化
            if mat.shape[0] != len(atoms) or mat.shape[0] == 0:
                return

            if self._client.has_collection(self.collection):
                self._client.drop_collection(self.collection)
            self._client.create_collection(
                collection_name=self.collection,
                dimension=int(mat.shape[1]),
                primary_field_name="atom_id",
                id_type="string",
                max_length=512,
                vector_field_name="vector",
                metric_type="COSINE",      # 向量已归一化,COSINE 直接可用
                auto_id=False,
            )
            self._client.insert(self.collection, [
                {"atom_id": a.id, "vector": mat[i].tolist()}
                for i, a in enumerate(atoms)
            ])
            self._client.flush(self.collection)   # 封盘:数据落 sealed 段,row_count 准确、重启后不依赖 WAL 回放
            self._save_meta_sig(sig)
            self._ok = True
            logger.info("Milvus 索引已重建 | source=%s | %d 原子", self.source, len(atoms))
        except Exception:
            self._ok = False
            logger.exception("Milvus 不可用,跳过向量路 | source=%s", self.source)

    def available(self) -> bool:
        return self._ok

    def query(self, question: str, top_k: int) -> list[Hit]:
        if not self._ok or self._client is None:
            return []
        try:
            qvec = embed([question])[0].tolist()
            res = self._client.search(
                collection_name=self.collection,
                data=[qvec],
                limit=top_k,
                output_fields=["atom_id"],
            )
            out: list[Hit] = []
            for h in res[0]:
                atom_id = h.get("entity", {}).get("atom_id") or h.get("id")
                out.append(Hit(str(atom_id), float(h["distance"]), self.name))
            return out
        except Exception:
            logger.exception("Milvus 查询失败 | source=%s", self.source)
            return []
