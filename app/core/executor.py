"""跨方言只读 SQL 执行器(SQLAlchemy)。

engine 在 data_sources 模块按 URL 缓存,并在连接层强制只读。
对 SQLite 用 ?mode=ro,对 PostgreSQL 用 default_transaction_read_only。
"""
from __future__ import annotations

import re
import time

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.data_sources import get_engine, get_source


class SQLExecutionError(RuntimeError):
    """SQL 执行阶段失败。"""


def execute(sql: str, source_name: str | None = None) -> tuple[list[str], list[list], int, bool]:
    """执行 SELECT,返回 (columns, rows, elapsed_ms, capped)。

    截断探测:若 SQL 末尾的 `LIMIT N` 正好等于系统上限 max_rows(无论是校验器补的、还是 LLM
    擅自写的),内部把它抬到 max_rows + 1 执行 + 多取一行,据此判断"是否还有更多":
      - 取到 > max_rows 行 → 实际被截断,capped=True,裁回 max_rows;
      - 取到 == max_rows 行(结果恰好这么多)→ capped=False,不误报。
    展示给用户的 SQL(safe_sql)不变,只在执行时内部抬这一行。用户明确的小 LIMIT(如"前5")不动。
    """
    source = get_source(source_name)
    engine = get_engine(source)
    cap = settings.max_rows

    # 仅当"末尾 LIMIT == 系统上限"时抬一行探测;末尾是更小的用户 LIMIT 则原样执行,不探测。
    exec_sql = re.sub(
        rf"(?i)\blimit\s+{cap}(\s+offset\s+\d+)?\s*$",
        lambda m: f"LIMIT {cap + 1}{m.group(1) or ''}",
        sql.strip(),
    )

    start = time.perf_counter()
    try:
        with engine.connect() as conn:
            if source.dialect == "postgresql" and settings.query_timeout_seconds > 0:
                ms = max(1, int(settings.query_timeout_seconds * 1000))
                with conn.begin():
                    conn.execute(text(f"SET LOCAL statement_timeout = {ms}"))
                    cur = conn.execute(text(exec_sql))
                    columns = list(cur.keys())
                    rows = cur.fetchmany(cap + 1)
            elif source.dialect == "sqlite" and settings.query_timeout_seconds > 0:
                raw = getattr(conn.connection, "driver_connection", None)
                deadline = time.perf_counter() + settings.query_timeout_seconds

                def _abort_if_timeout() -> int:
                    return 1 if time.perf_counter() > deadline else 0

                if raw is not None and hasattr(raw, "set_progress_handler"):
                    raw.set_progress_handler(_abort_if_timeout, 10000)
                try:
                    cur = conn.execute(text(exec_sql))
                    columns = list(cur.keys())
                    rows = cur.fetchmany(cap + 1)
                finally:
                    if raw is not None and hasattr(raw, "set_progress_handler"):
                        raw.set_progress_handler(None, 0)
            else:
                cur = conn.execute(text(exec_sql))
                columns = list(cur.keys())
                rows = cur.fetchmany(cap + 1)
    except SQLAlchemyError as e:
        # SQLAlchemy 把驱动错误包一层,取 orig 更清晰
        orig = getattr(e, "orig", None)
        raise SQLExecutionError(str(orig) if orig else str(e)) from e

    capped = len(rows) > cap
    if capped:
        rows = rows[:cap]
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return columns, [list(r) for r in rows], elapsed_ms, capped
