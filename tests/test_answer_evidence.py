from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.core import assistant_orchestrator, teaching_migrations
from app.core.business_domains import token_for
from app.main import app


def _headers(username: str) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username)}


def _legacy(*, degraded: bool = False, confidence: int = 55) -> dict:
    return {
        "sql": "SELECT count(*) AS n FROM teaching_class",
        "columns": ["n"],
        "column_sources": ["n"],
        "rows": [[2]],
        "row_count": 1,
        "elapsed_ms": 4,
        "truncated": False,
        "error": None,
        "clarify": None,
        "source": "teaching",
        "source_label": "教学业务库",
        "auto_routed": False,
        "route_reason": "统一助手固定教学库",
        "confidence": confidence,
        "confidence_detail": {"reason": "测试置信度"},
        "judge_id": None,
        "explanation": {},
        "trace": {
            "retrieval_used": True,
            "retrieval_status": "degraded" if degraded else "used",
            "retrievers_used": ["keyword", "graph"],
            "tables": ["teaching_class"],
            "context_preview": "不得进入响应或轨迹表",
            "stage_timings": {
                "retrieval_ms": 2,
                "model_ms": 3,
                "validation_ms": 1,
                "execution_ms": 4,
            },
            "degraded": degraded,
            "degradation_reason": "检索服务不可用，已安全回退" if degraded else None,
            "attempts": 1,
        },
    }


def _delete_session(session_id: int) -> None:
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        turn_ids = [row[0] for row in conn.execute("SELECT id FROM assistant_turn WHERE session_id=?", (session_id,))]
        if turn_ids:
            marks = ",".join("?" for _ in turn_ids)
            conn.execute(f"DELETE FROM query_execution_trace WHERE turn_id IN ({marks})", turn_ids)
        conn.execute("DELETE FROM assistant_turn WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM assistant_session WHERE id=?", (session_id,))
        conn.commit()


def test_admin_trace_has_stage_detail_but_never_sensitive_context(monkeypatch):
    monkeypatch.setattr(assistant_orchestrator, "ask_service", lambda *a, **k: _legacy())
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("admin"),
            json={
                "question": "证据测试：统计课程数据",
                "context": {"page": "assistant"},
                "options": {"preferred_answer_type": "nl2sql", "include_trace": True},
            },
        )
        low_confidence = client.get(
            "/api/assistant/metrics",
            params={"page": "governance", "code": "assistant_low_confidence_rate"},
            headers=_headers("admin"),
        )
        stage_latency = client.get(
            "/api/assistant/metrics",
            params={"page": "governance", "code": "assistant_stage_latency"},
            headers=_headers("admin"),
        )
    body = response.json()
    try:
        assert response.status_code == 200
        assert body["scope"]["page"] == "assistant"
        assert body["evidence"][0]["source"] == "teaching"
        assert body["trace_summary"]["retrieval_status"] == "used"
        assert body["trace_summary"]["stages"]["model"]["elapsed_ms"] == 3
        assert "context_preview" not in str(body["trace_summary"])
        assert "tables" not in body["trace_summary"]
        assert any(item["code"] == "LOW_CONFIDENCE" for item in body["warnings"])

        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            trace = conn.execute("SELECT * FROM query_execution_trace WHERE turn_id=?", (body["turn_id"],)).fetchone()
            columns = {row[1] for row in conn.execute("PRAGMA table_info(query_execution_trace)")}
        assert trace is not None and trace["confidence_score"] == 55
        assert {"question", "sql", "rows", "context_preview"}.isdisjoint(columns)
        assert "context_preview" not in trace["stages_json"]
        low_item = low_confidence.json()["items"][0]
        latency_item = stage_latency.json()["items"][0]
        assert low_item["status"] == "available" and low_item["sample_size"] >= 1
        assert low_item["value"] is not None
        assert latency_item["status"] == "available" and latency_item["sample_size"] >= 1
        assert "model" in latency_item["value"]
    finally:
        _delete_session(body["session_id"])


def test_ordinary_user_gets_safe_stage_status_without_timings(monkeypatch):
    monkeypatch.setattr(assistant_orchestrator, "ask_service", lambda *a, **k: _legacy(confidence=90))
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("tea_li"),
            json={
                "question": "证据测试：统计课程数据",
                "context": {"page": "assistant"},
                "options": {"preferred_answer_type": "nl2sql", "include_trace": True},
            },
        )
    body = response.json()
    try:
        assert response.status_code == 200
        assert "retrievers_used" not in body["trace_summary"]
        assert "retrieval_status" not in body["trace_summary"]
        assert body["trace_summary"]["stages"]["model"] == {"status": "success"}
        assert "elapsed_ms" not in body["trace_summary"]["stages"]["execution"]
        assert body["scope"]["description"] == "仅本人授课范围"
    finally:
        _delete_session(body["session_id"])


def test_retrieval_fallback_is_structured_degraded_response(monkeypatch):
    monkeypatch.setattr(assistant_orchestrator, "ask_service", lambda *a, **k: _legacy(degraded=True, confidence=90))
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("admin"),
            json={
                "question": "证据测试：统计课程数据",
                "context": {"page": "assistant"},
                "options": {"preferred_answer_type": "nl2sql"},
            },
        )
    body = response.json()
    try:
        assert body["status"] == "degraded"
        assert body["trace_summary"]["degraded"] is True
        assert any(item["code"] == "RETRIEVAL_DEGRADED" for item in body["warnings"])
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            row = conn.execute("SELECT degraded,degradation_reason FROM query_execution_trace WHERE turn_id=?", (body["turn_id"],)).fetchone()
        assert row[0] == 1 and "安全回退" in row[1]
    finally:
        _delete_session(body["session_id"])
