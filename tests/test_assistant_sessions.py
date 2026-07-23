from __future__ import annotations

import sqlite3

import pytest

from app.core import teaching_migrations
from app.core.assistant_context import AssistantContextAuthorizationError
from app.core.assistant_sessions import (
    AssistantSessionNotFoundError,
    append_turn,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    update_session,
)
from app.core.business_domains import switch_role, token_for, user_from_token


REQUEST_PREFIX = "test-v3-1-2-"


@pytest.fixture(autouse=True)
def clean_assistant_test_sessions():
    _clean_sessions()
    yield
    _clean_sessions()


def _clean_sessions() -> None:
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        ids = [
            row[0]
            for row in conn.execute(
                "SELECT id FROM assistant_session WHERE client_request_id LIKE ?",
                (f"{REQUEST_PREFIX}%",),
            ).fetchall()
        ]
        if ids:
            marks = ",".join("?" for _ in ids)
            conn.execute(
                f"DELETE FROM assistant_saved_query WHERE session_id IN ({marks})", ids
            )
            conn.execute(f"DELETE FROM assistant_turn WHERE session_id IN ({marks})", ids)
            conn.execute(f"DELETE FROM assistant_session WHERE id IN ({marks})", ids)
        conn.commit()


def _auth(username: str):
    return user_from_token(token_for(username))


def _create_admin_session(auth, suffix: str, title: str | None = None):
    return create_session(
        auth,
        {
            "title": title or f"测试会话 {suffix}",
            "context": {"page": "assistant", "filters": {"topic": suffix}},
            "client_request_id": f"{REQUEST_PREFIX}{suffix}",
        },
    )


def test_create_list_update_and_duplicate_request_are_stable():
    auth = _auth("admin")
    first = _create_admin_session(auth, "create-0001")
    duplicate = _create_admin_session(auth, "create-0001", "不会覆盖原会话")
    _create_admin_session(auth, "create-0002")
    _create_admin_session(auth, "create-0003")

    assert duplicate["id"] == first["id"]
    assert duplicate["title"] == first["title"]
    page_one = list_sessions(auth, page=1, page_size=2)
    page_two = list_sessions(auth, page=2, page_size=2)
    assert page_one["total"] == 3
    assert len(page_one["items"]) == 2
    assert len(page_two["items"]) == 1
    assert {item["id"] for item in page_one["items"]}.isdisjoint(
        {item["id"] for item in page_two["items"]}
    )

    updated = update_session(
        auth, first["id"], {"title": "  数据库课程追踪  ", "is_favorite": True}
    )
    assert updated["title"] == "数据库课程追踪"
    assert updated["is_favorite"] is True
    assert list_sessions(auth)["items"][0]["id"] == first["id"]


def test_turns_are_paginated_and_idempotent_without_large_results():
    auth = _auth("admin")
    session = _create_admin_session(auth, "turns-0001")
    first = append_turn(
        auth,
        session["id"],
        {
            "question": "本学期课程数量是多少？",
            "answer_type": "metric",
            "status": "success",
            "safe_answer_summary": "已返回经过权限过滤的课程数量。",
            "context": {"page": "assistant"},
            "client_request_id": f"{REQUEST_PREFIX}turn-0001",
        },
    )
    duplicate = append_turn(
        auth,
        session["id"],
        {
            "question": "重复请求不会生成新轮次",
            "answer_type": "metric",
            "status": "success",
            "context": {"page": "assistant"},
            "client_request_id": f"{REQUEST_PREFIX}turn-0001",
        },
    )
    second = append_turn(
        auth,
        session["id"],
        {
            "question": "哪些课程需要关注？",
            "answer_type": "business_state",
            "status": "degraded",
            "context": {"page": "assistant"},
            "client_request_id": f"{REQUEST_PREFIX}turn-0002",
        },
    )

    assert duplicate["id"] == first["id"]
    assert second["sequence_no"] == 2
    detail_one = get_session(auth, session["id"], turn_page=1, turn_page_size=1)
    detail_two = get_session(auth, session["id"], turn_page=2, turn_page_size=1)
    assert detail_one["turns"]["total"] == 2
    assert detail_one["turns"]["items"][0]["sequence_no"] == 1
    assert detail_two["turns"]["items"][0]["sequence_no"] == 2
    assert detail_two["item"]["last_question"] == "哪些课程需要关注？"

    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(assistant_turn)")
        }
    assert not {"result", "result_rows", "attachment", "answer_body"} & columns
    assert "safe_answer_summary" in columns


def test_session_is_invisible_to_another_user_and_work_identity():
    teacher = _auth("tea_li")
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        class_id = conn.execute(
            "SELECT id FROM teaching_class WHERE teacher_id = ? ORDER BY id LIMIT 1",
            (teacher.row_scope["teacher_id"],),
        ).fetchone()[0]
    session = create_session(
        teacher,
        {
            "title": "本人课程会话",
            "context": {"page": "course_analytics", "teaching_class_id": class_id},
            "client_request_id": f"{REQUEST_PREFIX}identity-0001",
        },
    )

    with pytest.raises(AssistantSessionNotFoundError):
        get_session(_auth("stu_zhang"), session["id"])
    counselor_binding = next(
        item for item in teacher.available_roles if item["role"] == "counselor"
    )
    counselor, _ = switch_role(teacher, counselor_binding["id"])
    with pytest.raises(AssistantSessionNotFoundError):
        get_session(counselor, session["id"])
    assert list_sessions(counselor)["total"] == 0


def test_suspended_account_cannot_read_sessions():
    auth = _auth("stu_zhang")
    session = create_session(
        auth,
        {
            "title": "冻结校验",
            "context": {"page": "assistant"},
            "client_request_id": f"{REQUEST_PREFIX}suspend-0001",
        },
    )
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        original = conn.execute(
            "SELECT status FROM app_user WHERE id = ?", (auth.user_id,)
        ).fetchone()[0]
        conn.execute("UPDATE app_user SET status = 'suspended' WHERE id = ?", (auth.user_id,))
        conn.commit()
    try:
        with pytest.raises(AssistantContextAuthorizationError):
            get_session(auth, session["id"])
    finally:
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            conn.execute("UPDATE app_user SET status = ? WHERE id = ?", (original, auth.user_id))
            conn.commit()


def test_soft_delete_is_repeatable_and_blocks_reads_and_new_turns():
    auth = _auth("admin")
    session = _create_admin_session(auth, "delete-0001")

    first = delete_session(auth, session["id"])
    second = delete_session(auth, session["id"])
    assert first == {"deleted": True, "already_deleted": False, "id": session["id"]}
    assert second == {"deleted": True, "already_deleted": True, "id": session["id"]}
    assert list_sessions(auth)["total"] == 0
    with pytest.raises(AssistantSessionNotFoundError):
        get_session(auth, session["id"])
    with pytest.raises(AssistantSessionNotFoundError):
        append_turn(
            auth,
            session["id"],
            {
                "question": "删除后不能继续提问",
                "answer_type": "unsupported",
                "status": "rejected",
                "context": {"page": "assistant"},
            },
        )


def test_assistant_tables_have_owner_indexes_timestamps_and_foreign_keys():
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        for table in ("assistant_session", "assistant_turn", "assistant_saved_query"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            foreign_keys = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
            indexes = conn.execute(f"PRAGMA index_list({table})").fetchall()
            assert {"created_at", "updated_at"} <= columns
            assert foreign_keys
            assert indexes
        conn.execute("PRAGMA foreign_keys = ON")
        users = conn.execute(
            """
            SELECT au.id, urb.id FROM app_user au
            JOIN user_role_binding urb ON urb.user_id = au.id
            WHERE urb.status = 'active' GROUP BY au.id ORDER BY au.id LIMIT 2
            """
        ).fetchall()
        assert len(users) == 2 and users[0][0] != users[1][0]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO assistant_session
                    (user_id, role_binding_id, title, page, context_summary,
                     created_at, updated_at)
                VALUES (?, ?, '错误身份组合', 'assistant', '{}', datetime('now'), datetime('now'))
                """,
                (users[0][0], users[1][1]),
            )
