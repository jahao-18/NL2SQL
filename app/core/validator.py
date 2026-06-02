"""SQL 安全校验:只允许单条 SELECT,禁危险关键字,强制 LIMIT。"""
from __future__ import annotations

import re

import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import DML, Keyword

from app.core.config import settings

# 任何出现这些关键字的 SQL 都直接拒绝(即使在子查询里)
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "REPLACE", "ATTACH", "DETACH", "PRAGMA",
    "VACUUM", "REINDEX", "GRANT", "REVOKE",
}


class SQLValidationError(ValueError):
    """SQL 不满足安全约束。"""


def validate_and_fix(sql: str, allowed_tables: dict[str, list[str]]) -> tuple[str, bool]:
    """校验 SQL 并补 LIMIT,返回 (最终可执行 SQL, truncated)。truncated=True 表示用户请求的 LIMIT 被收紧到 MAX_ROWS。失败抛 SQLValidationError。"""
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise SQLValidationError("生成的 SQL 为空")

    statements = sqlparse.parse(sql)
    if len(statements) != 1:
        raise SQLValidationError("只允许单条 SQL 语句")

    stmt: Statement = statements[0]

    # 1) 顶层 DML 必须是 SELECT
    first_dml = next((t for t in stmt.flatten() if t.ttype is DML), None)
    if first_dml is None or first_dml.normalized.upper() != "SELECT":
        raise SQLValidationError("仅允许 SELECT 查询")

    # 2) 任何位置不得出现禁用关键字
    for tok in stmt.flatten():
        if tok.ttype in (DML, Keyword, Keyword.DDL, Keyword.DML):
            if tok.normalized.upper() in FORBIDDEN_KEYWORDS:
                raise SQLValidationError(f"包含禁用关键字: {tok.normalized}")

    # 3) 表名白名单(粗校验:FROM/JOIN 后第一个标识符)
    _check_tables_in_whitelist(sql, set(allowed_tables.keys()))

    # 4) 强制 LIMIT,并记录是否截断
    truncated = False
    limit_match = re.search(r"\blimit\s+(\d+)\b", sql, flags=re.IGNORECASE)
    if not limit_match:
        sql = f"{sql} LIMIT {settings.max_rows}"
    else:
        user_limit = int(limit_match.group(1))
        if user_limit > settings.max_rows:
            truncated = True
            sql = _cap_limit(sql, settings.max_rows)

    return sql, truncated


def _check_tables_in_whitelist(sql: str, whitelist: set[str]) -> None:
    # 抓 FROM xxx / JOIN xxx 后的表名(忽略 schema 前缀和别名)
    pattern = re.compile(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
    found = {m.group(1) for m in pattern.finditer(sql)}
    illegal = found - whitelist
    if illegal:
        raise SQLValidationError(f"引用了未授权的表: {', '.join(sorted(illegal))}")


def _cap_limit(sql: str, cap: int) -> str:
    """如果 LIMIT 超过 cap,强制收紧到 cap;只处理简单的 LIMIT N 形式。"""
    def replace(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return f"LIMIT {min(n, cap)}"

    return re.sub(r"\blimit\s+(\d+)\b", replace, sql, flags=re.IGNORECASE)
