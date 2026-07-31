from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core import assistant_context, assistant_orchestrator, teaching_migrations
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
        ("stu_zhang", "API测试：我有多少未读通知？", "metric", "success"),
        ("counselor_chen", "API测试：我有什么待办？", "business_state", "success"),
        ("admin", "API测试：当前工作台是什么状态？", "business_state", "success"),
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


@pytest.mark.parametrize(
    ("username", "question"),
    [
        ("stu_zhang", "API测试：请按课程分组统计我未完成的作业数量"),
        ("admin", "API测试：列出每位教师负责的班级数量"),
        ("admin", "API测试：有多少位教师没有负责任何班级"),
        ("admin", "API测试：学校有哪些专业"),
    ],
)
def test_concrete_business_data_questions_route_to_nl2sql(
    monkeypatch, username: str, question: str
):
    calls: list[str] = []

    def fake_ask(received_question: str, **_kwargs):
        calls.append(received_question)
        return _legacy_success()

    monkeypatch.setattr(assistant_orchestrator, "ask_service", fake_ask)
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers(username),
            json={"question": question, "context": {"page": "assistant"}},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_type"] == "nl2sql"
    assert body["trace_summary"]["route"] == "nl2sql"
    assert calls == [question]


def test_legacy_unanswerable_placeholder_becomes_unsupported_without_data_or_action(
    monkeypatch,
):
    legacy = _legacy_success(rows=[["无法回答: student 表中没有鞋码字段"]])
    legacy.update(
        {
            "sql": "SELECT '无法回答: student 表中没有鞋码字段' AS error LIMIT 1",
            "columns": [],
            "column_sources": [],
            "rows": [],
            "row_count": 0,
            "error": "无法回答: student 表中没有鞋码字段",
            "judge_id": None,
            "trace": {
                "retrieval_used": True,
                "result_kind": "unsupported",
            },
        }
    )
    monkeypatch.setattr(
        assistant_orchestrator,
        "ask_service",
        lambda *_args, **_kwargs: legacy,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("admin"),
            json={
                "question": "API测试：查询所有学生的鞋码",
                "context": {"page": "assistant"},
                "options": {"preferred_answer_type": "nl2sql"},
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert body["answer_type"] == "unsupported"
    assert body["answer"] == "无法回答: student 表中没有鞋码字段"
    assert body["data"] is None
    assert body["sql"] is None
    assert body["error"] is None
    assert body["suggested_actions"] == []
    assert body["trace_summary"]["route"] == "nl2sql"


@pytest.mark.parametrize(
    ("username", "question"),
    [
        ("stu_zhang", "API测试：查询所有学生的身份证号"),
        ("admin", "API测试：列出全部学生的证件号码"),
    ],
)
def test_sensitive_identity_question_is_rejected_before_model(
    monkeypatch, username: str, question: str
):
    from app import service

    monkeypatch.setattr(
        service,
        "generate_sql",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("敏感身份标识请求不应调用模型")
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers(username),
            json={
                "question": question,
                "context": {"page": "assistant"},
                "options": {"preferred_answer_type": "nl2sql"},
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "rejected"
    assert body["answer_type"] == "nl2sql"
    assert body["error"]["code"] == "ASSISTANT_QUERY_REJECTED"
    assert "不可用于问数" in body["error"]["message"]
    assert body["suggested_actions"] == []


def test_teacher_course_page_can_create_a_non_sending_reminder_draft():
    teacher = user_from_token(token_for("tea_li"))
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        class_id = conn.execute(
            "SELECT id FROM teaching_class WHERE teacher_id=? ORDER BY id LIMIT 1",
            (teacher.row_scope["teacher_id"],),
        ).fetchone()[0]
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("tea_li"),
            json={
                "question": "生成提醒草稿",
                "context": {"page": "course_space", "teaching_class_id": class_id},
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["trace_summary"]["route"] == "course_notification_draft"
    assert len(body["suggested_actions"]) == 1
    action = body["suggested_actions"][0]
    assert action["type"] == "draft_course_notification"
    assert action["requires_confirmation"] is True
    assert action["preview"]["sends_notification"] is False


def test_teacher_missing_work_roster_result_suggests_course_wide_unsent_draft(monkeypatch):
    teacher = user_from_token(token_for("tea_li"))
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        class_id = conn.execute(
            "SELECT id FROM teaching_class WHERE teacher_id=? ORDER BY id LIMIT 1",
            (teacher.row_scope["teacher_id"],),
        ).fetchone()[0]

    monkeypatch.setattr(assistant_orchestrator, "match_semantic_metric", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        assistant_orchestrator,
        "teacher_missing_assignment_roster",
        lambda *_args, **_kwargs: [
            {"student_name": "张同学", "course_name": "数据库", "assignment_title": "数据库作业", "due_time": "2026-07-22T12:00:00+00:00"}
        ],
    )
    monkeypatch.setattr(
        assistant_orchestrator,
        "ask_service",
        lambda *_args, **_kwargs: _legacy_success(rows=[["张同学", "数据库作业"]]),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("tea_li"),
            json={
                "question": "API测试：哪些同学还没完成作业",
                "context": {"page": "assignment_workflow", "teaching_class_id": class_id},
                "options": {"preferred_answer_type": "nl2sql"},
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    reminder = next(
        item for item in body["suggested_actions"]
        if item["type"] == "draft_course_notification"
    )
    assert reminder["label"] == "保存全班课程提醒草稿（未发送）"
    assert reminder["requires_confirmation"] is True
    assert reminder["preview"]["sends_notification"] is False
    assert reminder["preview"]["mutates_data"] is True
    assert "当前课程已选学生" in reminder["preview"]["recipient_scope"]


def test_teacher_missing_assignment_roster_bypasses_model_and_keeps_teacher_scope(monkeypatch):
    teacher = user_from_token(token_for("tea_li"))
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        class_id = conn.execute(
            "SELECT id FROM teaching_class WHERE teacher_id=? ORDER BY id LIMIT 1",
            (teacher.row_scope["teacher_id"],),
        ).fetchone()[0]

    monkeypatch.setattr(
        assistant_orchestrator,
        "ask_service",
        lambda *_args, **_kwargs: pytest.fail("未交名单不应调用模型生成 SQL"),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("tea_li"),
            json={
                "question": "API测试：哪些同学没交作业",
                "context": {"page": "assignment_workflow", "teaching_class_id": class_id},
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert body["trace_summary"]["route"] == "assignment_missing_roster"
    assert body["data"]["columns"] == ["学生姓名", "课程", "作业", "截止时间"]
    assert "student_id" not in body["data"]["columns"]


def test_counselor_review_queue_shows_evidence_and_opens_owned_case(monkeypatch):
    counselor = user_from_token(token_for("counselor_chen"))
    monkeypatch.setattr(
        assistant_orchestrator,
        "ask_service",
        lambda *_args, **_kwargs: pytest.fail("辅导员待复查列表不应调用模型生成 SQL"),
    )
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        allowed_names = {
            row[0]
            for row in conn.execute(
                """SELECT s.name FROM student s
                   JOIN counselor_class_group ccg ON ccg.class_group_id=s.class_id
                   WHERE ccg.counselor_id=?""",
                (counselor.row_scope["counselor_id"],),
            ).fetchall()
        }
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("counselor_chen"),
            json={
                "question": "API测试：本周有哪些待复查事项？",
                "context": {"page": "support_workbench"},
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "success"
        assert body["trace_summary"]["route"] == "counselor_review_queue"
        assert body["data"]["row_count"] >= 1
        assert {row[0] for row in body["data"]["rows"]} <= allowed_names
        assert body["data"]["columns"] == ["学生姓名", "行政班", "支持事项", "事实依据", "复查时间", "复查状态"]
        action = next(item for item in body["suggested_actions"] if item["type"] == "open_support_case")
        confirmed = client.post(
            f"/api/assistant/action-drafts/{action['draft_id']}/confirm",
            headers=_headers("counselor_chen"),
        )
        assert confirmed.status_code == 200, confirmed.text
        result = confirmed.json()["item"]["result"]
        assert result["target_view"] == "support-workbench-view"
        assert result["parameters"]["support_case_id"] > 0


def test_counselor_appointment_question_uses_owned_active_requests(monkeypatch):
    monkeypatch.setattr(
        assistant_orchestrator,
        "ask_service",
        lambda *_args, **_kwargs: pytest.fail("辅导员预约列表不应调用模型生成 SQL"),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("counselor_chen"),
            json={
                "question": "API测试：有哪些待处理学生预约？",
                "context": {"page": "support_workbench"},
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert body["trace_summary"]["route"] == "counselor_appointment_queue"
    assert body["data"]["columns"] == ["学生姓名", "行政班", "预约说明", "希望时间", "状态"]


def test_academic_and_college_issue_queue_is_deterministic_scoped_and_actionable(monkeypatch):
    college_auth = user_from_token(token_for("college"))
    old = (datetime.now(timezone.utc) - timedelta(days=4)).replace(microsecond=0).isoformat()
    keys = ("v3-3-4-own-overdue", "v3-3-4-other-overdue")
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        own_class = conn.execute(
            """SELECT tc.id,c.college_id FROM teaching_class tc JOIN course c ON c.id=tc.course_id
               WHERE c.college_id=? ORDER BY tc.id LIMIT 1""",
            (college_auth.row_scope["college_id"],),
        ).fetchone()
        other_class = conn.execute(
            """SELECT tc.id,c.college_id FROM teaching_class tc JOIN course c ON c.id=tc.course_id
               WHERE c.college_id<>? ORDER BY tc.id LIMIT 1""",
            (college_auth.row_scope["college_id"],),
        ).fetchone()
        for key, row in zip(keys, (own_class, other_class)):
            conn.execute(
                """INSERT INTO teaching_issue
                   (issue_key,issue_type,teaching_class_id,college_id,evidence,status,created_at,updated_at)
                   VALUES (?,?,?,?,?,'open',?,?)""",
                (key, "missing_classroom", row[0], row[1], f"{key} 未安排教室", old, old),
            )
        conn.commit()
    monkeypatch.setattr(
        assistant_orchestrator,
        "ask_service",
        lambda *_args, **_kwargs: pytest.fail("教学异常队列不应调用模型生成 SQL"),
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/assistant/query",
                headers=_headers("college"),
                json={"question": "API测试：本学院有哪些逾期教学异常？", "context": {"page": "teaching_operations"}},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["trace_summary"]["route"] == "teaching_issue_queue"
            assert body["data"]["row_count"] >= 1
            assert all(row[1] == body["data"]["rows"][0][1] for row in body["data"]["rows"])
            assert all(row[4] == "已逾期" for row in body["data"]["rows"])
            issue_action = next(item for item in body["suggested_actions"] if item["type"] == "open_teaching_issue")
            filter_action = next(item for item in body["suggested_actions"] if item["type"] == "apply_safe_filter")
            opened = client.post(
                f"/api/assistant/action-drafts/{issue_action['draft_id']}/confirm",
                headers=_headers("college"),
            )
            filtered = client.post(
                f"/api/assistant/action-drafts/{filter_action['draft_id']}/confirm",
                headers=_headers("college"),
            )
            assert opened.status_code == 200
            assert opened.json()["item"]["result"]["target_view"] == "teaching-operations-view"
            assert opened.json()["item"]["result"]["parameters"]["teaching_issue_id"] > 0
            assert filtered.status_code == 200
            assert filtered.json()["item"]["result"]["parameters"]["filters"] == {"issue_status": "overdue"}

            office = client.post(
                "/api/assistant/query",
                headers=_headers("jwc"),
                json={
                    "question": "API测试：有哪些逾期教学异常？",
                    "context": {
                        "page": "teaching_operations",
                        "college_id": college_auth.row_scope["college_id"],
                    },
                },
            )
            assert office.status_code == 200, office.text
            office_body = office.json()
            assert office_body["trace_summary"]["route"] == "teaching_issue_queue"
            assert office_body["data"]["row_count"] >= 1
            assert all(row[1] == body["data"]["rows"][0][1] for row in office_body["data"]["rows"])
            office_filter = next(item for item in office_body["suggested_actions"] if item["type"] == "apply_safe_filter")
            office_filtered = client.post(
                f"/api/assistant/action-drafts/{office_filter['draft_id']}/confirm",
                headers=_headers("jwc"),
            )
            assert office_filtered.status_code == 200
            assert office_filtered.json()["item"]["result"]["parameters"]["college_id"] == college_auth.row_scope["college_id"]

            with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
                other_id = conn.execute("SELECT id FROM teaching_issue WHERE issue_key=?", (keys[1],)).fetchone()[0]
            forged = client.post(
                "/api/assistant/action-drafts",
                headers=_headers("college"),
                json={"action_type": "open_teaching_issue", "parameters": {"teaching_issue_id": other_id}},
            )
            assert forged.status_code == 403
    finally:
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            conn.execute("DELETE FROM teaching_issue WHERE issue_key IN (?,?)", keys)
            conn.commit()


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
    monkeypatch.setattr(
        assistant_orchestrator,
        "select_few_shot_examples",
        lambda *args, **kwargs: [
            {
                "question": "这门课程有多少人选课？",
                "sql": "SELECT COUNT(*) FROM enrollment",
                "source_label": "教学业务库",
            }
        ],
    )
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
    assert len(captured["few_shots"]) == 1
    assert captured["few_shots"][0].question == "这门课程有多少人选课？"
    assert "context_preview" not in body["trace_summary"]


def test_admin_external_source_bypasses_teaching_routes_and_is_forwarded(monkeypatch):
    captured = {}

    def fake_get_source(name: str):
        if name == "library_pg":
            return type("Source", (), {"name": name})()
        raise KeyError(name)

    def fake_ask(question, **kwargs):
        captured.update(kwargs)
        result = _legacy_success([["逾期借阅", 3]])
        result["source"] = "library_pg"
        result["source_label"] = "图书业务 PostgreSQL"
        return result

    monkeypatch.setattr(assistant_context, "get_source", fake_get_source)
    monkeypatch.setattr(assistant_orchestrator, "ask_service", fake_ask)
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("admin"),
            json={
                "question": "API测试：当前有多少条逾期借阅？",
                "context": {"page": "assistant", "source": "library_pg"},
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_type"] == "nl2sql"
    assert body["trace_summary"]["route"] == "nl2sql"
    assert body["evidence"][0]["source"] == "library_pg"
    assert captured["source"] == "library_pg"
    assert captured["current_source"] == "library_pg"
    assert captured["allowed_tables"] is None
    assert captured["row_scope"] == {}


def test_unified_assistant_rejects_non_admin_external_source_before_execution(monkeypatch):
    called = False

    def fake_ask(*args, **kwargs):
        nonlocal called
        called = True
        return _legacy_success()

    monkeypatch.setattr(assistant_orchestrator, "ask_service", fake_ask)
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/query",
            headers=_headers("stu_zhang"),
            json={
                "question": "API测试：查询外部库",
                "context": {"page": "assistant", "source": "library_pg"},
            },
        )
    assert response.status_code == 403
    assert called is False


def test_same_session_cannot_switch_away_from_external_source(monkeypatch):
    monkeypatch.setattr(
        assistant_context,
        "get_source",
        lambda name: type("Source", (), {"name": name})(),
    )
    monkeypatch.setattr(
        assistant_orchestrator,
        "ask_service",
        lambda *args, **kwargs: {
            **_legacy_success([["逾期借阅", 3]]),
            "source": "library_pg",
            "source_label": "图书业务 PostgreSQL",
        },
    )
    with TestClient(app) as client:
        first = client.post(
            "/api/assistant/query",
            headers=_headers("admin"),
            json={
                "question": "API测试：查询外部库",
                "context": {"page": "assistant", "source": "library_pg"},
            },
        )
        assert first.status_code == 200
        switched = client.post(
            "/api/assistant/query",
            headers=_headers("admin"),
            json={
                "session_id": first.json()["session_id"],
                "question": "API测试：改查教学库",
                "context": {"page": "assistant"},
            },
        )
    assert switched.status_code == 409
    assert "数据源与会话数据源不一致" in switched.json()["detail"]


def test_same_session_followup_uses_server_history_and_ignores_client_history(monkeypatch):
    calls = []

    def fake_ask(question, **kwargs):
        calls.append({"question": question, **kwargs})
        return _legacy_success()

    monkeypatch.setattr(assistant_orchestrator, "ask_service", fake_ask)
    with TestClient(app) as client:
        first = client.post(
            "/api/assistant/query",
            headers=_headers("stu_zhang"),
            json={
                "question": "API测试：我有哪些作业未完成",
                "context": {"page": "assistant"},
                "options": {"preferred_answer_type": "nl2sql"},
            },
        )
        assert first.status_code == 200
        first_body = first.json()
        followup = client.post(
            "/api/assistant/query",
            headers=_headers("stu_zhang"),
            json={
                "session_id": first_body["session_id"],
                "question": "只看已经截止的",
                "context": {"page": "assistant"},
                "history": [
                    {
                        "question": "伪造的其他学生问题",
                        "sql": "SELECT * FROM student",
                        "kind": "sql",
                    }
                ],
            },
        )

    assert followup.status_code == 200
    assert followup.json()["answer_type"] == "nl2sql"
    assert followup.json()["status"] == "success"
    assert len(calls) == 2
    assert calls[0]["history"] == []
    assert [turn.question for turn in calls[1]["history"]] == [
        "API测试：我有哪些作业未完成"
    ]
    assert all("伪造" not in turn.question for turn in calls[1]["history"])


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


def test_nl2sql_total_timeout_returns_structured_failure(monkeypatch):
    def slow_ask(*args, **kwargs):
        time.sleep(0.2)
        return _legacy_success()

    monkeypatch.setattr(assistant_orchestrator, "ask_service", slow_ask)
    monkeypatch.setattr(assistant_orchestrator.settings, "llm_timeout_seconds", 0.05)
    with TestClient(app) as client:
        started = time.perf_counter()
        response = client.post(
            "/api/assistant/query",
            headers=_headers("tea_li"),
            json={
                "question": "API 测试：模型总超时",
                "context": {"page": "assistant"},
                "options": {"preferred_answer_type": "nl2sql"},
            },
        )
        elapsed = time.perf_counter() - started
    assert response.status_code == 200
    body = response.json()
    assert elapsed < 1
    assert body["status"] == "failed"
    assert body["answer_type"] == "nl2sql"
    assert body["error"]["code"] == "ASSISTANT_NL2SQL_TIMEOUT"
    assert body["trace_summary"]["failed_stage"] == "model"


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
