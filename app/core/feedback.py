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
from app.core.file_store import atomic_write_text, lock_for

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
    path = _path(source)
    with lock_for(path):
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def upsert_turn_feedback(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Keep one feedback item per assistant turn and work identity."""
    source = str(payload.get("source") or "unknown")
    turn_id = int(payload["turn_id"])
    submitted_user_id = int(payload["submitted_user_id"])
    role_binding_id = int(payload["role_binding_id"])
    now = datetime.now(timezone.utc).isoformat()
    path = _path(source)
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

    with lock_for(path):
        items = _read_path(path)
        existing = next(
            (
                item
                for item in items
                if int(item.get("turn_id") or 0) == turn_id
                and int(item.get("submitted_user_id") or 0) == submitted_user_id
                and int(item.get("role_binding_id") or 0) == role_binding_id
            ),
            None,
        )
        created = existing is None
        if existing is None:
            existing = {
                "id": uuid4().hex,
                "created_at": now,
            }
            items.append(existing)
        existing.update(
            {
                "source": source,
                "source_label": payload.get("source_label") or source,
                "kind": payload.get("kind") or "incorrect",
                "reason": payload.get("reason") or "",
                "category": payload.get("category") or "",
                "question": payload.get("question") or "",
                "sql": payload.get("sql") or "",
                "explanation": payload.get("explanation") or {},
                "turn_id": turn_id,
                "submitted_user_id": submitted_user_id,
                "role_binding_id": role_binding_id,
                "updated_at": now,
                "status": "open",
            }
        )
        atomic_write_text(
            path,
            ("\n".join(json.dumps(item, ensure_ascii=False) for item in items) + "\n")
            if items
            else "",
        )
    return existing, created


def delete_turn_feedback(
    source: str,
    *,
    turn_id: int,
    submitted_user_id: int,
    role_binding_id: int,
) -> dict[str, Any]:
    """Delete feedback only when it belongs to the given assistant identity."""
    path = _path(source)
    with lock_for(path):
        items = _read_path(path)
        deleted = next(
            (
                item
                for item in items
                if int(item.get("turn_id") or 0) == turn_id
                and int(item.get("submitted_user_id") or 0) == submitted_user_id
                and int(item.get("role_binding_id") or 0) == role_binding_id
            ),
            None,
        )
        if deleted is None:
            raise FileNotFoundError(turn_id)
        kept = [item for item in items if item is not deleted]
        atomic_write_text(
            path,
            ("\n".join(json.dumps(item, ensure_ascii=False) for item in kept) + "\n")
            if kept
            else "",
        )
    return deleted


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


def _read_path(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            items.append(obj)
    return items


def update_feedback(item_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Update one feedback item in-place across the file-backed store."""
    if not FEEDBACK_DIR.exists():
        raise FileNotFoundError(item_id)

    allowed = {
        "status",
        "assignee",
        "priority",
        "resolution",
        "resolution_action",
        "updated_at",
        "closed_at",
    }
    clean_patch = {k: v for k, v in patch.items() if k in allowed}

    for path in sorted(FEEDBACK_DIR.glob("*.jsonl")):
        changed = False
        found: dict[str, Any] | None = None
        lines: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                lines.append(line)
                continue
            if isinstance(obj, dict) and obj.get("id") == item_id:
                obj.update(clean_patch)
                found = obj
                changed = True
            lines.append(json.dumps(obj, ensure_ascii=False) if isinstance(obj, dict) else line)
        if changed and found is not None:
            atomic_write_text(path, "\n".join(lines) + "\n")
            return found

    raise FileNotFoundError(item_id)


def delete_feedback(item_id: str) -> dict[str, Any]:
    if not FEEDBACK_DIR.exists():
        raise FileNotFoundError(item_id)

    for path in sorted(FEEDBACK_DIR.glob("*.jsonl")):
        changed = False
        deleted: dict[str, Any] | None = None
        lines: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                lines.append(line)
                continue
            if isinstance(obj, dict) and obj.get("id") == item_id:
                deleted = obj
                changed = True
                continue
            lines.append(json.dumps(obj, ensure_ascii=False) if isinstance(obj, dict) else line)
        if changed and deleted is not None:
            atomic_write_text(path, ("\n".join(lines) + "\n") if lines else "")
            return deleted

    raise FileNotFoundError(item_id)
