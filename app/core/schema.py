"""Schema 加载:从 sqlite_master 读建表语句(含 -- 中文注释),供 prompt 拼装与白名单校验使用。"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.core.config import settings


BUSINESS_NOTES = """
【业务说明 / 取值映射】
- 用户位置有两处:`users.city`(注册时填写)和 `addresses.city / addresses.province`(收货地址)。涉及"省份"必须 JOIN `addresses` 表(`users` 表没有 province)。
- `categories.code` 是英文代号:electronics / clothing / food / book / beauty / sports / home。`categories.name` 是中文名:电子产品 / 服装鞋帽 / 食品饮料 / 图书音像 / 美妆护肤 / 运动户外 / 家居家电。`products` 通过 `category_id` 关联,涉及类目必须 JOIN `categories`。
- 订单状态 `orders.status` 取值:pending / paid / cancelled / refunded(全英文小写)。
- 用户性别 `users.gender` 取值:male / female(全英文小写)。
- `addresses.is_default` 是整数 0 / 1,不是布尔值。
- `created_at` / `registered_at` 是 ISO8601 文本(如 '2025-03-15T10:00:00'),可用 substr/strftime/LIKE 提取年月日。
""".strip()


@dataclass
class SchemaInfo:
    ddl_text: str                          # 拼接所有 CREATE TABLE 后的文本,直接喂 prompt
    tables: dict[str, list[str]] = field(default_factory=dict)  # 表名 -> 列名列表(用于白名单)


_COL_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+", re.MULTILINE)


def _extract_columns(ddl: str) -> list[str]:
    """从 CREATE TABLE 语句体里粗略抽列名。

    只用于白名单校验,不需要严格 SQL 解析:取每行首个标识符,
    排除 PRIMARY/FOREIGN/UNIQUE/CHECK/CONSTRAINT 等表级约束关键字。
    """
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


@lru_cache(maxsize=1)
def load_schema(db_path: str | None = None) -> SchemaInfo:
    """读 sqlite_master,返回带注释的 DDL 文本 + 表/列白名单。带进程级缓存。"""
    path = Path(db_path) if db_path else settings.db_abspath
    if not path.exists():
        raise FileNotFoundError(f"数据库不存在: {path}。请先运行 python scripts/seed_db.py")

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    tables: dict[str, list[str]] = {}
    parts: list[str] = []
    for name, sql in rows:
        if not sql:
            continue
        parts.append(sql.strip() + ";")
        tables[name] = _extract_columns(sql)

    ddl_text = "\n\n".join(parts) + "\n\n" + BUSINESS_NOTES
    return SchemaInfo(ddl_text=ddl_text, tables=tables)


def clear_cache() -> None:
    load_schema.cache_clear()
