from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.core.business_domains import token_for, user_from_token
from app.main import app


def _headers(username: str) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username)}


def _teacher_class(username: str = "tea_li") -> int:
    auth = user_from_token(token_for(username))
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        return int(
            conn.execute(
                "SELECT id FROM teaching_class WHERE teacher_id=? ORDER BY id LIMIT 1",
                (auth.row_scope["teacher_id"],),
            ).fetchone()[0]
        )


def _delete_session(session_id: int) -> None:
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        turn_ids = [row[0] for row in conn.execute("SELECT id FROM assistant_turn WHERE session_id=?", (session_id,))]
        if turn_ids:
            marks = ",".join("?" for _ in turn_ids)
            conn.execute(f"DELETE FROM query_execution_trace WHERE turn_id IN ({marks})", turn_ids)
        conn.execute("DELETE FROM assistant_turn WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM assistant_session WHERE id=?", (session_id,))
        conn.commit()


def test_metric_catalog_exposes_safe_role_and_page_visible_definitions():
    class_id = _teacher_class()
    with TestClient(app) as client:
        response = client.get(
            "/api/assistant/metrics",
            params={"page": "course_analytics", "teaching_class_id": class_id},
            headers=_headers("tea_li"),
        )
    assert response.status_code == 200
    body = response.json()
    codes = {item["definition"]["code"] for item in body["items"]}
    assert {"assignment_completion_rate", "attendance_rate", "grade_pass_rate"} <= codes
    assert "assistant_success_rate" not in codes
    definition = body["items"][0]["definition"]
    assert "row_scope" not in definition and "roles" not in definition and "aliases" not in definition
    assert "sql" not in definition and "tables" not in definition


def test_fixed_api_and_natural_language_use_identical_certified_result():
    class_id = _teacher_class()
    with TestClient(app) as client:
        fixed = client.get(
            "/api/assistant/metrics",
            params={
                "page": "course_analytics",
                "teaching_class_id": class_id,
                "code": "assignment_completion_rate",
            },
            headers=_headers("tea_li"),
        )
        asked = client.post(
            "/api/assistant/query",
            headers=_headers("tea_li"),
            json={
                "question": "这门课的作业完成率是多少？",
                "context": {"page": "course_analytics", "teaching_class_id": class_id},
            },
        )
    assert fixed.status_code == asked.status_code == 200
    fixed_metric = fixed.json()["items"][0]
    asked_body = asked.json()
    try:
        assert asked_body["status"] == "success"
        assert asked_body["answer_type"] == "metric"
        assert asked_body["trace_summary"]["route"] == "semantic_metric"
        assert asked_body["data"]["metric"] == fixed_metric
        assert asked_body["sql"] is None
    finally:
        _delete_session(asked_body["session_id"])


def test_metric_context_cannot_escape_teacher_row_scope():
    auth = user_from_token(token_for("tea_li"))
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        other_class = int(
            conn.execute(
                "SELECT id FROM teaching_class WHERE teacher_id<>? ORDER BY id LIMIT 1",
                (auth.row_scope["teacher_id"],),
            ).fetchone()[0]
        )
    with TestClient(app) as client:
        response = client.get(
            "/api/assistant/metrics",
            params={
                "page": "course_analytics",
                "teaching_class_id": other_class,
                "code": "assignment_completion_rate",
            },
            headers=_headers("tea_li"),
        )
    assert response.status_code == 403


def test_trace_backed_metric_is_available_without_fabricating_missing_samples():
    with TestClient(app) as client:
        fixed = client.get(
            "/api/assistant/metrics",
            params={"page": "governance", "code": "assistant_low_confidence_rate"},
            headers=_headers("admin"),
        )
        asked = client.post(
            "/api/assistant/query",
            headers=_headers("admin"),
            json={"question": "当前低置信率是多少？", "context": {"page": "governance"}},
        )
    item = fixed.json()["items"][0]
    asked_body = asked.json()
    try:
        assert item["status"] == "available"
        assert item["value"] is None or 0 <= item["value"] <= 100
        assert asked_body["status"] == "success"
        assert asked_body["error"] is None
        assert asked_body["data"]["metric"] == item
    finally:
        _delete_session(asked_body["session_id"])


def test_unknown_or_invisible_metric_returns_404():
    with TestClient(app) as client:
        unknown = client.get(
            "/api/assistant/metrics",
            params={"page": "assistant", "code": "not_a_metric"},
            headers=_headers("admin"),
        )
        invisible = client.get(
            "/api/assistant/metrics",
            params={"page": "assistant", "code": "assistant_success_rate"},
            headers=_headers("tea_li"),
        )
    assert unknown.status_code == invisible.status_code == 404
