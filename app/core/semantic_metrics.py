"""Version-controlled semantic metrics shared by cards and assistant queries."""
from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core import teaching_migrations
from app.core.assistant_context import AssistantPageContext, resolve_assistant_context
from app.core.business_domains import AuthContext
from app.core.config import ROOT_DIR
from app.core.governance import load_settings


METRIC_CATALOG_PATH = ROOT_DIR / "data" / "semantic_metrics.yaml"


class SemanticMetricNotFoundError(LookupError):
    """The requested metric is unknown or not visible in this role/page."""


@dataclass(frozen=True)
class MetricDefinition:
    code: str
    name: str
    aliases: tuple[str, ...]
    domain: str
    description: str
    formula: str
    source: str
    time_semantics: str
    roles: frozenset[str]
    pages: frozenset[str]
    row_scope: str
    minimum_sample_size: int
    supports_drilldown: bool
    unit: str
    availability: str = "available"
    unavailable_reason: str | None = None

    def public(self, catalog_updated_at: str) -> dict[str, Any]:
        # Deliberately exclude aliases, physical tables, SQL and internal row-scope rules.
        return {
            "code": self.code,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "formula": self.formula,
            "source": self.source,
            "time_semantics": self.time_semantics,
            "minimum_sample_size": self.minimum_sample_size,
            "supports_drilldown": self.supports_drilldown,
            "unit": self.unit,
            "availability": self.availability,
            "unavailable_reason": self.unavailable_reason,
            "definition_updated_at": catalog_updated_at,
        }


@lru_cache(maxsize=1)
def _catalog() -> tuple[str, tuple[MetricDefinition, ...]]:
    raw = yaml.safe_load(Path(METRIC_CATALOG_PATH).read_text(encoding="utf-8")) or {}
    updated_at = str(raw.get("updated_at") or "")
    definitions = tuple(
        MetricDefinition(
            code=str(item["code"]),
            name=str(item["name"]),
            aliases=tuple(str(value) for value in item.get("aliases") or ()),
            domain=str(item["domain"]),
            description=str(item["description"]),
            formula=str(item["formula"]),
            source=str(item["source"]),
            time_semantics=str(item["time_semantics"]),
            roles=frozenset(str(value) for value in item.get("roles") or ()),
            pages=frozenset(str(value) for value in item.get("pages") or ()),
            row_scope=str(item["row_scope"]),
            minimum_sample_size=int(item.get("minimum_sample_size") or 1),
            supports_drilldown=bool(item.get("supports_drilldown")),
            unit=str(item.get("unit") or ""),
            availability=str(item.get("availability") or "available"),
            unavailable_reason=(str(item["unavailable_reason"]) if item.get("unavailable_reason") else None),
        )
        for item in raw.get("metrics") or ()
    )
    codes = [item.code for item in definitions]
    if len(codes) != len(set(codes)):
        raise ValueError("semantic metric code must be unique")
    return updated_at, definitions


def clear_metric_catalog_cache() -> None:
    _catalog.cache_clear()


def list_metric_definitions(auth: AuthContext, page: str) -> list[MetricDefinition]:
    return [item for item in _catalog()[1] if auth.role in item.roles and page in item.pages]


def match_semantic_metric(
    auth: AuthContext, question: str, effective_context: dict[str, Any]
) -> MetricDefinition | None:
    candidates: list[tuple[int, MetricDefinition]] = []
    normalized = question.strip().lower()
    for definition in list_metric_definitions(auth, str(effective_context["page"])):
        for alias in (definition.name, *definition.aliases):
            if alias.lower() in normalized:
                candidates.append((len(alias), definition))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def metric_results(
    auth: AuthContext,
    context: AssistantPageContext | dict[str, Any],
    code: str | None = None,
) -> dict[str, Any]:
    resolution = resolve_assistant_context(auth, context)
    visible = list_metric_definitions(auth, str(resolution.effective_context["page"]))
    if code:
        visible = [item for item in visible if item.code == code]
        if not visible:
            raise SemanticMetricNotFoundError("指标不存在或当前工作身份无权查看")
    items = [evaluate_semantic_metric(auth, item, resolution.effective_context) for item in visible]
    return {
        "items": items,
        "count": len(items),
        "context": resolution.effective_context,
        "ignored_context_fields": resolution.ignored_fields,
    }


def evaluate_semantic_metric(
    auth: AuthContext,
    definition: MetricDefinition,
    effective_context: dict[str, Any],
) -> dict[str, Any]:
    updated_at = _catalog()[0]
    result: dict[str, Any] = {
        "definition": definition.public(updated_at),
        "status": "available",
        "value": None,
        "unit": definition.unit,
        "sample_size": 0,
        "small_sample": False,
        "breakdown": None,
        "warnings": [],
    }
    if definition.availability != "available":
        result["status"] = "unavailable"
        result["warnings"] = [definition.unavailable_reason or "当前数据条件不足"]
        return result
    with _connect() as conn:
        value, sample_size, breakdown, data_updated_at = _compute(
            conn, auth, definition.code, effective_context
        )
    result.update(
        value=value,
        sample_size=sample_size,
        breakdown=breakdown,
        data_updated_at=data_updated_at,
    )
    if sample_size < definition.minimum_sample_size:
        result["small_sample"] = True
        result["warnings"] = [
            f"当前样本量 {sample_size}，低于建议最小样本量 {definition.minimum_sample_size}，请谨慎解读。"
        ]
    return result


def metric_answer_payload(result: dict[str, Any]) -> dict[str, Any]:
    definition = result["definition"]
    if result["status"] == "unavailable":
        return {
            "status": "failed",
            "answer_type": "metric",
            "answer": "",
            "data": {"metric": result},
            "sql": None,
            "evidence": [],
            "metric_definitions": [definition],
            "warnings": result["warnings"],
            "confidence": None,
            "trace_summary": {"route": "semantic_metric", "metric_code": definition["code"]},
            "suggested_questions": [],
            "suggested_actions": [],
            "error": {"code": "METRIC_UNAVAILABLE", "message": result["warnings"][0]},
            "clarify": None,
        }
    value = result["value"]
    display = "暂无可计算数据" if value is None else f"{value}{result['unit']}"
    return {
        "status": "success",
        "answer_type": "metric",
        "answer": f"{definition['name']}：{display}",
        "data": {"metric": result},
        "sql": None,
        "evidence": [{"kind": "semantic_metric", "label": definition["source"], "source": "certified_metric"}],
        "metric_definitions": [definition],
        "warnings": result["warnings"],
        "confidence": {"level": "high", "basis": "certified_metric"},
        "trace_summary": {"route": "semantic_metric", "metric_code": definition["code"]},
        "suggested_questions": [],
        "suggested_actions": [],
        "error": None,
        "clarify": None,
    }


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(teaching_migrations.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _compute(
    conn: sqlite3.Connection, auth: AuthContext, code: str, context: dict[str, Any]
) -> tuple[Any, int, Any, str | None]:
    if code.startswith("assignment_"):
        return _assignment(conn, auth, code, context)
    if code.startswith("attendance_"):
        return _attendance(conn, auth, code, context)
    if code.startswith("grade_"):
        return _grade(conn, auth, code, context)
    if code.startswith("teaching_"):
        return _teaching_issue(conn, auth, code, context)
    if code.startswith("support_"):
        return _support(conn, auth, code, context)
    if code.startswith("assistant_"):
        return _platform(conn, code)
    raise SemanticMetricNotFoundError(f"未实现的指标：{code}")


def _filters(auth: AuthContext, context: dict[str, Any], tc_alias: str = "tc") -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if context.get("teaching_class_id"):
        clauses.append(f"{tc_alias}.id = ?")
        params.append(context["teaching_class_id"])
    if context.get("academic_year"):
        clauses.append(f"{tc_alias}.year = ?")
        params.append(context["academic_year"])
    if context.get("semester"):
        clauses.append(f"lower({tc_alias}.semester) = ?")
        params.append(context["semester"])
    if auth.role == "teacher":
        clauses.append(f"{tc_alias}.teacher_id = ?")
        params.append(auth.row_scope.get("teacher_id"))
    elif auth.role == "college_manager":
        clauses.append(f"c.college_id = ?")
        params.append(auth.row_scope.get("college_id"))
    if context.get("college_id"):
        clauses.append("c.college_id = ?")
        params.append(context["college_id"])
    return clauses, params


def _assignment(conn: sqlite3.Connection, auth: AuthContext, code: str, context: dict[str, Any]):
    clauses, params = _filters(auth, context)
    if auth.role == "student":
        clauses.append("e.student_id = ?")
        params.append(auth.row_scope.get("student_id"))
    elif context.get("student_id"):
        clauses.append("e.student_id = ?")
        params.append(context["student_id"])
    where = " AND ".join(clauses) or "1=1"
    row = conn.execute(
        f"""SELECT count(*) expected_count,
            sum(CASE WHEN s.id IS NOT NULL AND s.submit_time IS NOT NULL AND s.status NOT IN ('missing','not_submitted') THEN 1 ELSE 0 END) submitted_count,
            sum(CASE WHEN s.id IS NOT NULL AND s.late=1 THEN 1 ELSE 0 END) late_count,
            sum(CASE WHEN s.id IS NOT NULL AND s.submit_time IS NOT NULL AND s.status NOT IN ('missing','not_submitted')
                AND NOT EXISTS (SELECT 1 FROM grading_record gr WHERE gr.submission_id=s.id) THEN 1 ELSE 0 END) pending_count,
            max(coalesce(s.submit_time,a.publish_time)) updated_at
            FROM assignment a JOIN teaching_class tc ON tc.id=a.teaching_class_id
            JOIN course c ON c.id=tc.course_id JOIN enrollment e ON e.teaching_class_id=tc.id
            LEFT JOIN assignment_submission s ON s.assignment_id=a.id AND s.student_id=e.student_id
            WHERE a.status='published' AND {where}""", params
    ).fetchone()
    expected, submitted, late, pending = map(int, row[:4])
    updated = row[-1]
    values = {
        "assignment_completion_rate": _pct(submitted, expected),
        "assignment_late_rate": _pct(late, submitted),
        "assignment_missing_count": expected - submitted,
        "assignment_pending_grading_count": pending,
    }
    samples = {"assignment_late_rate": submitted, "assignment_pending_grading_count": submitted}
    breakdown = {"expected_count": expected, "submitted_count": submitted, "late_count": late, "pending_grading_count": pending}
    return values[code], samples.get(code, expected), breakdown, updated


def _attendance(conn: sqlite3.Connection, auth: AuthContext, code: str, context: dict[str, Any]):
    clauses, params = _filters(auth, context)
    if auth.role == "student":
        clauses.append("a.student_id = ?")
        params.append(auth.row_scope.get("student_id"))
    elif context.get("student_id"):
        clauses.append("a.student_id = ?")
        params.append(context["student_id"])
    if auth.role == "counselor":
        clauses.append("EXISTS (SELECT 1 FROM student s JOIN counselor_class_group ccg ON ccg.class_group_id=s.class_id WHERE s.id=a.student_id AND ccg.counselor_id=?)")
        params.append(auth.row_scope.get("counselor_id"))
    time_range = context.get("time_range") or {}
    if time_range.get("start"):
        clauses.append("datetime(a.class_date) >= datetime(?)")
        params.append(time_range["start"])
    if time_range.get("end"):
        clauses.append("datetime(a.class_date) <= datetime(?)")
        params.append(time_range["end"])
    where = " AND ".join(clauses) or "1=1"
    rows = conn.execute(
        f"""SELECT a.student_id,a.status,a.class_date,a.session_no,a.updated_at
            FROM attendance a JOIN teaching_class tc ON tc.id=a.teaching_class_id
            JOIN course c ON c.id=tc.course_id WHERE {where}
            ORDER BY a.student_id,a.class_date,a.session_no""", params
    ).fetchall()
    present = sum(1 for row in rows if row["status"] in {"present", "late"})
    absent = sum(1 for row in rows if row["status"] == "absent")
    longest = current = 0
    previous_student = None
    for row in rows:
        if row["student_id"] != previous_student:
            current = 0
            previous_student = row["student_id"]
        current = current + 1 if row["status"] == "absent" else 0
        longest = max(longest, current)
    values = {"attendance_rate": _pct(present, len(rows)), "attendance_absence_count": absent, "attendance_consecutive_absence": longest}
    return values[code], len(rows), {"record_count": len(rows), "present_or_late_count": present, "absence_count": absent}, max((row["updated_at"] or row["class_date"] for row in rows), default=None)


def _grade(conn: sqlite3.Connection, auth: AuthContext, code: str, context: dict[str, Any]):
    clauses, params = _filters(auth, context)
    where = " AND ".join(clauses) or "1=1"
    if code in {"grade_submission_status", "grade_publication_progress"}:
        rows = conn.execute(
            f"""SELECT coalesce(gs.status,'not_submitted') status,gs.updated_at
                FROM teaching_class tc JOIN course c ON c.id=tc.course_id
                LEFT JOIN grade_submission gs ON gs.teaching_class_id=tc.id WHERE {where}""", params
        ).fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        if code == "grade_submission_status":
            value: Any = counts
        else:
            value = _pct(counts.get("published", 0), len(rows))
        return value, len(rows), counts, max((row["updated_at"] for row in rows if row["updated_at"]), default=None)
    if auth.role == "student":
        clauses.append("s.student_id = ?")
        params.append(auth.row_scope.get("student_id"))
    where = " AND ".join(clauses) or "1=1"
    rows = conn.execute(
        f"""SELECT gr.score,gr.published_at FROM grading_record gr
            JOIN assignment_submission s ON s.id=gr.submission_id
            JOIN assignment a ON a.id=s.assignment_id JOIN teaching_class tc ON tc.id=a.teaching_class_id
            JOIN course c ON c.id=tc.course_id WHERE gr.published=1 AND gr.score IS NOT NULL AND {where}""", params
    ).fetchall()
    scores = [float(row["score"]) for row in rows]
    bands = {"below_60": 0, "60_69": 0, "70_79": 0, "80_89": 0, "90_plus": 0}
    for score in scores:
        key = "below_60" if score < 60 else "60_69" if score < 70 else "70_79" if score < 80 else "80_89" if score < 90 else "90_plus"
        bands[key] += 1
    value = bands if code == "grade_distribution" else _pct(sum(score >= 60 for score in scores), len(scores))
    return value, len(scores), bands, max((row["published_at"] for row in rows if row["published_at"]), default=None)


def _teaching_issue(conn: sqlite3.Connection, auth: AuthContext, code: str, context: dict[str, Any]):
    clauses, params = _filters(auth, context)
    where = " AND ".join(clauses) or "1=1"
    row = conn.execute(
        f"""SELECT count(*) total,
            sum(CASE WHEN ti.status!='resolved' THEN 1 ELSE 0 END) open_count,
            sum(CASE WHEN ti.status!='resolved' AND (julianday('now')-julianday(ti.created_at))*24>48 THEN 1 ELSE 0 END) overdue_count,
            avg(CASE WHEN ti.status='resolved' AND ti.resolved_at IS NOT NULL THEN (julianday(ti.resolved_at)-julianday(ti.created_at))*24 END) avg_hours,
            sum(CASE WHEN ti.status='resolved' AND ti.resolved_at IS NOT NULL THEN 1 ELSE 0 END) resolved_count,max(ti.updated_at)
            FROM teaching_issue ti JOIN teaching_class tc ON tc.id=ti.teaching_class_id JOIN course c ON c.id=tc.course_id WHERE {where}""", params
    ).fetchone()
    values = {"teaching_open_issue_count": int(row[1] or 0), "teaching_overdue_issue_count": int(row[2] or 0), "teaching_avg_resolution_hours": round(float(row[3]), 2) if row[3] is not None else None}
    sample = int(row[4] or 0) if code.endswith("avg_resolution_hours") else int(row[0] or 0)
    return values[code], sample, {"total_count": int(row[0] or 0), "open_count": int(row[1] or 0), "overdue_count": int(row[2] or 0), "resolved_count": int(row[4] or 0)}, row[5]


def _support(conn: sqlite3.Connection, auth: AuthContext, code: str, context: dict[str, Any]):
    clauses = ["sc.counselor_id = ?"]
    params: list[Any] = [auth.row_scope.get("counselor_id")]
    if context.get("student_id"):
        clauses.append("sc.student_id = ?")
        params.append(context["student_id"])
    if context.get("college_id"):
        clauses.append("s.college_id = ?")
        params.append(context["college_id"])
    row = conn.execute(
        f"""SELECT count(*) total,
            sum(CASE WHEN sc.status='open' THEN 1 ELSE 0 END) pending_contact,
            sum(CASE WHEN sc.status IN ('contacted','tracking') THEN 1 ELSE 0 END) pending_review,
            sum(CASE WHEN sc.status!='closed' AND sc.review_at IS NOT NULL AND datetime(sc.review_at)<datetime('now') THEN 1 ELSE 0 END) overdue_review,
            max(coalesce(sc.updated_at,sc.created_at)) FROM support_case sc JOIN student s ON s.id=sc.student_id
            WHERE {' AND '.join(clauses)}""", params
    ).fetchone()
    values = {"support_pending_contact_count": int(row[1] or 0), "support_pending_review_count": int(row[2] or 0), "support_overdue_review_count": int(row[3] or 0)}
    return values[code], int(row[0] or 0), {"case_count": int(row[0] or 0), "pending_contact_count": int(row[1] or 0), "pending_review_count": int(row[2] or 0), "overdue_review_count": int(row[3] or 0)}, row[4]


def _platform(conn: sqlite3.Connection, code: str):
    if code == "assistant_low_confidence_rate":
        threshold = int(load_settings().get("low_confidence_threshold") or 70)
        row = conn.execute(
            """SELECT count(*) evaluated,
            sum(CASE WHEN confidence_score < ? THEN 1 ELSE 0 END) low_count,
            max(created_at) FROM query_execution_trace WHERE confidence_score IS NOT NULL""",
            (threshold,),
        ).fetchone()
        evaluated, low = int(row[0] or 0), int(row[1] or 0)
        return _pct(low, evaluated), evaluated, {
            "evaluated_turn_count": evaluated,
            "low_confidence_count": low,
            "threshold": threshold,
        }, row[2]
    if code == "assistant_stage_latency":
        rows = conn.execute(
            "SELECT stages_json,created_at FROM query_execution_trace ORDER BY id"
        ).fetchall()
        totals: dict[str, float] = {}
        counts: dict[str, int] = {}
        for row in rows:
            try:
                stages = json.loads(row["stages_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            for name, item in stages.items():
                elapsed = item.get("elapsed_ms") if isinstance(item, dict) else None
                if isinstance(elapsed, (int, float)):
                    totals[name] = totals.get(name, 0.0) + float(elapsed)
                    counts[name] = counts.get(name, 0) + 1
        averages = {
            name: round(totals[name] / counts[name], 2) for name in sorted(totals)
        }
        return averages or None, len(rows), {
            "stage_sample_counts": counts
        }, max((row["created_at"] for row in rows), default=None)
    row = conn.execute(
        """SELECT count(*) total,sum(CASE WHEN status IN ('success','degraded') THEN 1 ELSE 0 END) completed,
        sum(CASE WHEN status='degraded' THEN 1 ELSE 0 END) degraded,max(completed_at) FROM assistant_turn"""
    ).fetchone()
    total, completed, degraded = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
    values = {"assistant_success_rate": _pct(completed, total), "assistant_degraded_rate": _pct(degraded, total)}
    return values[code], total, {"turn_count": total, "successful_or_degraded_count": completed, "degraded_count": degraded}, row[3]


def _pct(numerator: int, denominator: int) -> float | None:
    return round(numerator * 100 / denominator, 2) if denominator else None
