from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core import assistant_orchestrator, teaching_migrations
from app.core.business_domains import token_for, user_from_token
from app.core.validator import SQLValidationError, validate_and_fix
from app.main import app


TITLE_PREFIX = "API测试"


@pytest.fixture(autouse=True)
def clean_api_sessions():
    _clean()
    yield
    _clean()


def _clean() -> None:
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        ids = [
            row[0]
            for row in conn.execute(
                "SELECT id FROM assistant_session WHERE title LIKE ?", (f"{TITLE_PREFIX}%",)
            ).fetchall()
        ]
        if ids:
            marks = ",".join("?" for _ in ids)
            turn_ids = [
                row[0]
                for row in conn.execute(
                    f"SELECT id FROM assistant_turn WHERE session_id IN ({marks})", ids
                ).fetchall()
            ]
            if turn_ids:
                turn_marks = ",".join("?" for _ in turn_ids)
                conn.execute(
                    f"DELETE FROM query_execution_trace WHERE turn_id IN ({turn_marks})",
                    turn_ids,
                )
            conn.execute(f"DELETE FROM assistant_turn WHERE session_id IN ({marks})", ids)
            conn.execute(f"DELETE FROM assistant_session WHERE id IN ({marks})", ids)
        conn.commit()


def _headers(username: str) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username)}


def _legacy_success(rows=None) -> dict:
    rows = rows or [["数据库系统", 42], ["Web 开发", 35]]
    return {
        "sql": "SELECT name, count FROM safe_summary LIMIT 2",
        "columns": ["name", "count"],
        "column_sources": ["name", "count"],
        "rows": rows,
        "row_count": len(rows),
        "elapsed_ms": 12,
        "truncated": False,
        "error": None,
        "clarify": None,
        "source": "teaching",
        "source_label": "教学业务库",
        "auto_routed": False,
        "route_reason": "统一助手固定教学库",
        "confidence": None,
        "confidence_detail": None,
        "judge_id": "judge-test",
        "explanation": {},
        "trace": {
            "retrieval_used": True,
            "retrievers_used": ["keyword"],
            "context_preview": "普通角色不应看到此字段",
        },
    }


@pytest.mark.parametrize(
    ("username", "question", "answer_type", "status"),
    [
        ("tea_li", "API测试：我有多少待批阅？", "metric", "success"),
        ("counselor_chen", "API测试：我有什么待办？", "business_state", "success"),
        ("tea_li", "API测试：怎么进入课程分析？", "navigation", "success"),
        ("admin", "API测试：给我讲个笑话", "unsupported", "success"),
    ],
)
def test_unified_endpoint_routes_deterministic_question_types(
    username: str, question: str, answer_type: str, status: str
):
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers(username),
            json={"question": question, "context": {"page": "assistant"}},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["answer_type"] == answer_type
    assert body["status"] == status
    assert body["session_id"] > 0 and body["turn_id"] > 0
    assert body["trace_summary"]["route"]


def test_nl2sql_is_transformed_limited_and_context_scope_is_forwarded(monkeypatch):
    teacher = user_from_token(token_for("tea_li"))
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        class_id = conn.execute(
            "SELECT id FROM teaching_class WHERE teacher_id = ? ORDER BY id LIMIT 1",
            (teacher.row_scope["teacher_id"],),
        ).fetchone()[0]
    captured = {}

    def fake_ask(question, **kwargs):
        captured.update(kwargs)
        return _legacy_success()

    monkeypatch.setattr(assistant_orchestrator, "ask_service", fake_ask)
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("tea_li"),
            json={
                "question": "API测试：查询这门课程的选课数量",
                "context": {"page": "course_analytics", "teaching_class_id": class_id},
                "options": {
                    "preferred_answer_type": "nl2sql",
                    "include_sql": False,
                    "include_trace": True,
                    "max_rows": 1,
                },
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["answer_type"] == "nl2sql" and body["status"] == "success"
    assert body["sql"] is None
    assert body["data"]["row_count"] == 1 and body["data"]["truncated"] is True
    assert captured["row_scope"]["teacher_id"] == teacher.row_scope["teacher_id"]
    assert captured["row_scope"]["teaching_class_id"] == class_id
    assert "context_preview" not in body["trace_summary"]


def test_forged_context_is_403_before_nl2sql(monkeypatch):
    teacher = user_from_token(token_for("tea_li"))
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        other_class = conn.execute(
            "SELECT id FROM teaching_class WHERE teacher_id <> ? ORDER BY id LIMIT 1",
            (teacher.row_scope["teacher_id"],),
        ).fetchone()[0]
    called = False

    def fake_ask(*args, **kwargs):
        nonlocal called
        called = True
        return _legacy_success()

    monkeypatch.setattr(assistant_orchestrator, "ask_service", fake_ask)
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("tea_li"),
            json={
                "question": "API测试：查询这门课程",
                "context": {"page": "course_analytics", "teaching_class_id": other_class},
            },
        )
    assert response.status_code == 403
    assert called is False


def test_teaching_class_context_is_enforced_by_sql_validator():
    allowed = {"assignment": ["id", "teaching_class_id"]}
    scoped = {"teaching_class_id": 900001}
    sql, _ = validate_and_fix(
        "SELECT id FROM assignment WHERE teaching_class_id = 900001 LIMIT 10",
        allowed,
        row_scope=scoped,
    )
    assert "teaching_class_id = 900001" in sql
    with pytest.raises(SQLValidationError, match="teaching_class_id = 900001"):
        validate_and_fix(
            "SELECT id FROM assignment LIMIT 10", allowed, row_scope=scoped
        )


def test_nl2sql_failure_is_structured_and_business_api_remains_available(monkeypatch):
    def failing_ask(*args, **kwargs):
        raise RuntimeError("simulated model outage")

    monkeypatch.setattr(assistant_orchestrator, "ask_service", failing_ask)
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("admin"),
            json={
                "question": "API测试：统计课程数据",
                "context": {"page": "assistant"},
                "options": {"preferred_answer_type": "nl2sql"},
            },
        )
        workbench = client.get("/api/workbench", headers=_headers("admin"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "ASSISTANT_INTERNAL_ERROR"
    assert body["trace_summary"]["failed_stage"] == "orchestrator"
    assert workbench.status_code == 200


def test_legacy_ask_endpoint_remains_compatible(monkeypatch):
    from app.api import routes

    monkeypatch.setattr(routes, "ask_service", lambda *args, **kwargs: _legacy_success())
    with TestClient(app) as client:
        response = client.post(
            "/api/ask",
            headers=_headers("admin"),
            json={"question": "API测试：旧接口兼容", "source": "teaching"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["name", "count"]
    assert body["rows"][0] == ["数据库系统", 42]


def test_session_http_api_is_identity_isolated_and_query_appends_turn(monkeypatch):
    monkeypatch.setattr(assistant_orchestrator, "ask_service", lambda *a, **k: _legacy_success())
    with TestClient(app) as client:
        created = client.post(
            "/api/assistant/sessions",
            headers=_headers("admin"),
            json={
                "title": "API测试会话接口",
                "context": {"page": "assistant"},
                "client_request_id": "api-test-session-0001",
            },
        )
        assert created.status_code == 201
        session_id = created.json()["item"]["id"]
        assert client.get(
            f"/api/assistant/sessions/{session_id}", headers=_headers("stu_zhang")
        ).status_code == 404
        queried = client.post(
            "/api/assistant/query",
            headers=_headers("admin"),
            json={
                "session_id": session_id,
                "question": "API测试：查询课程数据",
                "context": {"page": "assistant"},
                "options": {"preferred_answer_type": "nl2sql"},
            },
        )
        assert queried.status_code == 200
        detail = client.get(
            f"/api/assistant/sessions/{session_id}", headers=_headers("admin")
        ).json()
        patched = client.patch(
            f"/api/assistant/sessions/{session_id}",
            headers=_headers("admin"),
            json={"title": "API测试已重命名", "is_favorite": True},
        )
        deleted = client.delete(
            f"/api/assistant/sessions/{session_id}", headers=_headers("admin")
        )
    assert detail["turns"]["total"] == 1
    assert patched.json()["item"]["is_favorite"] is True
    assert deleted.json()["deleted"] is True
