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
    row_scope: dict[str, object] | None = None,
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

    # 3.5) 字段治理黑名单:敏感/禁用/废弃字段不允许作为结果输出。
    # 注意:部分身份字段可用于 JOIN/WHERE 做行级范围过滤,但不能 SELECT 展示。
    blocked_hit = _blocked_output_column_hit(stmt, blocked_columns or set())
    if blocked_hit:
        raise SQLValidationError(f"引用了不可用于问数的字段: {blocked_hit}")

    # 3.6) 行级范围必须由最终 SQL 明确落实，不能只依赖 LLM prompt。
    _enforce_row_scope(stmt, sql, row_scope or {})

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


_ROW_SCOPE_RULES: dict[str, dict[str, object]] = {
    "student_id": {
        "tables": {
            "student", "enrollment", "score", "evaluation", "assignment_submission",
            "attendance", "learning_activity", "scholarship", "academic_warning",
            "student_task_analytics",
        },
        "columns": {
            "student": "id",
            "enrollment": "student_id",
            "assignment_submission": "student_id",
            "attendance": "student_id",
            "learning_activity": "student_id",
            "scholarship": "student_id",
            "academic_warning": "student_id",
            "student_task_analytics": "student_id",
        },
        "label": "student_id",
    },
    "teacher_id": {
        "tables": {"teacher", "teaching_class", "evaluation", "assignment", "attendance", "learning_activity", "course_assignment_analytics", "student_task_analytics"},
        "columns": {"teacher": "id", "teaching_class": "teacher_id", "course_assignment_analytics": "teacher_id", "student_task_analytics": "teacher_id"},
        "label": "teacher_id",
    },
    "college_id": {
        "tables": {
            "college", "major", "class_group", "student", "teacher", "course", "teaching_class",
            "enrollment", "score", "evaluation", "assignment", "assignment_submission",
            "attendance", "learning_activity", "scholarship", "academic_warning",
        },
        "columns": {
            "college": "id", "major": "college_id", "student": "college_id",
            "teacher": "college_id", "course": "college_id",
        },
        "label": "college_id",
    },
    "teaching_class_id": {
        "tables": {"course_assignment_analytics", "student_task_analytics"},
        "columns": {
            "course_assignment_analytics": "teaching_class_id",
            "student_task_analytics": "teaching_class_id",
        },
        "label": "teaching_class_id",
    },
}


def _enforce_row_scope(stmt: Statement, sql: str, row_scope: dict[str, object]) -> None:
    if not row_scope:
        return
    refs = {name.lower() for name in _table_refs(stmt)}
    aliases = _table_aliases(stmt)
    for scope_key, scope_value in row_scope.items():
        rule = _ROW_SCOPE_RULES.get(scope_key)
        if not rule or not (refs & set(rule["tables"])):
            continue
        value = str(scope_value)
        candidates: list[tuple[str, str]] = []
        for table, column in dict(rule["columns"]).items():
            if table not in refs:
                continue
            qualifiers = {table, *(alias for alias, real in aliases.items() if real == table)}
            candidates.extend((qualifier, column) for qualifier in qualifiers)
            if len(refs) == 1:
                candidates.append(("", column))
        if any(_scope_predicate_present(sql, qualifier, column, value) for qualifier, column in candidates):
            continue
        raise SQLValidationError(f"当前身份查询这些数据时必须限定 {rule['label']} = {value}")


def _scope_predicate_present(sql: str, qualifier: str, column: str, value: str) -> bool:
    col = rf"{re.escape(qualifier)}\s*\.\s*{re.escape(column)}" if qualifier else rf"(?<!\.)\b{re.escape(column)}"
    literal = re.escape(value)
    return bool(
        re.search(rf"\b{col}\b\s*=\s*{literal}\b", sql, re.IGNORECASE)
        or re.search(rf"\b{literal}\b\s*=\s*{col}\b", sql, re.IGNORECASE)
    )


def _blocked_output_column_hit(stmt: Statement, blocked_columns: set[str]) -> str | None:
    if not blocked_columns:
        return None
    aliases = _table_aliases(stmt)
    select_text = " ".join(_select_output_tokens(stmt)).lower()
    if not select_text:
        return None
    for full in sorted(blocked_columns):
        if "." not in full:
            continue
        table, column = full.split(".", 1)
        table_l = table.lower()
        column_l = column.lower()
        alias_names = {a for a, t in aliases.items() if t == table_l}
        if _selects_star_for_table(select_text, table_l, alias_names, aliases):
            return full
        patterns = [
            rf"\b{re.escape(table_l)}\s*\.\s*{re.escape(column_l)}\b",
        ]
        patterns.extend(rf"\b{re.escape(alias)}\s*\.\s*{re.escape(column_l)}\b" for alias in alias_names)
        if column_l not in {"id", "name"}:
            patterns.append(rf"(?<!\.)\b{re.escape(column_l)}\b")
        if any(re.search(pattern, select_text) for pattern in patterns):
            return full
    return None


def _select_output_tokens(stmt: Statement) -> list[str]:
    tokens = _meaningful(stmt)
    out: list[str] = []
    in_select = False
    for tok in tokens:
        norm = tok.normalized.upper() if hasattr(tok, "normalized") else ""
        if tok.ttype is DML and norm == "SELECT":
            in_select = True
            continue
        if in_select and norm == "FROM":
            break
        if in_select:
            out.append(str(tok.value))
    return out


def _selects_star_for_table(select_text: str, table: str, aliases: set[str], alias_map: dict[str, str]) -> bool:
    if re.search(r"(^|,)\s*\*\s*(,|$)", select_text):
        return table in set(alias_map.values())
    names = {table, *aliases}
    return any(re.search(rf"\b{re.escape(name)}\s*\.\s*\*", select_text) for name in names)


def _table_aliases(stmt: Statement) -> dict[str, str]:
    aliases: dict[str, str] = {}
    tokens = _meaningful(stmt)
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        norm = tok.normalized.upper() if hasattr(tok, "normalized") else ""
        if norm == "FROM" or norm == "JOIN" or norm.endswith(" JOIN"):
            if i + 1 < len(tokens):
                _collect_identifier_aliases(tokens[i + 1], aliases)
            i += 2
            continue
        if isinstance(tok, Parenthesis) and _contains_select(tok):
            aliases.update(_table_aliases(tok))
        elif isinstance(tok, TokenList) and not isinstance(tok, Identifier):
            aliases.update(_table_aliases(tok))
        i += 1
    return aliases


def _collect_identifier_aliases(token, aliases: dict[str, str]) -> None:
    if isinstance(token, IdentifierList):
        for ident in token.get_identifiers():
            _collect_identifier_aliases(ident, aliases)
        return
    if isinstance(token, Identifier):
        if _contains_select(token):
            aliases.update(_table_aliases(token))
            return
        real = _clean_name(token.get_real_name())
        alias = _clean_name(token.get_alias())
        if real:
            aliases[real.lower()] = real.lower()
            if alias:
                aliases[alias.lower()] = real.lower()
        return
    if token.ttype is Name:
        name = _clean_name(token.value)
        if name:
            aliases[name.lower()] = name.lower()


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
        if norm == "FROM" or norm == "JOIN" or norm.endswith(" JOIN"):
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
