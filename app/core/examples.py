"""Persistent standard question / few-shot examples."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import ROOT_DIR

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
    EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    _path(source).write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def list_examples(source: str, limit: int = 200) -> list[dict[str, Any]]:
    items = _read(source)
    items.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
    return items[: max(1, min(limit, 500))]


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
