"""验证 server 检索后端(四路真组件)是否生效:Milvus(向量)+ ES(关键字)+ PG/pgvector(术语)+ 关系图。

跑法:RETRIEVAL_BACKEND=server 下,对教学业务库走一遍
retrieve_context —— 与 service.py 完全相同的入口。预期日志里出现:
    Milvus 索引已重建 / Milvus 索引命中缓存
    ES 索引已重建 / ES 索引命中缓存
    术语索引已重建 / 术语索引命中缓存
末尾 retrievers_used 里出现 vector / keyword / glossary / graph 即证明真组件生效。
"""
from __future__ import annotations

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

from app.core.config import settings
from app.core.retrieval import retrieve_context
from app.core.schema import load_schema

SOURCE = sys.argv[1] if len(sys.argv) > 1 else "teaching"
QUESTION = sys.argv[2] if len(sys.argv) > 2 else "统计各学院当前开设的教学班数量"

print(f"== retrieval_backend = {settings.retrieval_backend}", flush=True)
print(f"== milvus_uri = {settings.milvus_uri} | es_url = {settings.es_url} | pg_dsn = {settings.pg_dsn}", flush=True)
print(f"== source = {SOURCE}", flush=True)

info = load_schema(SOURCE)
print(f"== ddl_text 长度 = {len(info.ddl_text)} 字符", flush=True)

rc = retrieve_context(QUESTION, SOURCE, info.ddl_text)
print("=" * 60, flush=True)
if rc is None:
    print("retrieve_context 返回 None —— 回退整库 DDL(未触发检索)", flush=True)
else:
    print(f"检索成功 | retrievers_used = {rc.retrievers_used}", flush=True)
    print(f"选中表 = {rc.tables}", flush=True)
    print("--- 精简上下文(前 600 字) ---", flush=True)
    print(rc.context_text[:600], flush=True)
