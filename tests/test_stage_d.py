from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.core.business_domains import token_for
from app.main import app


def test_stage_d_frontend_and_navigation_are_available_to_course_roles():
    root = Path(__file__).parents[1]
    html = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    script = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    api_script = (root / "app" / "static" / "api.js").read_text(encoding="utf-8")
    style = (root / "app" / "static" / "style.css").read_text(encoding="utf-8")
    assert 'id="attendance-view"' in html and 'id="course-questions-view"' in html
    assert 'id="course-session-form"' in html and 'id="course-question-form"' in html
    assert "loadAttendanceWorkspace" in script and "loadCourseQuestions" in script
    assert "saveSessionAttendance" in api_script and "replyCourseQuestion" in api_script
    assert ".stage-d-create[hidden],.stage-d-panel[hidden]{display:none}" in style
    with TestClient(app) as client:
        for username in ("tea_li", "stu_zhang"):
            session = client.get("/api/auth/session", headers={"X-Demo-Token": token_for(username)})
            views = {item["view"] for item in session.json()["user"]["navigation"]}
            assert {"attendance-view", "course-questions-view"}.issubset(views)


def _fixture_scope():
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT tc.id AS class_id, tc.teacher_id, tea.username AS teacher_username,
                   s.id AS student_id, stu.username AS student_username,
                   s2.id AS peer_id, stu2.username AS peer_username
            FROM teaching_class tc
            JOIN staff st ON st.teacher_id = tc.teacher_id
            JOIN person_identity tpi ON tpi.person_type='staff' AND tpi.entity_id=st.id AND tpi.status='verified'
            JOIN app_user tea ON tea.id=tpi.user_id AND tea.status='active'
            JOIN enrollment e ON e.teaching_class_id=tc.id
            JOIN student s ON s.id=e.student_id
            JOIN person_identity spi ON spi.person_type='student' AND spi.entity_id=s.id AND spi.status='verified'
            JOIN app_user stu ON stu.id=spi.user_id AND stu.status='active'
            JOIN enrollment e2 ON e2.teaching_class_id=tc.id AND e2.student_id<>s.id
            JOIN student s2 ON s2.id=e2.student_id
            JOIN person_identity spi2 ON spi2.person_type='student' AND spi2.entity_id=s2.id AND spi2.status='verified'
            JOIN app_user stu2 ON stu2.id=spi2.user_id AND stu2.status='active'
            WHERE tc.id >= 900000
            LIMIT 1
            """
        ).fetchone()
        other_teacher = conn.execute(
            """
            SELECT au.username FROM teaching_class tc
            JOIN staff st ON st.teacher_id=tc.teacher_id
            JOIN person_identity pi ON pi.person_type='staff' AND pi.entity_id=st.id AND pi.status='verified'
            JOIN app_user au ON au.id=pi.user_id AND au.status='active'
            WHERE tc.teacher_id<>? LIMIT 1
            """,
            (row["teacher_id"],),
        ).fetchone()
        counselor = conn.execute(
            """
            SELECT au.username FROM student s
            JOIN counselor_class_group ccg ON ccg.class_group_id=s.class_id
            JOIN staff st ON st.counselor_id=ccg.counselor_id
            JOIN person_identity pi ON pi.person_type='staff' AND pi.entity_id=st.id AND pi.status='verified'
            JOIN app_user au ON au.id=pi.user_id AND au.status='active'
            WHERE s.id=? LIMIT 1
            """,
            (row["student_id"],),
        ).fetchone()
    return dict(row), other_teacher["username"], counselor["username"]


def test_stage_d_attendance_is_session_based_correctable_and_scoped():
    scope, other_teacher, counselor = _fixture_scope()
    teacher_headers = {"X-Demo-Token": token_for(scope["teacher_username"])}
    student_headers = {"X-Demo-Token": token_for(scope["student_username"])}
    with TestClient(app) as client:
        created = client.post(
            f"/api/teaching/classes/{scope['class_id']}/sessions",
            headers=teacher_headers,
            json={"session_date": "2026-07-17", "start_time": "09:00", "end_time": "10:40", "topic": "阶段 D 点名", "classroom": "A101"},
        )
        assert created.status_code == 200
        session_id = created.json()["item"]["id"]
        assert client.post(f"/api/teaching/classes/{scope['class_id']}/sessions", headers=student_headers, json={"session_date": "2026-07-18"}).status_code == 403
        assert client.put(f"/api/teaching/sessions/{session_id}/attendance", headers={"X-Demo-Token": token_for(other_teacher)}, json={"entries": [{"student_id": scope["student_id"], "status": "present"}]}).status_code == 403

        recorded = client.put(f"/api/teaching/sessions/{session_id}/attendance", headers=teacher_headers, json={"entries": [{"student_id": scope["student_id"], "status": "late", "note": "迟到十分钟"}, {"student_id": scope["peer_id"], "status": "present"}]})
        assert recorded.status_code == 200 and recorded.json()["item"]["updated_count"] == 2
        corrected = client.put(f"/api/teaching/sessions/{session_id}/attendance", headers=teacher_headers, json={"entries": [{"student_id": scope["student_id"], "status": "present", "note": "教师核实后修正"}]})
        assert corrected.status_code == 200

        own = client.get(f"/api/teaching/attendance/students/{scope['student_id']}", headers=student_headers)
        assert own.status_code == 200
        fact = next(item for item in own.json()["items"] if item["session_id"] == session_id)
        assert fact["status"] == "present" and fact["note"] == "教师核实后修正"
        assert client.get(f"/api/teaching/attendance/students/{scope['peer_id']}", headers=student_headers).status_code == 403
        counselor_view = client.get(f"/api/teaching/attendance/students/{scope['student_id']}", headers={"X-Demo-Token": token_for(counselor)})
        assert counselor_view.status_code == 200
        counselor_fact = next(item for item in counselor_view.json()["items"] if item["session_id"] == session_id)
        assert "note" not in counselor_fact and counselor_fact["status"] == "present"

    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        audit_actions = {row[0] for row in conn.execute("SELECT action FROM audit_log WHERE resource_type='attendance' AND resource_id IN (SELECT id FROM attendance WHERE course_session_id=?)", (session_id,))}
    assert {"record_attendance", "correct_attendance"}.issubset(audit_actions)


def test_stage_d_questions_support_privacy_reply_followup_and_notification():
    scope, other_teacher, _ = _fixture_scope()
    teacher_headers = {"X-Demo-Token": token_for(scope["teacher_username"])}
    student_headers = {"X-Demo-Token": token_for(scope["student_username"])}
    peer_headers = {"X-Demo-Token": token_for(scope["peer_username"])}
    with TestClient(app) as client:
        public = client.post(f"/api/teaching/classes/{scope['class_id']}/questions", headers=student_headers, json={"title": "公开问题", "body": "索引为什么能加速？", "visibility": "public"})
        private = client.post(f"/api/teaching/classes/{scope['class_id']}/questions", headers=student_headers, json={"title": "私密问题", "body": "请单独指导", "visibility": "private"})
        assert public.status_code == 200 and private.status_code == 200
        assert client.post(f"/api/teaching/classes/{scope['class_id']}/questions", headers=teacher_headers, json={"title": "教师提问", "body": "不应允许", "visibility": "public"}).status_code == 403
        public_id, private_id = public.json()["item"]["id"], private.json()["item"]["id"]

        peer_items = client.get(f"/api/teaching/classes/{scope['class_id']}/questions", headers=peer_headers).json()["items"]
        assert any(item["id"] == public_id for item in peer_items)
        assert all(item["id"] != private_id for item in peer_items)
        assert all("student_id" not in item and item["student_name"] == "课程同学" for item in peer_items)
        assert client.get(f"/api/teaching/questions/{private_id}", headers=peer_headers).status_code == 403
        assert client.get(f"/api/teaching/classes/{scope['class_id']}/questions", headers={"X-Demo-Token": token_for(other_teacher)}).status_code == 403

        replied = client.post(f"/api/teaching/questions/{public_id}/replies", headers=teacher_headers, json={"body": "索引通过减少扫描范围提高查询效率。"})
        assert replied.status_code == 200 and replied.json()["item"]["status"] == "answered"
        notices = client.get("/api/notifications", headers=student_headers).json()["items"]
        assert any(item["type"] == "course_question_reply" and item["resource_id"] == public_id for item in notices)

        followup = client.post(f"/api/teaching/questions/{public_id}/replies", headers=student_headers, json={"body": "那联合索引的顺序如何选择？"})
        assert followup.status_code == 200 and followup.json()["item"]["status"] == "open"
        moderated = client.patch(f"/api/teaching/questions/{public_id}", headers=teacher_headers, json={"status": "closed", "pinned": True})
        assert moderated.status_code == 200 and moderated.json()["item"]["status"] == "closed" and moderated.json()["item"]["pinned"] == 1
        assert client.post(f"/api/teaching/questions/{public_id}/replies", headers=student_headers, json={"body": "关闭后追问"}).status_code == 400
