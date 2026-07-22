from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.core.action_drafts import ACTION_TYPES, PARAMETER_MODELS, _course_reminder_proposal
from app.core.business_domains import token_for, user_from_token
from app.main import app


TITLE_PREFIX = "V3-2.3 测试通知"


def _headers(username: str, role_binding_id: int | None = None) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username, role_binding_id)}


@pytest.fixture(autouse=True)
def clean_action_drafts():
    _clean()
    yield
    _clean()


def _clean() -> None:
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.execute("DELETE FROM assistant_action_draft")
        conn.execute("DELETE FROM course_announcement WHERE title LIKE ?", (f"{TITLE_PREFIX}%",))
        conn.commit()


def _teacher_class_ids() -> tuple[int, int]:
    auth = user_from_token(token_for("tea_li"))
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        own = conn.execute(
            "SELECT id FROM teaching_class WHERE teacher_id=? ORDER BY id LIMIT 1",
            (auth.row_scope["teacher_id"],),
        ).fetchone()[0]
        other = conn.execute(
            "SELECT id FROM teaching_class WHERE teacher_id<>? ORDER BY id LIMIT 1",
            (auth.row_scope["teacher_id"],),
        ).fetchone()[0]
    return int(own), int(other)


def test_result_linked_reminder_requires_teacher_course_risk_roster_with_rows():
    teacher = user_from_token(token_for("tea_li"))
    student = user_from_token(token_for("stu_zhang"))
    own, _ = _teacher_class_ids()
    context = {"page": "assignment_workflow", "teaching_class_id": own}
    result = {
        "status": "success",
        "answer_type": "nl2sql",
        "data": {"row_count": 1},
    }

    assert _course_reminder_proposal(teacher, "哪些同学未交作业", context, result) is not None
    assert _course_reminder_proposal(student, "哪些同学未交作业", context, result) is None
    assert _course_reminder_proposal(teacher, "这门课有多少学生", context, result) is None
    assert _course_reminder_proposal(
        teacher,
        "哪些同学未交作业",
        context,
        {**result, "data": {"row_count": 0}},
    ) is None
    assert _course_reminder_proposal(
        teacher,
        "哪些同学未交作业",
        {"page": "assistant"},
        result,
    ) is None


def _create_notification(client: TestClient, class_id: int) -> dict:
    response = client.post(
        "/api/assistant/action-drafts",
        headers=_headers("tea_li"),
        json={
            "action_type": "draft_course_notification",
            "parameters": {
                "teaching_class_id": class_id,
                "title": f"{TITLE_PREFIX}：数据库课程",
                "body": "这只是待确认的通知草稿。",
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["item"]


def test_allowlist_is_exact_and_unknown_action_or_extra_parameter_is_rejected():
    assert set(PARAMETER_MODELS) == set(ACTION_TYPES) == {
        "open_assignment_roster",
        "open_course",
        "open_support_case",
        "open_teaching_issue",
        "apply_safe_filter",
        "draft_course_notification",
        "submit_governance_feedback",
        "export_current_result",
    }
    own, _ = _teacher_class_ids()
    with TestClient(app) as client:
        unknown = client.post(
            "/api/assistant/action-drafts",
            headers=_headers("tea_li"),
            json={"action_type": "publish_grades", "parameters": {}},
        )
        extra = client.post(
            "/api/assistant/action-drafts",
            headers=_headers("tea_li"),
            json={"action_type": "open_course", "parameters": {"teaching_class_id": own, "is_admin": True}},
        )
    assert unknown.status_code == 422
    assert extra.status_code == 400


def test_forged_course_is_rejected_when_draft_is_created():
    _, other = _teacher_class_ids()
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/action-drafts",
            headers=_headers("tea_li"),
            json={"action_type": "open_course", "parameters": {"teaching_class_id": other}},
        )
    assert response.status_code == 403


def test_tampered_parameters_are_reauthorized_at_confirmation():
    own, other = _teacher_class_ids()
    with TestClient(app) as client:
        created = client.post(
            "/api/assistant/action-drafts",
            headers=_headers("tea_li"),
            json={"action_type": "open_course", "parameters": {"teaching_class_id": own}},
        ).json()["item"]
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            conn.execute(
                "UPDATE assistant_action_draft SET parameters_json=? WHERE id=?",
                (json.dumps({"teaching_class_id": other}), created["id"]),
            )
            conn.commit()
        confirmed = client.post(
            f"/api/assistant/action-drafts/{created['id']}/confirm",
            headers=_headers("tea_li"),
        )
    assert confirmed.status_code == 403
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        assert conn.execute("SELECT status FROM assistant_action_draft WHERE id=?", (created["id"],)).fetchone()[0] == "pending"


def test_expired_draft_cannot_be_confirmed():
    own, _ = _teacher_class_ids()
    with TestClient(app) as client:
        created = client.post(
            "/api/assistant/action-drafts",
            headers=_headers("tea_li"),
            json={"action_type": "open_course", "parameters": {"teaching_class_id": own}},
        ).json()["item"]
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            conn.execute("UPDATE assistant_action_draft SET expires_at=? WHERE id=?", (expired, created["id"]))
            conn.commit()
        response = client.post(
            f"/api/assistant/action-drafts/{created['id']}/confirm",
            headers=_headers("tea_li"),
        )
    assert response.status_code == 410
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        assert conn.execute("SELECT status FROM assistant_action_draft WHERE id=?", (created["id"],)).fetchone()[0] == "expired"


def test_notification_requires_confirmation_stays_draft_and_cannot_repeat():
    own, _ = _teacher_class_ids()
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        student_username = conn.execute(
            """SELECT au.username FROM enrollment e
               JOIN person_identity pi ON pi.person_type='student' AND pi.entity_id=e.student_id AND pi.status='verified'
               JOIN app_user au ON au.id=pi.user_id
               WHERE e.teaching_class_id=? ORDER BY au.id LIMIT 1""",
            (own,),
        ).fetchone()[0]
    with TestClient(app) as client:
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            notification_count = conn.execute("SELECT count(*) FROM notification").fetchone()[0]
        draft = _create_notification(client, own)
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            assert conn.execute("SELECT count(*) FROM course_announcement WHERE title LIKE ?", (f"{TITLE_PREFIX}%",)).fetchone()[0] == 0
            assert conn.execute("SELECT count(*) FROM notification").fetchone()[0] == notification_count
        confirmed = client.post(
            f"/api/assistant/action-drafts/{draft['id']}/confirm", headers=_headers("tea_li")
        )
        repeated = client.post(
            f"/api/assistant/action-drafts/{draft['id']}/confirm", headers=_headers("tea_li")
        )
    assert confirmed.status_code == 200
    item = confirmed.json()["item"]
    assert item["status"] == "confirmed" and item["result"]["sent"] is False
    assert repeated.status_code == 409
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        announcement = conn.execute("SELECT status,published_at FROM course_announcement WHERE id=?", (item["result"]["resource_id"],)).fetchone()
        assert announcement == ("draft", None)
        assert conn.execute("SELECT count(*) FROM notification").fetchone()[0] == notification_count
    with TestClient(app) as client:
        teacher_space = client.get(
            f"/api/teaching/classes/{own}/space", headers=_headers("tea_li")
        )
        assert teacher_space.status_code == 200
        assert any(draft["id"] == item["result"]["resource_id"] for draft in teacher_space.json()["item"]["announcement_drafts"])
        student_space = client.get(
            f"/api/teaching/classes/{own}/space", headers=_headers(student_username)
        )
        assert student_space.status_code == 200
        assert student_space.json()["item"]["announcement_drafts"] == []
        published = client.post(
            f"/api/teaching/announcements/{item['result']['resource_id']}/publish",
            headers=_headers("tea_li"),
        )
        assert published.status_code == 200, published.text
        assert published.json()["item"]["published"] is True
        assert client.post(
            f"/api/teaching/announcements/{item['result']['resource_id']}/publish",
            headers=_headers("tea_li"),
        ).status_code == 400
        assert any(
            notice["resource_id"] == item["result"]["resource_id"]
            for notice in client.get("/api/notifications", headers=_headers(student_username)).json()["items"]
        )


def test_switching_role_binding_cannot_confirm_old_draft():
    own, _ = _teacher_class_ids()
    teacher = user_from_token(token_for("tea_li"))
    counselor_binding = next(item for item in teacher.available_roles if item["role"] == "counselor")
    with TestClient(app) as client:
        created = client.post(
            "/api/assistant/action-drafts",
            headers=_headers("tea_li", teacher.role_binding_id),
            json={"action_type": "open_course", "parameters": {"teaching_class_id": own}},
        ).json()["item"]
        response = client.post(
            f"/api/assistant/action-drafts/{created['id']}/confirm",
            headers=_headers("tea_li", counselor_binding["id"]),
        )
    assert response.status_code == 404


def test_unified_assistant_returns_persisted_confirmable_export_draft():
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("tea_li"),
            json={
                "question": "V3-2.3 动作草稿测试",
                "context": {"page": "assistant"},
                "options": {"preferred_answer_type": "metric"},
            },
        )
        assert response.status_code == 200, response.text
        action = next(item for item in response.json()["suggested_actions"] if item["type"] == "export_current_result")
        detail = client.get(
            f"/api/assistant/action-drafts/{action['draft_id']}", headers=_headers("tea_li")
        )
    assert detail.status_code == 200
    assert detail.json()["item"]["turn_id"] == response.json()["turn_id"]
    assert detail.json()["item"]["status"] == "pending"


def test_deleting_session_cancels_its_pending_action_drafts():
    with TestClient(app) as client:
        queried = client.post(
            "/api/assistant/query",
            headers=_headers("tea_li"),
            json={
                "question": "V3-2.3 会话删除测试",
                "context": {"page": "assistant"},
                "options": {"preferred_answer_type": "metric"},
            },
        ).json()
        action = next(item for item in queried["suggested_actions"] if item["type"] == "export_current_result")
        deleted = client.delete(
            f"/api/assistant/sessions/{queried['session_id']}", headers=_headers("tea_li")
        )
        detail = client.get(
            f"/api/assistant/action-drafts/{action['draft_id']}", headers=_headers("tea_li")
        )
        confirmed = client.post(
            f"/api/assistant/action-drafts/{action['draft_id']}/confirm", headers=_headers("tea_li")
        )
    assert deleted.status_code == 200
    assert detail.json()["item"]["status"] == "canceled"
    assert confirmed.status_code == 409
