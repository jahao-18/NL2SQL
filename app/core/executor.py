"""SQLite 只读执行器。"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from app.core.config import settings


class SQLExecutionError(RuntimeError):
    """SQL 执行阶段失败。"""


def execute(sql: str, db_path: Path | None = None) -> tuple[list[str], list[list], int]:
    """执行 SELECT,返回 (columns, rows, elapsed_ms)。

    用只读 URI 连接,防止任何写入。设置 busy_timeout 避免长锁。
    """
    path = db_path or settings.db_abspath
    if not path.exists():
        raise SQLExecutionError(f"数据库不存在: {path}")

    uri = f"file:{path}?mode=ro"
    start = time.perf_counter()
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=settings.query_timeout_seconds)
    except sqlite3.Error as e:
        raise SQLExecutionError(f"无法打开数据库: {e}") from e

    try:
        conn.execute(f"PRAGMA busy_timeout = {settings.query_timeout_seconds * 1000}")
        cur = conn.execute(sql)
        rows = cur.fetchmany(settings.max_rows)
        columns = [d[0] for d in cur.description] if cur.description else []
    except sqlite3.Error as e:
        raise SQLExecutionError(str(e)) from e
    finally:
        conn.close()

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return columns, [list(r) for r in rows], elapsed_ms
