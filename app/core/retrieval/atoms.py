"""把一个数据源的 schema 拆成可检索的 SchemaAtom 列表(每列一个 + 每表一个)。

元数据来源(尽量通用,不绑定 BIRD):
  - 表/列/类型/主键/注释: SQLAlchemy inspect(跨方言)
  - 列业务描述/自然名/取值含义: 若 sqlite 库旁有 database_description/*.csv 则解析(BIRD 自带)
  - 低基数取值示例: 对文本列采样 SELECT DISTINCT
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.core.data_sources import get_engine, get_source
from app.core.retrieval.base import SchemaAtom
from app.core.schema_profile import load_profile

logger = logging.getLogger("nl2sql.retrieval.atoms")

# 与 app.core.schema 的完整 Schema 枚举发现上限保持一致。若这里更小，
# 检索模式可能丢掉完整 Schema 已发现的合法枚举值，导致模型重新猜值。
_ENUM_MAX = 20
_ENUM_TEXT_LEN_LIMIT = 32


def _sqlite_path_from_url(url: str) -> Path | None:
    """从 sqlite SQLAlchemy URL 还原磁盘路径,兼容只读 URI 形式 sqlite:///file:PATH?...。"""
    if not url.startswith("sqlite:"):
        return None
    body = url.split("sqlite:///", 1)[-1]
    if body.startswith("file:"):
        body = body[len("file:"):]
    body = body.split("?", 1)[0]
    if not body or body == ":memory:":
        return None
    return Path(body)


def _load_descriptions(url: str) -> dict[tuple[str, str], tuple[str, str, str]]:
    """返回 {(table, column): (自然名, 描述, 取值含义)};没有 database_description 目录则空。

    BIRD 的 description CSV 每表一个文件,文件名即表名,列名大小写/留空不统一,做容错。
    """
    db_path = _sqlite_path_from_url(url)
    if not db_path:
        return {}
    desc_dir = db_path.parent / "database_description"
    if not desc_dir.exists():
        return {}

    out: dict[tuple[str, str], tuple[str, str, str]] = {}
    for csv_path in desc_dir.glob("*.csv"):
        table = csv_path.stem
        rows = _read_csv(csv_path)
        for row in rows:
            norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            col = norm.get("original_column_name") or norm.get("column_name")
            if not col:
                continue
            friendly = norm.get("column_name", "")
            desc = norm.get("column_description", "")
            vdesc = norm.get("value_description", "")
            out[(table, col)] = (friendly, desc, vdesc)
    return out


def _read_csv(path: Path) -> list[dict]:
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            with path.open(encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except (UnicodeDecodeError, csv.Error):
            continue
    return []


def _sample_enum(engine: Engine, table: str, column: str) -> str:
    """低基数文本列的取值示例;非低基数/长文本返回空串。"""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                f'SELECT DISTINCT "{column}" FROM "{table}" '
                f'WHERE "{column}" IS NOT NULL LIMIT {_ENUM_MAX + 1}'
            )).all()
    except Exception:
        return ""
    vals = [str(r[0]) for r in rows if r[0] is not None]
    if not vals or len(vals) > _ENUM_MAX:
        return ""
    if any(len(v) > _ENUM_TEXT_LEN_LIMIT for v in vals):
        return ""
    return " / ".join(sorted(vals))


def extract_atoms(source_name: str) -> list[SchemaAtom]:
    """抽取某数据源的全部 schema 原子。"""
    source = get_source(source_name)
    engine = get_engine(source)
    insp = inspect(engine)
    descriptions = _load_descriptions(source.url)
    profile = load_profile(source_name)

    atoms: list[SchemaAtom] = []
    for table in insp.get_table_names():
        try:
            cols = insp.get_columns(table)
        except Exception as e:
            logger.warning("跳过表 %s: %s", table, e)
            continue
        try:
            pk_cols = set(insp.get_pk_constraint(table).get("constrained_columns") or [])
        except Exception:
            pk_cols = set()

        # 表级原子:汇总列名,便于"这张表是干嘛的"这类召回
        col_names = [c["name"] for c in cols]
        table_profile = profile.tables.get(table)
        table_desc_parts = [f"表,包含列: {', '.join(col_names)}"]
        if table_profile:
            if table_profile.business_name:
                table_desc_parts.append(table_profile.business_name)
            if table_profile.description:
                table_desc_parts.append(table_profile.description)
            if table_profile.grain:
                table_desc_parts.append(f"粒度: {table_profile.grain}")
            if table_profile.default_filters:
                table_desc_parts.append("默认过滤: " + " AND ".join(table_profile.default_filters))
        atoms.append(SchemaAtom(
            source=source_name, table=table,
            description=" | ".join(table_desc_parts),
        ))

        for c in cols:
            name = c["name"]
            prof = profile.columns.get(f"{table}.{name}")
            if prof and (not prof.enabled or prof.sensitive or prof.deprecated):
                continue
            friendly, desc, vdesc = descriptions.get((table, name), ("", "", ""))
            if prof and prof.business_name:
                friendly = prof.business_name
            comment = c.get("comment") or ""
            col_type = str(c["type"])
            full_desc = " ".join(
                p for p in (
                    prof.description if prof else "",
                    desc,
                    comment,
                    f"语义类型: {prof.semantic_type}" if prof and prof.semantic_type else "",
                    f"默认聚合: {prof.default_aggregation}" if prof and prof.default_aggregation else "",
                    f"单位: {prof.unit}" if prof and prof.unit else "",
                ) if p
            )
            value_hints = vdesc
            if prof and prof.enum_values:
                value_hints = " / ".join(prof.enum_values)
            if not value_hints and any(t in col_type.upper() for t in ("TEXT", "CHAR", "STRING")):
                value_hints = _sample_enum(engine, table, name)
            atoms.append(SchemaAtom(
                source=source_name, table=table, column=name,
                col_type=col_type, natural_name=friendly,
                description=full_desc, value_hints=value_hints,
                is_pk=name in pk_cols,
            ))
    return atoms
