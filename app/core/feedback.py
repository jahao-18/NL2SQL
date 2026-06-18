"""Persistent query feedback.

This is intentionally file-backed for the current local product stage. It gives
the UI a real governance queue without introducing a database migration.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import ROOT_DIR

FEEDBACK_DIR = ROOT_DIR / "data" / "feedback"


def _path(source: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in source or "unknown")
    return FEEDBACK_DIR / f"{safe}.jsonl"


def add_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    source = str(payload.get("source") or "unknown")
    item = {
        "id": uuid4().hex,
        "source": source,
        "source_label": payload.get("source_label") or source,
        "kind": payload.get("kind") or "incorrect",
        "reason": payload.get("reason") or "",
        "category": payload.get("category") or "",
        "question": payload.get("question") or "",
        "sql": payload.get("sql") or "",
        "explanation": payload.get("explanation") or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "open",
    }
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    with _path(source).open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def list_feedback(source: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    paths = [_path(source)] if source else sorted(FEEDBACK_DIR.glob("*.jsonl")) if FEEDBACK_DIR.exists() else []
    items: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                items.append(obj)
    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return items[: max(1, min(limit, 500))]
