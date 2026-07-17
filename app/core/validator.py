"""SQL 安全校验:只允许单条 SELECT,禁危险关键字,强制 LIMIT。"""
from __future__ import annotations

import re

import sqlparse
from sqlparse.sql import Identifier, IdentifierList, Parenthesis, Statement, TokenList, Where
from sqlparse.tokens import Comment, DML, Keyword, Literal, Name

from app.core.config import settings

# 任何出现这些关键字的 SQL 都直接拒绝(即使在子查询里)
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "REPLACE", "ATTACH", "DETACH", "PRAGMA",
    "VACUUM", "REINDEX", "GRANT", "REVOKE",
}
FORBIDDEN_FUNCTIONS = {
    "LOAD_EXTENSION", "READFILE", "WRITEFILE", "PG_READ_FILE", "PG_READ_BINARY_FILE",
    "PG_LS_DIR", "LO_IMPORT", "LO_EXPORT", "DBLINK", "DBLINK_EXEC",
    "LOAD_FILE", "SLEEP", "BENCHMARK",
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

    # 注释既可能让追加的 LIMIT 失效，也能伪造行范围条件；问数 SQL 不接受注释。
    if any(tok.ttype in Comment for tok in stmt.flatten()):
        raise SQLValidationError("SQL 不允许包含注释")

    # 1) 顶层 DML 必须是 SELECT
    first_dml = next((t for t in stmt.flatten() if t.ttype is DML), None)
    if first_dml is None or first_dml.normalized.upper() != "SELECT":
        raise SQLValidationError("仅允许 SELECT 查询")

    # 2) 任何位置不得出现禁用关键字
    for tok in stmt.flatten():
        if tok.ttype in (DML, Keyword, Keyword.DDL, Keyword.DML):
            if tok.normalized.upper() in FORBIDDEN_KEYWORDS:
                raise SQLValidationError(f"包含禁用关键字: {tok.normalized}")
    security_text = _security_text(stmt)
    for function_name in FORBIDDEN_FUNCTIONS:
        if re.search(rf"\b{re.escape(function_name)}\s*\(", security_text, re.IGNORECASE):
            raise SQLValidationError(f"包含禁用函数: {function_name}")
    if re.search(r"\bINTO\s+(?:OUTFILE|DUMPFILE)\b", security_text, re.IGNORECASE):
        raise SQLValidationError("包含禁用的文件输出语法")

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
            "student", "course", "teaching_class", "enrollment", "score", "evaluation", "assignment", "assignment_submission",
            "attendance", "learning_activity", "scholarship", "academic_warning",
            "academic_teaching_operations_summary", "college_teacher_workload_summary", "college_quality_summary",
            "student_task_analytics",
        },
        "columns": {
            "student": "id",
            "enrollment": "student_id",
            "evaluation": "student_id",
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
        "tables": {"teacher", "course", "teaching_class", "enrollment", "score", "evaluation", "assignment", "assignment_submission", "attendance", "learning_activity", "course_assignment_analytics", "student_task_analytics"},
        "columns": {"teacher": "id", "teaching_class": "teacher_id", "course_assignment_analytics": "teacher_id", "student_task_analytics": "teacher_id"},
        "label": "teacher_id",
    },
    "college_id": {
        "tables": {
            "college", "major", "class_group", "student", "teacher", "course", "teaching_class",
            "enrollment", "score", "evaluation", "assignment", "assignment_submission",
            "attendance", "learning_activity", "scholarship", "academic_warning",
            "academic_teaching_operations_summary", "college_teacher_workload_summary", "college_quality_summary",
        },
        "columns": {
            "college": "id", "major": "college_id", "student": "college_id",
            "teacher": "college_id", "course": "college_id",
            "academic_teaching_operations_summary": "college_id",
            "college_teacher_workload_summary": "college_id", "college_quality_summary": "college_id",
        },
        "label": "college_id",
    },
    "counselor_id": {
        "tables": {
            "student", "academic_warning", "attendance", "assignment", "assignment_submission",
            "support_case", "support_request", "counselor_class_group",
        },
        "columns": {
            "support_case": "counselor_id", "support_request": "counselor_id",
            "counselor_class_group": "counselor_id",
        },
        "label": "counselor_id",
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
    flat_keywords = {
        tok.normalized.upper() for tok in stmt.flatten()
        if tok.ttype in Keyword
    }
    if "OR" in flat_keywords:
        raise SQLValidationError("带数据范围的问数暂不允许使用 OR 条件")
    if flat_keywords & {"UNION", "UNION ALL", "INTERSECT", "EXCEPT"}:
        raise SQLValidationError("带数据范围的问数不允许使用集合查询")
    for scope_key, scope_value in row_scope.items():
        # 辅导员必须按所带行政班/个案负责人限制；学院范围只是其组织归属，不能替代班级范围。
        if scope_key == "college_id" and row_scope.get("counselor_id") is not None:
            continue
        rule = _ROW_SCOPE_RULES.get(scope_key)
        if not rule:
            continue
        for block in _query_blocks(stmt):
            refs = {name.lower() for name in _direct_table_refs(block)}
            if not (refs & set(rule["tables"])):
                continue
            aliases = _direct_table_aliases(block)
            value = str(scope_value)
            candidates: list[tuple[str, str]] = []
            for table, column in dict(rule["columns"]).items():
                if table not in refs:
                    continue
                qualifiers = {table, *(alias for alias, real in aliases.items() if real == table)}
                candidates.extend((qualifier, column) for qualifier in qualifiers)
                if len(refs) == 1:
                    candidates.append(("", column))
            where = next((tok for tok in block.tokens if isinstance(tok, Where)), None)
            where_text = _security_text(where, remove_subqueries=True) if where is not None else ""
            if candidates and any(_scope_predicate_present(where_text, qualifier, column, value) for qualifier, column in candidates):
                continue
            raise SQLValidationError(f"当前身份查询这些数据时必须限定 {rule['label']} = {value}（每个查询块均需落实）")


def _scope_predicate_present(sql: str, qualifier: str, column: str, value: str) -> bool:
    quoted_column = rf"[`\"\[]?{re.escape(column)}[`\"\]]?"
    quoted_qualifier = rf"[`\"\[]?{re.escape(qualifier)}[`\"\]]?"
    col = rf"{quoted_qualifier}\s*\.\s*{quoted_column}" if qualifier else rf"(?<!\.){quoted_column}"
    literal = re.escape(value)
    direct = re.compile(rf"^\s*{col}\s*=\s*{literal}\s*$", re.IGNORECASE)
    reverse = re.compile(rf"^\s*{literal}\s*=\s*{col}\s*$", re.IGNORECASE)
    return any(direct.match(part) or reverse.match(part) for part in _top_level_conjuncts(sql))


def _top_level_conjuncts(where_text: str) -> list[str]:
    text = re.sub(r"^\s*WHERE\b", "", where_text, flags=re.IGNORECASE).strip()

    def strip_outer(value: str) -> str:
        value = value.strip()
        while value.startswith("(") and value.endswith(")"):
            depth = 0
            encloses_all = True
            for index, char in enumerate(value):
                if char == "(": depth += 1
                elif char == ")": depth -= 1
                if depth == 0 and index < len(value) - 1:
                    encloses_all = False
                    break
            if not encloses_all:
                break
            value = value[1:-1].strip()
        return value

    def split(value: str) -> list[str]:
        value = strip_outer(value)
        depth = 0
        start = 0
        parts: list[str] = []
        for match in re.finditer(r"[()]|\bAND\b", value, flags=re.IGNORECASE):
            token = match.group(0).upper()
            if token == "(": depth += 1
            elif token == ")": depth = max(0, depth - 1)
            elif depth == 0:
                parts.append(value[start:match.start()].strip())
                start = match.end()
        if parts:
            parts.append(value[start:].strip())
            flattened: list[str] = []
            for part in parts:
                flattened.extend(split(part))
            return flattened
        return [strip_outer(value)] if value else []

    return split(text)


def _security_text(token_list: TokenList | None, *, remove_subqueries: bool = False) -> str:
    if token_list is None:
        return ""
    parts: list[str] = []
    for tok in token_list.tokens:
        if tok.ttype in Comment or tok.ttype in Literal.String:
            parts.append(" ")
        elif remove_subqueries and isinstance(tok, Parenthesis) and _contains_select(tok):
            parts.append(" ")
        elif isinstance(tok, TokenList):
            parts.append(_security_text(tok, remove_subqueries=remove_subqueries))
        else:
            parts.append(str(tok.value))
    return " ".join(parts)


def _query_blocks(stmt: Statement) -> list[TokenList]:
    blocks: list[TokenList] = [stmt]
    def visit(token_list: TokenList) -> None:
        for tok in token_list.tokens:
            if isinstance(tok, Parenthesis) and _contains_select(tok):
                blocks.append(tok)
                visit(tok)
            elif isinstance(tok, TokenList):
                visit(tok)
    visit(stmt)
    return blocks


def _direct_table_refs(token_list: TokenList) -> set[str]:
    refs: set[str] = set()
    tokens = _meaningful(token_list)
    for index, tok in enumerate(tokens):
        norm = tok.normalized.upper() if hasattr(tok, "normalized") else ""
        if (norm == "FROM" or norm == "JOIN" or norm.endswith(" JOIN")) and index + 1 < len(tokens):
            refs |= _direct_identifier_names(tokens[index + 1])
    return refs


def _direct_identifier_names(token) -> set[str]:
    if isinstance(token, IdentifierList):
        names: set[str] = set()
        for ident in token.get_identifiers():
            names |= _direct_identifier_names(ident)
        return names
    if isinstance(token, Identifier):
        if _contains_select(token):
            return set()
        real = _clean_name(token.get_real_name())
        return {real} if real else set()
    if token.ttype is Name:
        name = _clean_name(token.value)
        return {name} if name else set()
    return set()


def _direct_table_aliases(token_list: TokenList) -> dict[str, str]:
    aliases: dict[str, str] = {}
    tokens = _meaningful(token_list)
    for index, tok in enumerate(tokens):
        norm = tok.normalized.upper() if hasattr(tok, "normalized") else ""
        if (norm == "FROM" or norm == "JOIN" or norm.endswith(" JOIN")) and index + 1 < len(tokens):
            _collect_identifier_aliases(tokens[index + 1], aliases)
    return aliases


def _blocked_output_column_hit(stmt: Statement, blocked_columns: set[str]) -> str | None:
    if not blocked_columns:
        return None
    for block in _query_blocks(stmt):
        aliases = _direct_table_aliases(block)
        direct_refs = {name.lower() for name in _direct_table_refs(block)}
        select_text = " ".join(_select_output_tokens(block)).lower()
        if not select_text:
            continue
        for full in sorted(blocked_columns):
            if "." not in full:
                continue
            table, column = full.split(".", 1)
            table_l = table.lower()
            column_l = column.lower()
            alias_names = {a for a, t in aliases.items() if t == table_l}
            if _selects_star_for_table(select_text, table_l, alias_names, aliases):
                return full
            quoted_column = rf"[`\"\[]?{re.escape(column_l)}[`\"\]]?"
            patterns = [
                rf"[`\"\[]?{re.escape(table_l)}[`\"\]]?\s*\.\s*{quoted_column}",
            ]
            patterns.extend(rf"[`\"\[]?{re.escape(alias)}[`\"\]]?\s*\.\s*{quoted_column}" for alias in alias_names)
            if table_l in direct_refs or column_l not in {"id", "name"}:
                patterns.append(rf"(?<![\w.]){quoted_column}(?!\w)")
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
    return any(re.search(rf"[`\"\[]?{re.escape(name)}[`\"\]]?\s*\.\s*\*", select_text) for name in names)


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
