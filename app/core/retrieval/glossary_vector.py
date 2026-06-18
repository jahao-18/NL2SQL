"""业务术语词表检索器(第 4 路):把 glossary 业务规则拆成条目,存进 PostgreSQL + pgvector,
按问题向量召回相关条目。

为什么需要它:大库走 schema 检索时 service 用精简 schema 文本**替换**整库 DDL,
原本附在 DDL 末尾的整份 glossary(取值映射 / JOIN 提示 / 状态枚举等业务规则)会被丢弃。
本路把这些规则按问题召回塞回上下文,同时命中条目引用的表并入 RRF 融合,影响选表。

存储:PostgreSQL 一张表 glossary_entries(source, entry_id, content, tables, embedding)。
embedding 列用无维度 vector(条目量小,精确 KNN 顺序扫足够,免去维度管理)。embedding 仍由
DashScope 生成。按条目文本签名缓存:签名一致就跳过重嵌入。连不上 / 无 glossary 时
available() 返回 False,pipeline 跳过 -> 退化为前三路,不影响可用。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass

from app.core.config import ROOT_DIR, settings
from app.core.retrieval.embedding import embed

logger = logging.getLogger("nl2sql.retrieval.glossary")

_META_DIR = ROOT_DIR / "data" / "retrieval_index"


@dataclass
class GlossaryEntry:
    """一条业务术语 / 规则:content 用于注入 prompt,tables 是它引用的表(用于并入 RRF 融合)。"""
    entry_id: str
    content: str
    tables: list[str]
    score: float = 0.0


def parse_glossary(text: str, known_tables: list[str]) -> list[GlossaryEntry]:
    """把 glossary markdown 拆成条目。

    - `## 表 X` / `## X` 这类二级标题设定"当前表"上下文(BIRD 式按表分组的词表)。
    - 每个 `- ` 开头的项是一条;紧随其后的非项、非标题行视为该条的续行(如 BIRD 的多行取值说明)。
    - `【...】`、`#` 标题等只作分节,不单独成条。
    - 每条引用的表 = 当前节的表(若有)+ 正文里出现的已知表名(按标识符边界匹配,兼容 `users.city`)。
    """
    known = sorted(known_tables, key=len, reverse=True)  # 长名优先,避免子串误命中
    entries: list[GlossaryEntry] = []
    section_table = ""
    cur: list[str] | None = None  # 当前条目的行缓冲

    def _flush() -> None:
        nonlocal cur
        if not cur:
            return
        content = " ".join(s.strip() for s in cur).strip()
        cur = None
        if not content:
            return
        tables: list[str] = []
        if section_table:
            tables.append(section_table)
        for t in known:
            if t in tables:
                continue
            if re.search(rf"(?<![\w]){re.escape(t)}(?![\w])", content):
                tables.append(t)
        entries.append(GlossaryEntry(entry_id=str(len(entries)), content=content, tables=tables))

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("##"):
            _flush()
            head = stripped.lstrip("#").strip()
            head = re.sub(r"^(表|table)\s*", "", head, flags=re.IGNORECASE).strip()
            section_table = head if head in known_tables else ""
            continue
        if stripped.startswith("#") or (stripped.startswith("【") and stripped.endswith("】")):
            _flush()
            continue
        if stripped.startswith(("-", "*", "•")):
            _flush()
            cur = [stripped.lstrip("-*• ").strip()]
        elif cur is not None:
            cur.append(stripped)   # 续行,接到当前条目
    _flush()
    return entries


class GlossaryRetriever:
    """业务术语词表检索器。不实现通用 Retriever 接口(query 返回的是条目不是原子 Hit),
    由 pipeline 像 graph 一样单独编排:命中条目的表并入 RRF,条目正文注入上下文。"""
    name = "glossary"
    _TABLE = "glossary_entries"

    def __init__(self, source: str) -> None:
        self.source = source
        self._ok = False

    @staticmethod
    def _connect():
        """每次开独立短连接 —— sync 端点跑在线程池,psycopg 连接非线程安全,不能跨线程共享。
        连接开销(~十几 ms)相比每次查询都要调的 DashScope embed 可忽略。vector 扩展由 build
        建好,这里 connect 后直接注册类型适配器即可。"""
        import psycopg
        from pgvector.psycopg import register_vector
        conn = psycopg.connect(settings.pg_dsn, connect_timeout=5)
        register_vector(conn)
        return conn

    def _meta_path(self):
        return _META_DIR / self.source / "glossary_meta.json"

    @staticmethod
    def _signature(contents: list[str]) -> str:
        h = hashlib.sha256()
        h.update(settings.embedding_model.encode("utf-8"))  # 换模型 -> 维度/语义变 -> 强制重建
        h.update(b"\x00")
        for c in contents:
            h.update(c.encode("utf-8"))
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

    @staticmethod
    def _ensure_schema(conn) -> None:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {GlossaryRetriever._TABLE} ("
                "  source    text NOT NULL,"
                "  entry_id  text NOT NULL,"
                "  content   text NOT NULL,"
                "  tables    text[] NOT NULL DEFAULT '{}',"
                "  embedding vector NOT NULL,"
                "  PRIMARY KEY (source, entry_id))"
            )
        conn.commit()

    def build(self, entries: list[GlossaryEntry]) -> None:
        """建/加载该源的术语索引。entries 由 pipeline 调 parse_glossary 传入(空则该路不就绪)。"""
        if not entries:
            logger.info("无 glossary 条目,跳过术语路 | source=%s", self.source)
            return

        import psycopg
        from pgvector.psycopg import register_vector

        contents = [e.content for e in entries]
        sig = self._signature(contents)
        try:
            # build 在缓存预热时单线程跑一次,自己开个临时连接;扩展未必存在,故不能用 _connect。
            conn = psycopg.connect(settings.pg_dsn, connect_timeout=5)
            with conn:
                self._ensure_schema(conn)      # 先建 vector 扩展 + 表
                register_vector(conn)          # 扩展就绪后才能注册 vector 类型适配器

                with conn.cursor() as cur:
                    cur.execute(f"SELECT count(*) FROM {self._TABLE} WHERE source = %s", (self.source,))
                    have = cur.fetchone()[0]
                # 缓存命中:库里有该源数据 + 签名一致 -> 不重嵌入
                if have and self._load_meta_sig() == sig:
                    self._ok = True
                    logger.info("术语索引命中缓存 | source=%s | %d 条", self.source, have)
                    return

                mat = embed(contents)
                if mat.shape[0] != len(entries) or mat.shape[0] == 0:
                    return
                with conn.cursor() as cur:
                    cur.execute(f"DELETE FROM {self._TABLE} WHERE source = %s", (self.source,))
                    cur.executemany(
                        f"INSERT INTO {self._TABLE} (source, entry_id, content, tables, embedding) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        [(self.source, e.entry_id, e.content, e.tables, mat[i])
                         for i, e in enumerate(entries)],
                    )
            self._save_meta_sig(sig)
            self._ok = True
            logger.info("术语索引已重建 | source=%s | %d 条", self.source, len(entries))
        except Exception:
            self._ok = False
            logger.exception("PG/pgvector 不可用,跳过术语路 | source=%s", self.source)

    def available(self) -> bool:
        return self._ok

    def query(self, question: str, top_k: int) -> list[GlossaryEntry]:
        if not self._ok:
            return []
        try:
            qvec = embed([question])[0]
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    f"SELECT entry_id, content, tables, 1 - (embedding <=> %s) AS score "
                    f"FROM {self._TABLE} WHERE source = %s "
                    "ORDER BY embedding <=> %s LIMIT %s",
                    (qvec, self.source, qvec, top_k),
                )
                rows = cur.fetchall()
            return [GlossaryEntry(entry_id=r[0], content=r[1], tables=list(r[2]), score=float(r[3]))
                    for r in rows]
        except Exception:
            logger.exception("术语查询失败 | source=%s", self.source)
            return []
