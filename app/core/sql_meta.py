"""从已生成的 SQL 抽取每个输出列的源表达式,供前端在表头下方显示真实字段来源。

解析失败或某列无法定位时返回空字符串,前端会回退到只显示别名。
"""
from __future__ import annotations

import sqlparse
from sqlparse.sql import Identifier, IdentifierList
from sqlparse.tokens import DML, Keyword


def extract_column_sources(sql: str) -> list[str]:
    """返回外层 SELECT 每列的源表达式(去掉 AS 别名后的部分)。

    顺序与 executor 返回的 columns 对齐。任意一项解析失败则该项为空字符串。
    """
    try:
        parsed = sqlparse.parse(sql)[0]
    except Exception:
        return []

    # 找最后一个顶层 DML SELECT(避开 WITH 子句里的 SELECT)
    select_idx = None
    for i, tok in enumerate(parsed.tokens):
        if tok.ttype is DML and tok.normalized.upper() == "SELECT":
            select_idx = i
    if select_idx is None:
        return []

    sources: list[str] = []
    i = select_idx + 1
    while i < len(parsed.tokens):
        tok = parsed.tokens[i]
        if tok.ttype is Keyword and tok.normalized.upper() == "FROM":
            break
        if tok.is_whitespace:
            i += 1
            continue
        # SELECT 后可能紧跟 DISTINCT / ALL
        if tok.ttype is Keyword and tok.normalized.upper() in {"DISTINCT", "ALL"}:
            i += 1
            continue
        if isinstance(tok, IdentifierList):
            for ident in tok.get_identifiers():
                sources.append(_source_of(ident))
        elif isinstance(tok, Identifier):
            sources.append(_source_of(tok))
        else:
            # Wildcard / Function / 字面量等
            sources.append(tok.value.strip())
        i += 1
    return sources


def _source_of(ident) -> str:
    """取 identifier 中 AS 之前的源表达式;无 AS 则整体作为源。"""
    alias = ident.get_alias() if hasattr(ident, "get_alias") else None
    if not alias:
        return ident.value.strip()

    tokens = list(ident.tokens)
    # 显式 AS 关键字
    as_idx = None
    for idx, t in enumerate(tokens):
        if t.ttype is Keyword and t.normalized.upper() == "AS":
            as_idx = idx
            break
    if as_idx is not None:
        return "".join(t.value for t in tokens[:as_idx]).strip()

    # 隐式别名:`expr alias` —— 去掉末尾的标识符 token
    end = len(tokens) - 1
    while end >= 0 and tokens[end].is_whitespace:
        end -= 1
    return "".join(t.value for t in tokens[:end]).strip()
