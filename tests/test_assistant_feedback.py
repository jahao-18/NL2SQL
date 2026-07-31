from __future__ import annotations

from fastapi.testclient import TestClient

from app.core import (
    assistant_orchestrator,
    examples,
    feedback,
    governance,
)
from app.core.business_domains import token_for
from app.main import app


def _headers(username: str) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username)}


def _legacy_success() -> dict:
    return {
        "sql": "SELECT name, COUNT(*) AS total FROM course GROUP BY name LIMIT 20",
        "columns": ["name", "total"],
        "column_sources": ["name", "total"],
        "rows": [["数据库系统", 1]],
        "row_count": 1,
        "elapsed_ms": 5,
        "truncated": False,
        "error": None,
        "clarify": None,
        "source": "teaching",
        "source_label": "教学业务库",
        "auto_routed": False,
        "route_reason": "统一助手固定教学库",
        "confidence": None,
        "confidence_detail": None,
        "judge_id": None,
        "explanation": {},
        "trace": {"retrieval_used": False},
    }


def _isolate_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(feedback, "FEEDBACK_DIR", tmp_path / "feedback")
    monkeypatch.setattr(examples, "EXAMPLE_DIR", tmp_path / "examples")
    monkeypatch.setattr(governance, "REVIEW_ITEMS_PATH", tmp_path / "review_items.jsonl")
    monkeypatch.setattr(governance, "SETTINGS_PATH", tmp_path / "settings.yaml")


def test_unified_turn_feedback_is_owned_upserted_and_queued(tmp_path, monkeypatch):
    _isolate_files(tmp_path, monkeypatch)
    monkeypatch.setattr(assistant_orchestrator, "ask_service", lambda *a, **k: _legacy_success())
    monkeypatch.setattr(assistant_orchestrator, "select_few_shot_examples", lambda *a, **k: [])

    with TestClient(app) as client:
        answer = client.post(
            "/api/assistant/query",
            headers=_headers("admin"),
            json={
                "question": "反馈测试：按课程统计数据",
                "context": {"page": "assistant"},
                "options": {"preferred_answer_type": "nl2sql"},
            },
        )
        assert answer.status_code == 200
        body = answer.json()
        turn_id = body["turn_id"]
        assert client.post(
            f"/api/assistant/turns/{turn_id}/feedback",
            headers=_headers("stu_zhang"),
            json={"kind": "correct", "sql": body["sql"]},
        ).status_code == 404

        first = client.post(
            f"/api/assistant/turns/{turn_id}/feedback",
            headers=_headers("admin"),
            json={"kind": "correct", "sql": body["sql"]},
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["created"] is True
        assert first_body["item"]["kind"] == "correct"
        assert first_body["review"]["type"] == "example_candidate"

        second = client.post(
            f"/api/assistant/turns/{turn_id}/feedback",
            headers=_headers("admin"),
            json={
                "kind": "incorrect",
                "category": "wrong_aggregation",
                "reason": "聚合口径需要调整",
                "sql": body["sql"],
            },
        )
        assert second.status_code == 200
        second_body = second.json()
        assert second_body["created"] is False
        assert second_body["item"]["id"] == first_body["item"]["id"]
        assert second_body["item"]["kind"] == "incorrect"
        assert second_body["review"]["type"] == "feedback_fix"
        assert len(feedback.list_feedback("teaching")) == 1
        reviews = governance.list_review_items(status="open")
        assert len(reviews) == 1
        assert reviews[0]["payload"]["feedback"]["id"] == first_body["item"]["id"]
        assert client.delete(
            f"/api/assistant/turns/{turn_id}/feedback",
            headers=_headers("stu_zhang"),
        ).status_code == 404
        canceled = client.delete(
            f"/api/assistant/turns/{turn_id}/feedback",
            headers=_headers("admin"),
        )
        assert canceled.status_code == 200
        assert canceled.json()["deleted_reviews"] == 1
        assert feedback.list_feedback("teaching") == []
        assert governance.list_review_items(status="all") == []

        client.delete(
            f"/api/assistant/sessions/{body['session_id']}",
            headers=_headers("admin"),
        )


def test_positive_feedback_can_be_accepted_and_selected_as_authorized_few_shot(
    tmp_path, monkeypatch
):
    _isolate_files(tmp_path, monkeypatch)
    item = feedback.upsert_turn_feedback(
        {
            "source": "teaching",
            "source_label": "教学业务库",
            "kind": "correct",
            "reason": "结果正确",
            "category": "confirmed_example",
            "question": "各学院学生人数是多少？",
            "sql": "SELECT c.name, COUNT(s.id) FROM student s JOIN college c ON s.college_id = c.id GROUP BY c.name",
            "turn_id": 100,
            "submitted_user_id": 1,
            "role_binding_id": 1,
            "explanation": {},
        }
    )[0]
    review = governance.create_feedback_review(item)
    accepted = governance.accept_review_item(review["id"], "example", {"source": "teaching"})
    assert accepted["item"]["status"] == "accepted"

    examples.upsert_example(
        "teaching",
        {
            "id": "forbidden-example",
            "question": "各学院学生人数是多少？",
            "sql": "SELECT * FROM app_user",
            "enabled": True,
        },
    )
    examples.upsert_example(
        "teaching",
        {
            "id": "disabled-example",
            "question": "各学院学生人数是多少？",
            "sql": "SELECT * FROM student",
            "enabled": False,
        },
    )
    selected = examples.select_few_shot_examples(
        "teaching",
        "请统计各学院的学生人数",
        allowed_tables=frozenset({"student", "college"}),
        limit=5,
    )
    assert [entry["id"] for entry in selected] == [review["id"]]
