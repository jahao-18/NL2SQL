"""Lightweight governance workflow for feedback review and settings."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import yaml

from app.core.config import ROOT_DIR
from app.core.examples import delete_matching_examples, upsert_example
from app.core.file_store import atomic_write_text, lock_for
from app.core.schema_profile import load_profile_dict, publish_profile, save_profile_dict

SETTINGS_PATH = ROOT_DIR / "data" / "governance" / "settings.yaml"
REVIEW_ITEMS_PATH = ROOT_DIR / "data" / "governance" / "review_items.jsonl"

DEFAULT_SETTINGS: dict[str, Any] = {
    "review_required_for_publish": False,
    "auto_queue_error_feedback": True,
    "low_confidence_threshold": 70,
    "require_publish_note": True,
    "default_status_filter": "open",
    "page_size": 50,
}

VALID_STATUSES = {"open", "in_progress", "accepted", "rejected", "closed"}
VALID_TYPES = {"feedback_fix", "example_candidate", "profile_publish", "relation_change", "metric_change", "field_change"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return dict(DEFAULT_SETTINGS)
    raw = yaml.safe_load(SETTINGS_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return dict(DEFAULT_SETTINGS)
    settings = dict(DEFAULT_SETTINGS)
    for key in settings:
        if key in raw:
            settings[key] = raw[key]
    settings["low_confidence_threshold"] = max(0, min(100, int(settings["low_confidence_threshold"] or 0)))
    settings["page_size"] = max(10, min(200, int(settings["page_size"] or 50)))
    if settings["default_status_filter"] not in VALID_STATUSES and settings["default_status_filter"] != "all":
        settings["default_status_filter"] = "open"
    return settings


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    for key in DEFAULT_SETTINGS:
        if key in payload:
            settings[key] = payload[key]
    settings["low_confidence_threshold"] = max(0, min(100, int(settings["low_confidence_threshold"] or 0)))
    settings["page_size"] = max(10, min(200, int(settings["page_size"] or 50)))
    atomic_write_text(SETTINGS_PATH, yaml.safe_dump(settings, allow_unicode=True, sort_keys=False))
    return settings


def _read_review_items() -> list[dict[str, Any]]:
    if not REVIEW_ITEMS_PATH.exists():
        return []
    items: list[dict[str, Any]] = []
    for line in REVIEW_ITEMS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            items.append(loaded)
    return items


def _write_review_items(items: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
    atomic_write_text(REVIEW_ITEMS_PATH, text)


def create_review_item(
    item_type: str,
    source: str,
    title: str,
    payload: dict[str, Any] | None = None,
    *,
    source_label: str = "",
    reason: str = "",
    category: str = "",
    priority: str = "normal",
) -> dict[str, Any]:
    if item_type not in VALID_TYPES:
        raise ValueError(f"invalid review item type: {item_type}")
    now = now_iso()
    item = {
        "id": uuid4().hex,
        "type": item_type,
        "kind": _kind_from_type(item_type),
        "source": source or "unknown",
        "source_label": source_label or source or "unknown",
        "title": title,
        "question": title,
        "reason": reason,
        "category": category,
        "payload": payload or {},
        "explanation": payload or {},
        "status": "open",
        "priority": priority,
        "created_at": now,
        "updated_at": now,
        "reviewed_at": "",
        "reviewer": "",
        "resolution": "",
        "resolution_action": "",
        "result": {},
    }
    with lock_for(REVIEW_ITEMS_PATH):
        items = _read_review_items()
        items.insert(0, item)
        _write_review_items(items[:1000])
    return item


def create_feedback_review(feedback_item: dict[str, Any]) -> dict[str, Any] | None:
    settings = load_settings()
    kind = feedback_item.get("kind")
    if kind == "incorrect" and not settings.get("auto_queue_error_feedback", True):
        return None
    if kind not in {"incorrect", "correct"}:
        return None
    item_type = "example_candidate" if kind == "correct" else "feedback_fix"
    reason = str(feedback_item.get("reason") or "")
    category = str(feedback_item.get("category") or kind or "")
    if kind == "correct":
        reason = reason or "用户确认结果正确，建议沉淀为标准问法样例"
        category = category or "confirmed_example"
    return create_review_item(
        item_type,
        source=str(feedback_item.get("source") or "unknown"),
        source_label=str(feedback_item.get("source_label") or feedback_item.get("source") or "unknown"),
        title=str(feedback_item.get("question") or "用户反馈"),
        reason=reason,
        category=category,
        payload={"feedback": feedback_item},
        priority="normal" if kind == "correct" else "high",
    )


def _kind_from_type(item_type: str) -> str:
    return {
        "feedback_fix": "feedback_fix",
        "example_candidate": "correct_example",
        "profile_publish": "publish_request",
        "relation_change": "relation_change",
        "metric_change": "metric_change",
        "field_change": "field_change",
    }.get(item_type, item_type)


def delete_review_items_for_feedback(feedback_id: str) -> int:
    deleted = 0
    with lock_for(REVIEW_ITEMS_PATH):
        items = _read_review_items()
        kept = []
        for item in items:
            feedback = (item.get("payload") or {}).get("feedback") or {}
            if feedback.get("id") == feedback_id:
                deleted += 1
                continue
            kept.append(item)
        if deleted:
            _write_review_items(kept)
    return deleted


def list_review_items(
    source: str | None = None,
    status: str | None = None,
    kind: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    items = _read_review_items()
    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    if source:
        items = [item for item in items if item.get("source") == source]
    if status and status != "all":
        items = [item for item in items if (item.get("status") or "open") == status]
    if kind and kind != "all":
        items = [item for item in items if item.get("kind") == kind or item.get("type") == kind]
    return items[: max(1, min(limit, 500))]


def create_publish_review(source: str, label: str = "", description: str = "") -> dict[str, Any]:
    profile = load_profile_dict(source)
    return create_review_item(
        "profile_publish",
        source=source,
        source_label=source,
        title=f"发布 Profile: {label.strip() or '发布版本'}",
        reason=description,
        category="profile_publish",
        payload={
            "label": label.strip(),
            "description": description.strip(),
            "profile": profile,
            "profile_meta": profile.get("_meta") or {},
            "table_count": len(profile.get("tables") or {}),
            "relation_count": len(profile.get("relations") or []),
            "metric_count": len(profile.get("metrics") or {}),
        },
    )


def create_low_confidence_review(payload: dict[str, Any]) -> dict[str, Any] | None:
    settings = load_settings()
    confidence = payload.get("confidence")
    try:
        score = int(confidence)
    except (TypeError, ValueError):
        return None
    if score >= int(settings.get("low_confidence_threshold") or 70):
        return None
    source = str(payload.get("source") or "unknown")
    question = str(payload.get("question") or "低可信度查询")
    return create_review_item(
        "feedback_fix",
        source=source,
        source_label=str(payload.get("source_label") or source),
        title=question,
        reason=f"可信度 {score} 低于阈值 {settings.get('low_confidence_threshold')}",
        category="low_confidence",
        priority="high",
        payload={"feedback": {**payload, "kind": "incorrect", "category": "low_confidence"}},
    )


def patch_review_item(item_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    status = patch.get("status")
    clean: dict[str, Any] = {}
    if status:
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {status}")
        clean["status"] = status
        if status in {"accepted", "rejected", "closed"}:
            clean["closed_at"] = now_iso()
    for key in ("assignee", "priority", "resolution"):
        if key in patch:
            clean[key] = str(patch.get(key) or "").strip()
    clean["updated_at"] = now_iso()
    return _update_review_item(item_id, clean)


def _update_review_item(item_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    with lock_for(REVIEW_ITEMS_PATH):
        items = _read_review_items()
        for item in items:
            if item.get("id") == item_id:
                item.update(patch)
                _write_review_items(items)
                return item
    raise FileNotFoundError(item_id)


def _find_item(item_id: str) -> dict[str, Any]:
    for item in _read_review_items():
        if item.get("id") == item_id:
            return item
    raise FileNotFoundError(item_id)


def accept_review_item(item_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    item = _find_item(item_id)
    payload = payload or {}
    source = str(payload.get("source") or item.get("source") or "")
    if not source:
        raise ValueError("source is required")

    result: dict[str, Any]
    if action == "example":
        feedback = (item.get("payload") or {}).get("feedback") or {}
        result = upsert_example(source, {
            "id": payload.get("id") or item_id,
            "question": payload.get("question") or feedback.get("question") or item.get("question") or "",
            "sql": payload.get("sql") or feedback.get("sql") or item.get("sql") or "",
            "source_label": payload.get("source_label") or feedback.get("source_label") or item.get("source_label") or source,
            "tags": payload.get("tags") or ["governance", item.get("category") or item.get("kind") or "feedback"],
            "enabled": payload.get("enabled", True),
        })
    elif action == "relation":
        result = _accept_relation(source, payload)
    elif action == "metric":
        result = _accept_metric(source, payload)
    elif action == "field_profile":
        result = _accept_field_profile(source, payload)
    elif action == "publish_profile":
        profile_snapshot = (item.get("payload") or {}).get("profile")
        if isinstance(profile_snapshot, dict):
            save_profile_dict(source, profile_snapshot)
        result = publish_profile(
            source,
            label=str(payload.get("label") or (item.get("payload") or {}).get("label") or item.get("question") or "").replace("发布 Profile:", "").strip(),
            description=str(payload.get("description") or (item.get("payload") or {}).get("description") or item.get("reason") or "").strip(),
        )
    else:
        raise ValueError(f"unsupported action: {action}")

    updated = _update_review_item(item_id, {
        "status": "accepted",
        "resolution_action": action,
        "resolution": str(payload.get("resolution") or f"accepted as {action}"),
        "updated_at": now_iso(),
        "closed_at": now_iso(),
        "reviewed_at": now_iso(),
        "result": result,
    })
    return {"item": updated, "action": action, "result": result}


def reject_review_item(item_id: str, reason: str = "") -> dict[str, Any]:
    item = _find_item(item_id)
    deleted_examples = 0
    if item.get("kind") == "correct_example" or item.get("type") == "example_candidate":
        feedback = (item.get("payload") or {}).get("feedback") or {}
        deleted_examples = delete_matching_examples(
            str(item.get("source") or ""),
            str(feedback.get("question") or item.get("question") or ""),
            str(feedback.get("sql") or item.get("sql") or ""),
        )
    return _update_review_item(item_id, {
        "status": "rejected",
        "resolution": (reason.strip() or "rejected") + (f"；已清理误沉淀样例 {deleted_examples} 条" if deleted_examples else ""),
        "updated_at": now_iso(),
        "closed_at": now_iso(),
        "reviewed_at": now_iso(),
    })


def _accept_relation(source: str, payload: dict[str, Any]) -> dict[str, Any]:
    left = str(payload.get("left") or "").strip()
    right = str(payload.get("right") or "").strip()
    if not left or not right:
        text = str(payload.get("relation") or "").strip()
        if "=" not in text:
            raise ValueError("relation must look like orders.user_id = users.id")
        left, right = [part.strip() for part in text.split("=", 1)]
    if "." not in left or "." not in right:
        raise ValueError("relation endpoints must use table.column")
    profile = load_profile_dict(source)
    profile["relations"] = profile.get("relations") or []
    exists = any(rel.get("left") == left and rel.get("right") == right for rel in profile["relations"])
    if not exists:
        profile["relations"].insert(0, {
            "left": left,
            "right": right,
            "type": payload.get("type") or "manual",
            "description": payload.get("description") or "",
            "recommended": payload.get("recommended", True),
        })
    return save_profile_dict(source, profile)


def _accept_metric(source: str, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    formula = str(payload.get("formula") or "").strip()
    if not name or not formula:
        raise ValueError("metric name and formula are required")
    profile = load_profile_dict(source)
    profile["metrics"] = profile.get("metrics") or {}
    profile["metrics"][name] = {
        "formula": formula,
        "description": payload.get("description") or "",
        "default_filters": payload.get("default_filters") or [],
        "default_time_column": payload.get("default_time_column") or "",
        "grain": payload.get("grain") or "",
        "examples": payload.get("examples") or [],
        "enabled": payload.get("enabled", True),
    }
    return save_profile_dict(source, profile)


def _accept_field_profile(source: str, payload: dict[str, Any]) -> dict[str, Any]:
    table = str(payload.get("table") or "").strip()
    column = str(payload.get("column") or "").strip()
    if not table or not column:
        raise ValueError("table and column are required")
    profile = load_profile_dict(source)
    profile["columns"] = profile.get("columns") or {}
    profile["columns"][table] = profile["columns"].get(table) or {}
    target = profile["columns"][table].get(column) or {}
    for key in (
        "business_name",
        "description",
        "semantic_type",
        "default_aggregation",
        "unit",
        "enum_values",
        "example_values",
        "default_filter",
        "enabled",
        "sensitive",
        "deprecated",
        "notes",
    ):
        if key in payload:
            target[key] = payload[key]
    profile["columns"][table][column] = target
    return save_profile_dict(source, profile)
