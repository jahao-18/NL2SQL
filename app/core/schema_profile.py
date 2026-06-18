"""Structured schema profile support.

The database catalog tells us what exists. A schema profile tells the NL2SQL
runtime how the business expects those tables and fields to be used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from app.core.config import ROOT_DIR
from app.core.data_sources import get_source


@dataclass(frozen=True)
class TableProfile:
    name: str
    business_name: str = ""
    description: str = ""
    grain: str = ""
    default_time_column: str = ""
    default_filters: tuple[str, ...] = ()
    enabled: bool = True
    notes: str = ""


@dataclass(frozen=True)
class ColumnProfile:
    table: str
    column: str
    business_name: str = ""
    description: str = ""
    semantic_type: str = ""
    default_aggregation: str = ""
    unit: str = ""
    enum_values: tuple[str, ...] = ()
    example_values: tuple[str, ...] = ()
    default_filter: str = ""
    enabled: bool = True
    sensitive: bool = False
    deprecated: bool = False
    notes: str = ""

    @property
    def key(self) -> str:
        return f"{self.table}.{self.column}"


@dataclass(frozen=True)
class RelationProfile:
    left: str
    right: str
    relation_type: str = ""
    description: str = ""
    recommended: bool = True

    @property
    def parts(self) -> tuple[str, str, str, str] | None:
        if "." not in self.left or "." not in self.right:
            return None
        lt, lc = self.left.split(".", 1)
        rt, rc = self.right.split(".", 1)
        if not lt or not lc or not rt or not rc:
            return None
        return lt, lc, rt, rc


@dataclass(frozen=True)
class MetricProfile:
    name: str
    formula: str
    description: str = ""
    default_filters: tuple[str, ...] = ()
    default_time_column: str = ""
    grain: str = ""
    examples: tuple[str, ...] = ()
    enabled: bool = True


@dataclass(frozen=True)
class SchemaProfile:
    source: str
    tables: dict[str, TableProfile] = field(default_factory=dict)
    columns: dict[str, ColumnProfile] = field(default_factory=dict)
    relations: tuple[RelationProfile, ...] = ()
    metrics: dict[str, MetricProfile] = field(default_factory=dict)

    @property
    def blocked_columns(self) -> set[str]:
        return {
            c.key
            for c in self.columns.values()
            if not c.enabled or c.sensitive or c.deprecated
        }


def _list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(v).strip() for v in value if str(v).strip())
    s = str(value).strip()
    return (s,) if s else ()


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _table(name: str, raw: dict[str, Any]) -> TableProfile:
    return TableProfile(
        name=name,
        business_name=str(raw.get("business_name") or raw.get("alias") or "").strip(),
        description=str(raw.get("description") or "").strip(),
        grain=str(raw.get("grain") or "").strip(),
        default_time_column=str(raw.get("default_time_column") or "").strip(),
        default_filters=_list(raw.get("default_filters")),
        enabled=_bool(raw.get("enabled"), True),
        notes=str(raw.get("notes") or "").strip(),
    )


def _column(table: str, column: str, raw: dict[str, Any]) -> ColumnProfile:
    return ColumnProfile(
        table=table,
        column=column,
        business_name=str(raw.get("business_name") or raw.get("alias") or "").strip(),
        description=str(raw.get("description") or "").strip(),
        semantic_type=str(raw.get("semantic_type") or "").strip(),
        default_aggregation=str(raw.get("default_aggregation") or "").strip(),
        unit=str(raw.get("unit") or "").strip(),
        enum_values=_list(raw.get("enum_values")),
        example_values=_list(raw.get("example_values")),
        default_filter=str(raw.get("default_filter") or "").strip(),
        enabled=_bool(raw.get("enabled"), True),
        sensitive=_bool(raw.get("sensitive"), False),
        deprecated=_bool(raw.get("deprecated"), False),
        notes=str(raw.get("notes") or "").strip(),
    )


@lru_cache(maxsize=16)
def load_profile(source_name: str | None = None) -> SchemaProfile:
    source = get_source(source_name)
    path = source.schema_profile_path
    if not path or not path.exists():
        return SchemaProfile(source=source.name)

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    tables: dict[str, TableProfile] = {}
    for name, body in (raw.get("tables") or {}).items():
        if isinstance(body, dict):
            tables[str(name)] = _table(str(name), body)

    columns: dict[str, ColumnProfile] = {}
    for table, cols in (raw.get("columns") or {}).items():
        if not isinstance(cols, dict):
            continue
        for column, body in cols.items():
            if isinstance(body, dict):
                item = _column(str(table), str(column), body)
                columns[item.key] = item

    relations: list[RelationProfile] = []
    for item in raw.get("relations") or []:
        if not isinstance(item, dict):
            continue
        rel = RelationProfile(
            left=str(item.get("left") or "").strip(),
            right=str(item.get("right") or "").strip(),
            relation_type=str(item.get("type") or item.get("relation_type") or "").strip(),
            description=str(item.get("description") or "").strip(),
            recommended=_bool(item.get("recommended"), True),
        )
        if rel.parts:
            relations.append(rel)

    metrics: dict[str, MetricProfile] = {}
    for name, body in (raw.get("metrics") or {}).items():
        if not isinstance(body, dict):
            continue
        formula = str(body.get("formula") or "").strip()
        if not formula:
            continue
        metrics[str(name)] = MetricProfile(
            name=str(name),
            formula=formula,
            description=str(body.get("description") or "").strip(),
            default_filters=_list(body.get("default_filters")),
            default_time_column=str(body.get("default_time_column") or "").strip(),
            grain=str(body.get("grain") or "").strip(),
            examples=_list(body.get("examples")),
            enabled=_bool(body.get("enabled"), True),
        )

    return SchemaProfile(
        source=source.name,
        tables=tables,
        columns=columns,
        relations=tuple(relations),
        metrics=metrics,
    )


def profile_context(source_name: str, selected_tables: list[str] | None = None) -> str:
    """Render profile guidance for the LLM."""
    profile = load_profile(source_name)
    selected = set(selected_tables or [])

    table_lines: list[str] = []
    for name, item in profile.tables.items():
        if selected and name not in selected:
            continue
        parts = [name]
        if item.business_name:
            parts.append(item.business_name)
        if item.grain:
            parts.append(f"粒度: {item.grain}")
        if item.default_time_column:
            parts.append(f"默认时间字段: {item.default_time_column}")
        if item.default_filters:
            parts.append("默认过滤: " + " AND ".join(item.default_filters))
        if not item.enabled:
            parts.append("不参与问数")
        if item.description:
            parts.append(item.description)
        if item.notes:
            parts.append(item.notes)
        table_lines.append("- " + "；".join(parts))

    column_lines: list[str] = []
    for key, item in profile.columns.items():
        if selected and item.table not in selected:
            continue
        parts = [key]
        if item.business_name:
            parts.append(item.business_name)
        if item.semantic_type:
            parts.append(f"类型: {item.semantic_type}")
        if item.default_aggregation:
            parts.append(f"默认聚合: {item.default_aggregation}")
        if item.unit:
            parts.append(f"单位: {item.unit}")
        if item.default_filter:
            parts.append(f"默认过滤: {item.default_filter}")
        flags = []
        if not item.enabled:
            flags.append("不要使用")
        if item.sensitive:
            flags.append("敏感字段")
        if item.deprecated:
            flags.append("废弃字段")
        if flags:
            parts.append(" / ".join(flags))
        if item.enum_values:
            parts.append("取值: " + " / ".join(item.enum_values))
        if item.description:
            parts.append(item.description)
        if item.notes:
            parts.append(item.notes)
        column_lines.append("- " + "；".join(parts))

    relation_lines: list[str] = []
    for rel in profile.relations:
        parts = rel.parts
        if not parts:
            continue
        lt, _, rt, _ = parts
        if selected and lt not in selected and rt not in selected:
            continue
        bits = [f"{rel.left} = {rel.right}"]
        if rel.relation_type:
            bits.append(rel.relation_type)
        if rel.description:
            bits.append(rel.description)
        if not rel.recommended:
            bits.append("低优先级")
        relation_lines.append("- " + "；".join(bits))

    metric_lines: list[str] = []
    for metric in profile.metrics.values():
        if not metric.enabled:
            continue
        bits = [f"{metric.name} = {metric.formula}"]
        if metric.default_filters:
            bits.append("默认过滤: " + " AND ".join(metric.default_filters))
        if metric.default_time_column:
            bits.append(f"默认时间字段: {metric.default_time_column}")
        if metric.grain:
            bits.append(f"统计粒度: {metric.grain}")
        if metric.description:
            bits.append(metric.description)
        metric_lines.append("- " + "；".join(bits))

    sections: list[str] = []
    if table_lines:
        sections.append("【表业务画像 / 粒度与默认口径】\n" + "\n".join(table_lines))
    if column_lines:
        sections.append("【字段业务语义 / 可用性】\n" + "\n".join(column_lines))
    if relation_lines:
        sections.append("【人工确认的表关系 / JOIN 规则】\n" + "\n".join(relation_lines))
    if metric_lines:
        sections.append("【结构化业务指标 / 计算口径】\n" + "\n".join(metric_lines))
    return "\n\n".join(sections)


def manual_relations(source_name: str) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    for rel in load_profile(source_name).relations:
        if rel.recommended and rel.parts:
            out.append(rel.parts)
    return out


def clear_cache() -> None:
    load_profile.cache_clear()


def empty_profile_dict() -> dict[str, Any]:
    return {"tables": {}, "columns": {}, "relations": [], "metrics": {}, "_meta": {}}


def profile_path(source_name: str) -> Path:
    source = get_source(source_name)
    if source.schema_profile_path:
        return source.schema_profile_path
    return ROOT_DIR / "data" / "schema_profiles" / f"{source.name}.yaml"


def _version_dir(source_name: str) -> Path:
    return ROOT_DIR / "data" / "schema_profiles" / ".versions" / source_name


def _version_meta_path(source_name: str, version_id: str) -> Path:
    return _version_dir(source_name) / f"{version_id}.meta.yaml"


def _version_yaml_path(source_name: str, version_id: str) -> Path:
    return _version_dir(source_name) / f"{version_id}.yaml"


def _write_version_snapshot(source_name: str, content: str, meta: dict[str, Any] | None = None) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    version_id = f"{stamp}-{uuid4().hex[:8]}"
    vdir = _version_dir(source_name)
    vdir.mkdir(parents=True, exist_ok=True)
    _version_yaml_path(source_name, version_id).write_text(content, encoding="utf-8")
    payload = {
        "id": version_id,
        "label": "",
        "description": "",
        "kind": "auto",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if meta:
        payload.update({k: v for k, v in meta.items() if v is not None})
    _version_meta_path(source_name, version_id).write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return version_id


def load_profile_dict(source_name: str) -> dict[str, Any]:
    path = profile_path(source_name)
    if not path.exists():
        return empty_profile_dict()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return empty_profile_dict()
    out = empty_profile_dict()
    for key in out:
        if key in raw and raw[key] is not None:
            out[key] = raw[key]
    return out


def save_profile_dict(source_name: str, raw: dict[str, Any]) -> dict[str, Any]:
    # Keep the file schema narrow and predictable. The model layer remains
    # permissive, but the persisted artifact should be easy to review.
    payload = empty_profile_dict()
    for key in payload:
        value = raw.get(key) if isinstance(raw, dict) else None
        if value is not None:
            payload[key] = value

    path = profile_path(source_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    clear_cache()
    # Related caches are optional imports to avoid circular imports at module load.
    try:
        from app.core import schema
        schema.clear_cache()
    except Exception:
        pass
    try:
        from app.core.retrieval.pipeline import clear_cache as clear_retrieval_cache
        clear_retrieval_cache()
    except Exception:
        pass
    return payload


def list_profile_versions(source_name: str) -> list[dict[str, Any]]:
    vdir = _version_dir(source_name)
    if not vdir.exists():
        return []
    items = []
    for path in sorted((p for p in vdir.glob("*.yaml") if not p.name.endswith(".meta.yaml")), reverse=True):
        meta_path = _version_meta_path(source_name, path.stem)
        meta = {}
        if meta_path.exists():
            loaded = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                meta = loaded
        items.append({
            "id": path.stem,
            "path": str(path.relative_to(ROOT_DIR)),
            "created_at": path.stem.split("-", 1)[0],
            "size": path.stat().st_size,
            "label": meta.get("label") or "",
            "description": meta.get("description") or "",
            "kind": meta.get("kind") or "auto",
            "updated_at": meta.get("updated_at") or meta.get("created_at") or "",
        })
    return items[:100]


def update_profile_version(source_name: str, version_id: str, label: str = "", description: str = "") -> dict[str, Any]:
    path = _version_yaml_path(source_name, version_id)
    if not path.exists():
        raise FileNotFoundError(version_id)
    meta_path = _version_meta_path(source_name, version_id)
    meta = {}
    if meta_path.exists():
        loaded = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            meta = loaded
    meta.update({
        "id": version_id,
        "label": label.strip(),
        "description": description.strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    if not meta.get("created_at"):
        meta["created_at"] = datetime.now(timezone.utc).isoformat()
    if not meta.get("kind"):
        meta["kind"] = "manual"
    meta_path.write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return next((x for x in list_profile_versions(source_name) if x["id"] == version_id), {"id": version_id, **meta})


def delete_profile_version(source_name: str, version_id: str) -> None:
    path = _version_yaml_path(source_name, version_id)
    if not path.exists():
        raise FileNotFoundError(version_id)
    path.unlink()
    meta_path = _version_meta_path(source_name, version_id)
    if meta_path.exists():
        meta_path.unlink()


def rollback_profile(source_name: str, version_id: str) -> dict[str, Any]:
    path = _version_yaml_path(source_name, version_id)
    if not path.exists():
        raise FileNotFoundError(version_id)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return save_profile_dict(source_name, raw)


def publish_profile(source_name: str, label: str = "", description: str = "") -> dict[str, Any]:
    # Draft saves are not versioned. Publishing stamps the current profile and
    # then records that exact published payload as a rollback snapshot.
    raw = load_profile_dict(source_name)
    meta = raw.setdefault("_meta", {})
    meta["published_at"] = datetime.now(timezone.utc).isoformat()
    meta["published_id"] = uuid4().hex
    version_meta = {
        "kind": "publish",
        "label": label.strip() or "发布版本",
        "description": description.strip(),
        "published_id": meta["published_id"],
        "published_at": meta["published_at"],
    }
    saved = save_profile_dict(source_name, raw)
    _write_version_snapshot(
        source_name,
        yaml.safe_dump(saved, allow_unicode=True, sort_keys=False),
        version_meta,
    )
    return {"published": True, "profile": saved, "published_id": meta["published_id"], "published_at": meta["published_at"]}


def quality_report(source_name: str, tables: dict[str, list[str]]) -> dict[str, Any]:
    profile = load_profile_dict(source_name)
    table_profiles = profile.get("tables") or {}
    column_profiles = profile.get("columns") or {}
    relations = profile.get("relations") or []
    metrics = profile.get("metrics") or {}

    table_names = list(tables)
    field_total = sum(len(cols) for cols in tables.values())
    table_profiled = sum(1 for t in table_names if (table_profiles.get(t) or {}).get("grain"))
    governed_fields = 0
    sensitive_marked = 0
    for table, cols in tables.items():
        prof_cols = column_profiles.get(table) or {}
        for col in cols:
            p = prof_cols.get(col) or {}
            if p.get("business_name") or p.get("description") or p.get("semantic_type"):
                governed_fields += 1
            if p.get("sensitive") or p.get("deprecated") or p.get("enabled") is False:
                sensitive_marked += 1

    def pct(n: int, d: int) -> int:
        return round(n / d * 100) if d else 0

    scores = {
        "table_grain": pct(table_profiled, len(table_names)),
        "field_semantics": pct(governed_fields, field_total),
        "relations": min(100, round(len(relations) / max(1, len(table_names) - 1) * 100)),
        "metrics": min(100, len(metrics) * 20),
        "safety": min(100, 60 + sensitive_marked * 10),
    }
    total = round(
        scores["table_grain"] * 0.25
        + scores["field_semantics"] * 0.30
        + scores["relations"] * 0.20
        + scores["metrics"] * 0.15
        + scores["safety"] * 0.10
    )
    gaps = []
    if scores["table_grain"] < 80:
        gaps.append("补齐核心表的表粒度")
    if scores["field_semantics"] < 70:
        gaps.append("补充字段中文名、描述和语义类型")
    if scores["relations"] < 60:
        gaps.append("补充无外键表的人工 JOIN 关系")
    if scores["metrics"] < 60:
        gaps.append("沉淀高频指标口径")
    return {"score": total, "parts": scores, "gaps": gaps}
