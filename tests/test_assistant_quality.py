from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core import assistant_quality, teaching_migrations
from app.core.business_domains import token_for, user_from_token
from app.main import app


TITLE_PREFIX = "V3-3.5 运营测试"
PRIVATE_QUESTION = "PRIVATE-QUESTION-不得出现在运营面板"


def _headers(username: str) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username)}


@pytest.fixture(autouse=True)
def clean_quality_rows():
    yield
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        session_ids = [row[0] for row in conn.execute("SELECT id FROM assistant_session WHERE title LIKE ?", (f"{TITLE_PREFIX}%",)).fetchall()]
        if session_ids:
            marks = ",".join("?" for _ in session_ids)
            conn.execute(f"DELETE FROM assistant_session WHERE id IN ({marks})", session_ids)
        conn.commit()


def _seed_quality_rows() -> None:
    auth = user_from_token(token_for("admin"))
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = [
        ("success", "nl2sql", None, "local", "used", 0, 100, 90, None),
        ("degraded", "nl2sql", None, "server", "degraded", 1, 300, 60, None),
        ("failed", "nl2sql", "ASSISTANT_NL2SQL_FAILED", "none", "not_used", 0, 500, None, "model"),
        ("rejected", "unsupported", "ASSISTANT_QUERY_REJECTED", "none", "not_applicable", 0, None, None, "validation"),
    ]
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        cursor = conn.execute(
            """INSERT INTO assistant_session
               (user_id,role_binding_id,title,page,context_summary,created_at,updated_at)
               VALUES (?,?,?,'assistant','{"page":"assistant"}',?,?)""",
            (auth.user_id, auth.role_binding_id, TITLE_PREFIX, now, now),
        )
        session_id = int(cursor.lastrowid)
        for index, (status, answer_type, error_code, backend, retrieval_status, degraded, elapsed, confidence, failed_stage) in enumerate(rows, 1):
            turn = conn.execute(
                """INSERT INTO assistant_turn
                   (session_id,sequence_no,question,answer_type,status,safe_answer_summary,
                    context_summary,error_code,started_at,completed_at,created_at,updated_at)
                   VALUES (?,?,?,?,?,'safe','{"page":"assistant"}',?,?,?,?,?)""",
                (session_id, index, f"{PRIVATE_QUESTION}-{index}", answer_type, status, error_code, now, now, now, now),
            )
            if elapsed is not None:
                conn.execute(
                    """INSERT INTO query_execution_trace
                       (turn_id,route,retrieval_status,retrieval_backend,retrievers_json,stages_json,
                        degraded,total_elapsed_ms,confidence_score,result_row_count,truncated,failed_stage,created_at)
                       VALUES (?,'nl2sql',?,?, '[]','{}',?,?,?,0,0,?,?)""",
                    (turn.lastrowid, retrieval_status, backend, degraded, elapsed, confidence, failed_stage, now),
                )
        conn.commit()


def test_quality_operations_is_aggregate_only_and_has_required_metrics(monkeypatch):
    _seed_quality_rows()
    monkeypatch.setattr(
        assistant_quality,
        "list_feedback",
        lambda limit=500: [{
            "kind": "incorrect",
            "source_label": "教学业务库",
            "category": "wrong_scope",
            "question": PRIVATE_QUESTION,
            "reason": "PRIVATE-FEEDBACK-REASON",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }],
    )
    monkeypatch.setattr(
        assistant_quality,
        "list_review_items",
        lambda limit=500: [{
            "kind": "feedback_fix",
            "status": "open",
            "title": PRIVATE_QUESTION,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }],
    )

    with TestClient(app) as client:
        response = client.get("/api/assistant/quality-operations?days=30", headers=_headers("admin"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["total_queries"] >= 4
    assert isinstance(body["summary"]["p50_ms"], int)
    assert body["summary"]["p95_ms"] >= body["summary"]["p50_ms"]
    assert body["summary"]["unauthorized_rejections"] >= 1
    assert body["summary"]["low_confidence_queries"] >= 1
    assert body["summary"]["negative_feedback"] == 1
    assert body["summary"]["pending_governance"] == 1
    assert body["retrieval"]["local_count"] >= 1
    assert body["retrieval"]["server_count"] >= 1
    assert next(item for item in body["failure_distribution"] if item["stage"] == "model")["count"] >= 1
    assert body["privacy"]["raw_question_exposed"] is False
    encoded = json.dumps(body, ensure_ascii=False)
    assert PRIVATE_QUESTION not in encoded
    assert "PRIVATE-FEEDBACK-REASON" not in encoded


def test_quality_percentile_uses_nearest_rank():
    assert assistant_quality._percentile([100, 300, 500], 0.50) == 300
    assert assistant_quality._percentile([100, 300, 500], 0.95) == 500


def test_quality_operations_is_admin_only():
    with TestClient(app) as client:
        response = client.get("/api/assistant/quality-operations", headers=_headers("tea_li"))
    assert response.status_code == 403
