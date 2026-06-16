"""SQL 安全校验:只允许单条 SELECT,禁危险关键字,强制 LIMIT。"""
from __future__ import annotations

import re

import sqlparse
from sqlparse.sql import Identifier, IdentifierList, Parenthesis, Statement, TokenList
from sqlparse.tokens import DML, Keyword, Name

from app.core.config import settings

# 任何出现这些关键字的 SQL 都直接拒绝(即使在子查询里)
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "REPLACE", "ATTACH", "DETACH", "PRAGMA",
    "VACUUM", "REINDEX", "GRANT", "REVOKE",
}


class SQLValidationError(ValueError):
    """SQL 不满足安全约束。"""


def validate_and_fix(
    sql: str,
    allowed_tables: dict[str, list[str]],
    blocked_columns: set[str] | None = None,
) -> tuple[str, bool]:
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

    # 3.5) 字段治理黑名单:敏感/禁用/废弃字段不允许执行。
    blocked_hit = _blocked_column_hit(sql, blocked_columns or set())
    if blocked_hit:
        raise SQLValidationError(f"引用了不可用于问数的字段: {blocked_hit}")

    # 4) 强制 LIMIT,并记录是否截断
    truncated = False
    limit_match = re.search(r"\blimit\s+(\d+)(\s+offset\s+\d+)?\s*$", sql, flags=re.IGNORECASE)
    if not limit_match:
        sql = f"{sql} LIMIT {settings.max_rows}"
    else:
        user_limit = int(limit_match.group(1))
        if user_limit > settings.max_rows:
            truncated = True
            sql = _cap_limit(sql, settings.max_rows)

    return sql, truncated


def _blocked_column_hit(sql: str, blocked_columns: set[str]) -> str | None:
    if not blocked_columns:
        return None
    lower_sql = sql.lower()
    for full in sorted(blocked_columns):
        if "." not in full:
            continue
        table, column = full.split(".", 1)
        patterns = [
            rf"\b{re.escape(table.lower())}\s*\.\s*{re.escape(column.lower())}\b",
            rf"\b{re.escape(column.lower())}\b",
        ]
        if any(re.search(pattern, lower_sql) for pattern in patterns):
            return full
    return None


def _check_tables_in_whitelist(sql: str, whitelist: set[str]) -> None:
    # 抓 FROM xxx / JOIN xxx 后的表名(忽略 schema 前缀和别名)
    statements = sqlparse.parse(sql)
    if not statements:
        raise SQLValidationError("SQL 解析失败")
    ctes = _cte_names(statements[0])
    illegal = (_table_refs(statements[0]) - ctes) - whitelist
    if illegal:
        raise SQLValidationError(f"引用了未授权的表: {', '.join(sorted(illegal))}")


def _meaningful(tokens: TokenList) -> list:
    return [t for t in tokens.tokens if not t.is_whitespace and not t.match(Keyword, ",")]


def _contains_select(token) -> bool:
    return isinstance(token, TokenList) and any(
        t.ttype is DML and t.normalized.upper() == "SELECT" for t in token.flatten()
    )


def _clean_name(name: str | None) -> str | None:
    return name.strip('"`[]') if name else None


def _identifier_names(token) -> set[str]:
    names: set[str] = set()
    if isinstance(token, IdentifierList):
        for ident in token.get_identifiers():
            names |= _identifier_names(ident)
        return names
    if isinstance(token, Identifier):
        if _contains_select(token):
            return _table_refs(token)
        real = _clean_name(token.get_real_name())
        if real:
            names.add(real)
        return names
    if token.ttype is Name:
        name = _clean_name(token.value)
        if name:
            names.add(name)
    return names


def _cte_names(stmt: Statement) -> set[str]:
    tokens = _meaningful(stmt)
    if not tokens or tokens[0].normalized.upper() != "WITH":
        return set()
    names: set[str] = set()
    for tok in tokens[1:]:
        if tok.ttype is DML and tok.normalized.upper() == "SELECT":
            break
        if isinstance(tok, IdentifierList):
            for ident in tok.get_identifiers():
                name = _clean_name(ident.get_name())
                if name:
                    names.add(name)
        elif isinstance(tok, Identifier):
            name = _clean_name(tok.get_name())
            if name:
                names.add(name)
    return names


def _table_refs(token_list: TokenList) -> set[str]:
    refs: set[str] = set()
    tokens = _meaningful(token_list)
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        norm = tok.normalized.upper() if hasattr(tok, "normalized") else ""
        if norm == "FROM" or norm.endswith(" JOIN"):
            if i + 1 < len(tokens):
                refs |= _identifier_names(tokens[i + 1])
            i += 2
            continue
        if isinstance(tok, Parenthesis) and _contains_select(tok):
            refs |= _table_refs(tok)
        elif isinstance(tok, TokenList) and not isinstance(tok, Identifier):
            refs |= _table_refs(tok)
        i += 1
    return refs


def _cap_limit(sql: str, cap: int) -> str:
    """如果 LIMIT 超过 cap,强制收紧到 cap;只处理简单的 LIMIT N 形式。"""
    def replace(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return f"LIMIT {min(n, cap)}{m.group(2) or ''}"

    return re.sub(r"\blimit\s+(\d+)(\s+offset\s+\d+)?\s*$", replace, sql, flags=re.IGNORECASE)
