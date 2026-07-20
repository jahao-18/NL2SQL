"""Elasticsearch 关键字检索器:与 KeywordRetriever 同接口(name='keyword'),用 ES 的 BM25。

每源一个索引(nl2sql_<source>),文档 _id 就是 atom.id,正文是 atom.index_text()。
按原子文本签名缓存:索引已存在且签名一致就跳过 bulk(签名含 analyzer,换分词器会强制重建)。
中文分词用 IK(docker/es/Dockerfile 烤入 analysis-ik 插件):索引 ik_max_word、搜索 ik_smart,
比 standard 逐字切精度高(把"出版商"当整词,不会被"商品库存"的单字"商"误召回)。analyzer 由
config.es_analyzer 配置;IK 插件没装时 _create_index 自动回退 standard,不影响可用。
连不上 / 依赖缺失时 available() 返回 False,pipeline 自动跳过 -> 回退整库 DDL。
当 schema 描述和问题使用不同语言时，BM25 命中率会下降，语义由向量检索补充。
"""
from __future__ import annotations

import hashlib
import json
import logging

from app.core.config import ROOT_DIR, settings
from app.core.retrieval.base import Hit, Retriever, SchemaAtom

logger = logging.getLogger("nl2sql.retrieval.es")

_META_DIR = ROOT_DIR / "data" / "retrieval_index"


class ESRetriever(Retriever):
    name = "keyword"   # 名字与本地关键字路一致,日志/RRF 融合无感

    def __init__(self, source: str) -> None:
        self.source = source
        self.index = f"nl2sql_{source.lower()}"   # ES 索引名必须小写
        self._es = None
        self._ok = False

    def _meta_path(self):
        return _META_DIR / self.source / "es_meta.json"

    @staticmethod
    def _signature(texts: list[str]) -> str:
        h = hashlib.sha256()
        # analyzer 进签名:换分词器(如 standard -> ik_max_word)即视为索引变更,强制重建,
        # 否则缓存命中会拿旧分词的索引继续用,改配置不生效。
        h.update(settings.es_analyzer.encode("utf-8"))
        h.update(settings.es_search_analyzer.encode("utf-8"))
        h.update(b"\x00")
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

    def _create_index(self) -> None:
        """建索引,text 字段挂配置里的分词器。IK 插件没装时 ES 会拒(unknown analyzer),
        捕获后回退 standard(按字切),保证无插件环境也能跑、只是中文召回差些。"""
        def _mappings(analyzer: str, search_analyzer: str) -> dict:
            return {"properties": {"text": {
                "type": "text",
                "analyzer": analyzer,
                "search_analyzer": search_analyzer,
            }}}

        try:
            self._es.indices.create(
                index=self.index,
                mappings=_mappings(settings.es_analyzer, settings.es_search_analyzer),
            )
        except Exception:
            logger.warning(
                "ES 分词器 %s 不可用(IK 插件未装?),回退 standard | source=%s",
                settings.es_analyzer, self.source,
            )
            self._es.indices.create(
                index=self.index,
                mappings=_mappings("standard", "standard"),
            )

    def build(self, atoms: list[SchemaAtom]) -> None:
        from elasticsearch import Elasticsearch, helpers

        texts = [a.index_text() for a in atoms]
        if not texts:
            return
        sig = self._signature(texts)

        try:
            self._es = Elasticsearch(settings.es_url, request_timeout=10)
            if not self._es.ping():
                self._ok = False
                logger.info("ES ping 失败,跳过关键字路 | source=%s", self.source)
                return

            # 缓存命中:索引在 + 签名一致 -> 不重建
            if self._es.indices.exists(index=self.index) and self._load_meta_sig() == sig:
                self._ok = True
                logger.info("ES 索引命中缓存 | source=%s | %d 原子", self.source, len(atoms))
                return

            if self._es.indices.exists(index=self.index):
                self._es.indices.delete(index=self.index)
            self._create_index()
            helpers.bulk(self._es, [
                {"_index": self.index, "_id": a.id, "text": a.index_text()}
                for a in atoms
            ])
            self._es.indices.refresh(index=self.index)
            self._save_meta_sig(sig)
            self._ok = True
            logger.info("ES 索引已重建 | source=%s | %d 原子", self.source, len(atoms))
        except Exception:
            self._ok = False
            logger.exception("ES 不可用,跳过关键字路 | source=%s", self.source)

    def available(self) -> bool:
        return self._ok

    def query(self, question: str, top_k: int) -> list[Hit]:
        if not self._ok or self._es is None:
            return []
        try:
            res = self._es.search(
                index=self.index,
                size=top_k,
                query={"match": {"text": question}},
            )
            return [Hit(h["_id"], float(h["_score"]), self.name)
                    for h in res["hits"]["hits"]]
        except Exception:
            logger.exception("ES 查询失败 | source=%s", self.source)
            return []
