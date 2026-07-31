"""Persistent standard question / few-shot examples."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import ROOT_DIR
from app.core.file_store import atomic_write_text
from app.core.validator import SQLValidationError, validate_and_fix

EXAMPLE_DIR = ROOT_DIR / "data" / "examples"


def _path(source: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in source or "unknown")
    return EXAMPLE_DIR / f"{safe}.json"


def _read(source: str) -> list[dict[str, Any]]:
    path = _path(source)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _write(source: str, items: list[dict[str, Any]]) -> None:
    atomic_write_text(_path(source), json.dumps(items, ensure_ascii=False, indent=2))


def list_examples(source: str, limit: int = 200) -> list[dict[str, Any]]:
    items = _read(source)
    items.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
    return items[: max(1, min(limit, 500))]


def select_few_shot_examples(
    source: str,
    question: str,
    *,
    allowed_tables: set[str] | frozenset[str],
    blocked_columns: set[str] | frozenset[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Select a small, authorized set of enabled examples for one question."""
    ranked: list[tuple[float, dict[str, Any]]] = []
    table_map = {table: [] for table in allowed_tables}
    if not table_map:
        return []
    for item in list_examples(source, limit=500):
        if item.get("enabled") is False:
            continue
        item_question = str(item.get("question") or "").strip()
        sql = str(item.get("sql") or "").strip()
        if not item_question or not sql:
            continue
        score = _similarity(question, item_question)
        if score <= 0:
            continue
        try:
            validate_and_fix(
                sql,
                table_map,
                set(blocked_columns or ()),
            )
        except SQLValidationError:
            continue
        ranked.append((score, item))
    ranked.sort(
        key=lambda pair: (
            pair[0],
            str(pair[1].get("updated_at") or pair[1].get("created_at") or ""),
        ),
        reverse=True,
    )
    return [item for _, item in ranked[: max(1, min(limit, 8))]]


def _similarity(left: str, right: str) -> float:
    left_tokens = _text_tokens(left)
    right_tokens = _text_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    hits = len(left_tokens.intersection(right_tokens))
    return hits / math.sqrt(len(left_tokens) * len(right_tokens))


def _text_tokens(value: str) -> set[str]:
    text = str(value or "").lower()
    tokens = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text))
    tokens.update(
        gram
        for index in range(max(0, len(text) - 1))
        if re.fullmatch(r"[\u4e00-\u9fff]{2}", gram := text[index : index + 2])
    )
    return tokens


def upsert_example(source: str, payload: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    items = _read(source)
    item_id = str(payload.get("id") or uuid4().hex)
    item = {
        "id": item_id,
        "source": source,
        "source_label": payload.get("source_label") or source,
        "question": payload.get("question") or "",
        "sql": payload.get("sql") or "",
        "tags": payload.get("tags") or [],
        "enabled": bool(payload.get("enabled", True)),
        "created_at": payload.get("created_at") or now,
        "updated_at": now,
    }
    next_items = [item if x.get("id") == item_id else x for x in items]
    if not any(x.get("id") == item_id for x in items):
        next_items.insert(0, item)
    _write(source, next_items[:500])
    return item


def delete_example(source: str, item_id: str) -> None:
    _write(source, [x for x in _read(source) if x.get("id") != item_id])


def delete_matching_examples(source: str, question: str, sql: str) -> int:
    question = (question or "").strip()
    sql = (sql or "").strip()
    if not question and not sql:
        return 0
    items = _read(source)
    kept: list[dict[str, Any]] = []
    deleted = 0
    for item in items:
        same_question = question and str(item.get("question") or "").strip() == question
        same_sql = sql and str(item.get("sql") or "").strip() == sql
        if same_question and same_sql:
            deleted += 1
            continue
        kept.append(item)
    if deleted:
        _write(source, kept)
    return deleted
