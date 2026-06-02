"""跨方言只读 SQL 执行器(SQLAlchemy)。

engine 在 data_sources 模块按 URL 缓存,并在连接层强制只读。
对 SQLite 用 ?mode=ro,对 PostgreSQL 用 default_transaction_read_only。
"""
from __future__ import annotations

import time

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.data_sources import get_engine, get_source


class SQLExecutionError(RuntimeError):
    """SQL 执行阶段失败。"""


def execute(sql: str, source_name: str | None = None) -> tuple[list[str], list[list], int]:
    """执行 SELECT,返回 (columns, rows, elapsed_ms)。

    max_rows 控制单次最多返回的行数;超出的行不读取。
    """
    source = get_source(source_name)
    engine = get_engine(source)

    start = time.perf_counter()
    try:
        with engine.connect() as conn:
            cur = conn.execute(text(sql))
            columns = list(cur.keys())
            rows = cur.fetchmany(settings.max_rows)
    except SQLAlchemyError as e:
        # SQLAlchemy 把驱动错误包一层,取 orig 更清晰
        orig = getattr(e, "orig", None)
        raise SQLExecutionError(str(orig) if orig else str(e)) from e

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return columns, [list(r) for r in rows], elapsed_ms
