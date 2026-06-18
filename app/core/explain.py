"""Business-readable query explanations and debug traces."""
from __future__ import annotations

import re
from typing import Any

from app.core.schema_profile import load_profile


def _sql_has(sql: str, text: str) -> bool:
    return text.lower() in (sql or "").lower()


def explain_query(
    question: str,
    source: str,
    source_label: str,
    sql: str,
    auto_routed: bool,
    route_reason: str | None,
    retrieval_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = load_profile(source)
    used_filters: list[str] = []
    used_relations: list[str] = []
    used_metrics: list[str] = []
    involved_tables = set(re.findall(r"\bfrom\s+([A-Za-z_][\w]*)|\bjoin\s+([A-Za-z_][\w]*)", sql or "", re.I))
    involved = {a or b for a, b in involved_tables if a or b}

    for table, info in profile.tables.items():
        if table not in involved:
            continue
        for condition in info.default_filters:
            if _sql_has(sql, condition):
                used_filters.append(f"{table}: {condition}")

    for col in profile.columns.values():
        if col.default_filter and _sql_has(sql, col.default_filter):
            used_filters.append(f"{col.key}: {col.default_filter}")

    for rel in profile.relations:
        if not rel.parts:
            continue
        lt, _, rt, _ = rel.parts
        if lt in involved and rt in involved:
            used_relations.append(f"{rel.left} = {rel.right}")

    q = question or ""
    for metric in profile.metrics.values():
        if metric.enabled and metric.name in q:
            used_metrics.append(f"{metric.name} = {metric.formula}")

    summary_bits = [f"使用 {source_label or source} 数据源"]
    if auto_routed:
        summary_bits.append("由系统自动路由")
    if used_metrics:
        summary_bits.append(f"命中指标: {', '.join(m.split('=', 1)[0].strip() for m in used_metrics)}")
    if used_filters:
        summary_bits.append("应用了默认业务过滤")
    if retrieval_trace and retrieval_trace.get("retrieval_used"):
        summary_bits.append("使用了精简 Schema 召回")

    return {
        "summary": "；".join(summary_bits),
        "source": source,
        "source_label": source_label,
        "route_reason": route_reason or "",
        "default_filters": sorted(set(used_filters)),
        "relations": sorted(set(used_relations)),
        "metrics": used_metrics,
        "retrieval": retrieval_trace or {},
    }
