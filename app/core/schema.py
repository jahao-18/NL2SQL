"""Schema 加载:跨方言读取表/列结构,生成喂给 LLM 的 DDL-like 文本 + 表白名单。

- SQLite: 直接读 sqlite_master.sql,保留原 CREATE TABLE 文本里的 `-- 中文注释`。
- 其它方言(PostgreSQL/MySQL): 用 SQLAlchemy inspect,从 column.comment 拿注释。
- 通用: 对低基数 TEXT 列跑 SELECT DISTINCT,把发现的取值注入 prompt。
- 通用: 末尾追加业务词表(可选)。
"""
from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.core.data_sources import DataSource, get_engine, get_source

logger = logging.getLogger("nl2sql.schema")

# 对低基数 TEXT 列自动发现取值的阈值;超过则放弃
ENUM_DISCOVER_MAX = 20
ENUM_DISCOVER_TEXT_LEN_LIMIT = 32  # 取值文本太长(可能是评论/详情)就跳过


@dataclass
class SchemaInfo:
    ddl_text: str                          # 拼接给 LLM 的文本(含注释 + 发现的取值 + 词表 + 派生指标)
    tables: dict[str, list[str]] = field(default_factory=dict)  # 表名 -> 列名列表(白名单)
    pure_ddl: str = ""                      # 仅表结构(CREATE TABLE),供前端「查看表结构」展示,不含 enum/词表/指标


_COL_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+", re.MULTILINE)


def _extract_columns_from_sqlite_ddl(ddl: str) -> list[str]:
    """从 sqlite CREATE TABLE 语句体粗抽列名,排除表级约束。"""
    inside = ddl[ddl.index("(") + 1 : ddl.rindex(")")]
    cols: list[str] = []
    skip = {"PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT", "INDEX", "KEY"}
    for line in inside.splitlines():
        m = _COL_LINE_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        if name.upper() in skip:
            continue
        cols.append(name)
    return cols


def _sqlite_ddl_text(engine: Engine) -> tuple[str, dict[str, list[str]]]:
    """SQLite 走 sqlite_master,保留原 DDL 注释。"""
    parts: list[str] = []
    tables: dict[str, list[str]] = {}
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )).all()
    for name, sql in rows:
        if not sql:
            continue
        parts.append(sql.strip() + ";")
        tables[name] = _extract_columns_from_sqlite_ddl(sql)
    return "\n\n".join(parts), tables


def _generic_ddl_text(engine: Engine) -> tuple[str, dict[str, list[str]]]:
    """非 SQLite 走 SQLAlchemy inspect,从 column.comment 拿注释。

    构造形如 `CREATE TABLE foo (\n  col TYPE NOT NULL,  -- comment\n  ...\n);`
    供 LLM 阅读,跟 SQLite 路径输出格式一致。
    """
    insp = inspect(engine)
    parts: list[str] = []
    tables: dict[str, list[str]] = {}
    for table_name in insp.get_table_names():
        cols = insp.get_columns(table_name)
        if not cols:
            continue
        col_names = [c["name"] for c in cols]
        tables[table_name] = col_names

        lines = [f"CREATE TABLE {table_name} ("]
        for i, c in enumerate(cols):
            col_type = str(c["type"])
            nullable = "" if c.get("nullable", True) else " NOT NULL"
            comment = c.get("comment") or ""
            comma = "," if i < len(cols) - 1 else ""
            comment_part = f"  -- {comment}" if comment else ""
            lines.append(f"    {c['name']:<14} {col_type}{nullable}{comma}{comment_part}")
        lines.append(");")
        parts.append("\n".join(lines))
    return "\n\n".join(parts), tables


def _discover_enums(engine: Engine, tables: dict[str, list[str]], dialect: str) -> str:
    """对每个 TEXT 列跑 SELECT DISTINCT 抽样;低基数(<=ENUM_DISCOVER_MAX)就注入。

    用 SQLAlchemy inspect 拿列类型(是否文本),避免硬编码方言判断。
    """
    insp = inspect(engine)
    discovered: list[str] = []
    for tbl, _ in tables.items():
        try:
            cols = insp.get_columns(tbl)
        except Exception:
            continue
        for c in cols:
            col_type = str(c["type"]).upper()
            if not any(t in col_type for t in ("TEXT", "CHAR", "STRING")):
                continue
            col_name = c["name"]
            try:
                with engine.connect() as conn:
                    rows = conn.execute(text(
                        f"SELECT DISTINCT {col_name} FROM {tbl} "
                        f"WHERE {col_name} IS NOT NULL LIMIT {ENUM_DISCOVER_MAX + 1}"
                    )).all()
            except Exception as e:
                logger.debug("enum discover skip %s.%s: %s", tbl, col_name, e)
                continue
            vals = [str(r[0]) for r in rows if r[0] is not None]
            if not vals or len(vals) > ENUM_DISCOVER_MAX:
                continue
            # 跳过长文本(评论、地址等)
            if any(len(v) > ENUM_DISCOVER_TEXT_LEN_LIMIT for v in vals):
                continue
            discovered.append(f"- {tbl}.{col_name} 取值: {' / '.join(sorted(vals))}")
    if not discovered:
        return ""
    return "【字段取值自动发现】\n" + "\n".join(discovered)


def _read_glossary(path: Path | None) -> str:
    if not path:
        return ""
    if not path.exists():
        logger.warning("glossary 文件不存在: %s", path)
        return ""
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=8)
def load_schema(source_name: str | None = None) -> SchemaInfo:
    """按数据源名加载 schema。返回 SchemaInfo,内含拼装好的 DDL 文本 + 表/列白名单。"""
    source = get_source(source_name)
    engine = get_engine(source)

    if source.dialect == "sqlite":
        ddl_text, tables = _sqlite_ddl_text(engine)
    else:
        ddl_text, tables = _generic_ddl_text(engine)

    if not tables:
        raise RuntimeError(f"数据源 {source.name} 没有可用的表")

    parts = [ddl_text]
    enum_block = _discover_enums(engine, tables, source.dialect)
    if enum_block:
        parts.append(enum_block)
    glossary = _read_glossary(source.glossary_path)
    if glossary:
        parts.append(glossary)

    # ddl_text 是喂 LLM 的完整上下文(表 + 取值发现 + 词表 + 派生指标);
    # pure_ddl 只含 CREATE TABLE,供前端「查看表结构」展示——业务说明那些不该露给用户看。
    return SchemaInfo(ddl_text="\n\n".join(parts), tables=tables, pure_ddl=ddl_text)


@lru_cache(maxsize=32)
def list_table_names(source_name: str | None = None) -> tuple[str, ...]:
    """只取某数据源的表名(不拼 DDL、不做 enum 发现),供数据源路由快速构建目录。"""
    source = get_source(source_name)
    engine = get_engine(source)
    try:
        return tuple(inspect(engine).get_table_names())
    except Exception as e:
        logger.warning("list_table_names 失败 %s: %s", source.name, e)
        return ()


@lru_cache(maxsize=32)
def count_columns(source_name: str | None = None) -> int:
    """某数据源的总列数(不拼 DDL、不做 enum 发现),供检索触发判断"宽表库"用。失败返回 0。"""
    source = get_source(source_name)
    engine = get_engine(source)
    insp = inspect(engine)
    total = 0
    try:
        for t in insp.get_table_names():
            try:
                total += len(insp.get_columns(t))
            except Exception:
                continue
    except Exception as e:
        logger.warning("count_columns 失败 %s: %s", source.name, e)
        return 0
    return total


def clear_cache() -> None:
    load_schema.cache_clear()
    list_table_names.cache_clear()
    count_columns.cache_clear()


def list_source_dialect(source_name: str | None = None) -> str:
    """供 chain.py 注入 prompt 用,返回 'sqlite' / 'postgresql' 等。"""
    return get_source(source_name).dialect
