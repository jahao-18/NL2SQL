from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.core.authorization import connect
from app.core.business_domains import token_for
from app.core.teaching_migrations import ensure_mvp_schema
from app.main import app


def _headers(username: str) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username)}


def _insert_test_case(case_id: int = 990001) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO support_case
            (id, code, student_id, counselor_id, rule_code, title, evidence, status, created_at,
             review_at, closed_reason, visible_to_student, suggested_action, updated_at)
            VALUES (?, ?, 900001, 900001, 'two_missing_assignments_same_course',
                    '阶段3流程测试事项', '{"fact":"连续两次作业未提交"}', 'open', ?,
                    NULL, NULL, 0, '确认原因并制定补交计划。', ?)
            """,
            (case_id, f"TEST-SUP-{case_id}", datetime.now().isoformat(), datetime.now().isoformat()),
        )
        conn.commit()


def _cleanup_test_case(case_id: int = 990001) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM notification WHERE resource_type = 'support_case' AND resource_id = ?", (case_id,))
        conn.execute("DELETE FROM audit_log WHERE resource_type = 'support_case' AND resource_id = ?", (case_id,))
        conn.execute("DELETE FROM support_case_log WHERE case_id = ?", (case_id,))
        conn.execute("DELETE FROM support_case WHERE id = ?", (case_id,))
        conn.commit()


def test_support_case_scope_and_student_privacy():
    ensure_mvp_schema()
    with TestClient(app) as client:
        counselor_cases = client.get("/api/teaching/support/cases", headers=_headers("counselor_chen"))
        assert counselor_cases.status_code == 200
        assert {900001, 900002}.issubset({item["id"] for item in counselor_cases.json()["items"]})

        wrong_counselor = client.get("/api/teaching/support/cases/900001", headers=_headers("counselor_lin"))
        assert wrong_counselor.status_code == 403

        hidden_from_student = client.get("/api/teaching/support/cases/900001", headers=_headers("stu_wang"))
        assert hidden_from_student.status_code == 403

        visible_to_student = client.get("/api/teaching/support/cases/900002", headers=_headers("stu_liu"))
        assert visible_to_student.status_code == 200
        item = visible_to_student.json()["item"]
        assert "logs" not in item
        assert "counselor_id" not in item
        assert "closed_reason" not in item

        teacher_denied = client.get("/api/teaching/support/cases/900001", headers=_headers("tea_li"))
        assert teacher_denied.status_code == 403


def test_counselor_complete_support_case_flow_and_share_to_student():
    ensure_mvp_schema()
    case_id = 990001
    _cleanup_test_case(case_id)
    _insert_test_case(case_id)
    follow_up = (datetime.now() + timedelta(days=7)).replace(microsecond=0).isoformat()
    try:
        with TestClient(app) as client:
            contacted = client.post(
                f"/api/teaching/support/cases/{case_id}/transition",
                headers=_headers("counselor_chen"),
                json={
                    "target_status": "contacted",
                    "note": "已与学生确认近期任务安排。",
                    "contact_method": "phone",
                    "student_feedback": "愿意制定补交计划。",
                    "visible_to_student": True,
                },
            )
            assert contacted.status_code == 200
            assert contacted.json()["item"]["status"] == "contacted"

            student_cases = client.get("/api/teaching/support/cases", headers=_headers("stu_zhang"))
            assert any(item["id"] == case_id for item in student_cases.json()["items"])

            tracking = client.post(
                f"/api/teaching/support/cases/{case_id}/transition",
                headers=_headers("counselor_chen"),
                json={"target_status": "tracking", "note": "约定一周后复查。", "follow_up_at": follow_up},
            )
            assert tracking.status_code == 200
            assert tracking.json()["item"]["review_at"] == follow_up

            improved = client.post(
                f"/api/teaching/support/cases/{case_id}/transition",
                headers=_headers("counselor_chen"),
                json={"target_status": "improved", "note": "后续作业已经按时提交。", "visible_to_student": True},
            )
            assert improved.status_code == 200

            closed = client.post(
                f"/api/teaching/support/cases/{case_id}/transition",
                headers=_headers("counselor_chen"),
                json={"target_status": "closed", "note": "复查完成，学生学习节奏恢复。"},
            )
            assert closed.status_code == 200
            assert closed.json()["item"]["status"] == "closed"
            assert len(closed.json()["item"]["logs"]) == 4
    finally:
        _cleanup_test_case(case_id)


def test_student_request_is_routed_and_counselor_can_reply():
    ensure_mvp_schema()
    request_id = None
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/teaching/support/requests",
                headers=_headers("stu_zhang"),
                json={"request_type": "appointment", "message": "希望沟通学习计划。", "preferred_time": "2026-07-20T15:00:00"},
            )
            assert created.status_code == 200
            request_id = created.json()["item"]["id"]
            assert created.json()["item"]["counselor_id"] == 900001

            counselor_requests = client.get("/api/teaching/support/requests", headers=_headers("counselor_chen"))
            assert any(item["id"] == request_id for item in counselor_requests.json()["items"])

            replied = client.patch(
                f"/api/teaching/support/requests/{request_id}",
                headers=_headers("counselor_chen"),
                json={"status": "accepted", "response": "已安排周一下午沟通。"},
            )
            assert replied.status_code == 200
            assert replied.json()["item"]["status"] == "accepted"

            wrong_student = client.patch(
                f"/api/teaching/support/requests/{request_id}",
                headers=_headers("stu_zhang"),
                json={"status": "completed", "response": "越权操作"},
            )
            assert wrong_student.status_code == 403
    finally:
        if request_id is not None:
            with connect() as conn:
                conn.execute("DELETE FROM notification WHERE resource_type = 'support_request' AND resource_id = ?", (request_id,))
                conn.execute("DELETE FROM audit_log WHERE resource_type = 'support_request' AND resource_id = ?", (request_id,))
                conn.execute("DELETE FROM support_request WHERE id = ?", (request_id,))
                conn.commit()


def test_transparent_rules_create_explainable_case_without_teacher_access():
    ensure_mvp_schema()
    with connect() as conn:
        rows = conn.execute("SELECT id FROM support_case WHERE code LIKE 'AUTO-ABS-900001-900004-%'").fetchall()
        for row in rows:
            conn.execute("DELETE FROM support_case_log WHERE case_id = ?", (row["id"],))
            conn.execute("DELETE FROM support_case WHERE id = ?", (row["id"],))
        conn.commit()
    created_id = None
    try:
        with TestClient(app) as client:
            refreshed = client.post("/api/teaching/support/cases/refresh", headers=_headers("counselor_chen"))
            assert refreshed.status_code == 200
            assert refreshed.json()["created_count"] >= 1
            cases = client.get("/api/teaching/support/cases", headers=_headers("counselor_chen")).json()["items"]
            case = next(item for item in cases if item["rule_code"] == "two_absences_same_course" and item["student_id"] == 900004)
            created_id = case["id"]
            assert case["evidence"]["fact"] == "连续两次缺勤"
            assert "risk_score" not in case["evidence"]
    finally:
        if created_id:
            _cleanup_test_case(created_id)
