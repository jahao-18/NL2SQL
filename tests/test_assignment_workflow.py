from __future__ import annotations

import base64
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.core.business_domains import token_for
from app.core.teaching_migrations import ensure_mvp_schema
from app.main import app


def test_stage2_assignment_submit_return_resubmit_grade_publish_flow():
    ensure_mvp_schema()
    due_time = (datetime.now() + timedelta(days=30)).replace(microsecond=0).isoformat()

    with TestClient(app) as client:
        teacher_token = token_for("tea_li")
        student_token = token_for("stu_zhang")

        created = client.post(
            "/api/teaching/classes/900001/assignments",
            headers={"X-Demo-Token": teacher_token},
            json={
                "title": "阶段2工作流测试作业",
                "instructions": "提交一个简短说明。",
                "due_time": due_time,
                "max_score": 100,
                "allow_late": True,
            },
        )
        assert created.status_code == 200
        assignment_id = created.json()["item"]["id"]

        todos = client.get("/api/teaching/assignments/my", headers={"X-Demo-Token": student_token})
        assert todos.status_code == 200
        assert any(item["id"] == assignment_id for item in todos.json()["items"])

        submitted = client.post(
            f"/api/teaching/assignments/{assignment_id}/submit",
            headers={"X-Demo-Token": student_token},
            json={
                "content": "第一次提交",
                "file_name": "stage2-v1.pdf",
                "file_content_base64": base64.b64encode(b"version 1").decode("ascii"),
            },
        )
        assert submitted.status_code == 200
        submission = submitted.json()["item"]
        submission_id = submission["id"]
        assert submission["status"] == "submitted"
        assert submission["versions"][0]["version_no"] == 1

        returned = client.post(
            f"/api/teaching/submissions/{submission_id}/return",
            headers={"X-Demo-Token": teacher_token},
            json={"feedback": "请补充 ER 图说明。"},
        )
        assert returned.status_code == 200
        assert returned.json()["item"]["status"] == "returned"

        resubmitted = client.post(
            f"/api/teaching/assignments/{assignment_id}/submit",
            headers={"X-Demo-Token": student_token},
            json={
                "content": "补交版本",
                "file_name": "stage2-v2.pdf",
                "file_content_base64": base64.b64encode(b"version 2").decode("ascii"),
            },
        )
        assert resubmitted.status_code == 200
        assert resubmitted.json()["item"]["status"] == "resubmitted"
        assert len(resubmitted.json()["item"]["versions"]) == 2

        graded = client.post(
            f"/api/teaching/submissions/{submission_id}/grade",
            headers={"X-Demo-Token": teacher_token},
            json={"score": 86, "feedback": "补充后达到要求。"},
        )
        assert graded.status_code == 200
        assert graded.json()["item"]["status"] == "graded_unpublished"
        assert graded.json()["item"]["grade"]["published"] == 0

        hidden = client.get(f"/api/teaching/submissions/{submission_id}", headers={"X-Demo-Token": student_token})
        assert hidden.status_code == 200
        assert hidden.json()["item"]["grade"]["published"] == 0
        assert "score" not in hidden.json()["item"]["grade"]

        published = client.post(
            f"/api/teaching/assignments/{assignment_id}/publish-grades",
            headers={"X-Demo-Token": teacher_token},
        )
        assert published.status_code == 200
        assert published.json()["published_count"] == 1

        visible = client.get(f"/api/teaching/submissions/{submission_id}", headers={"X-Demo-Token": student_token})
        assert visible.status_code == 200
        assert visible.json()["item"]["status"] == "graded_published"
        assert visible.json()["item"]["grade"]["score"] == 86


def test_stage2_assignment_write_permissions_are_server_enforced():
    ensure_mvp_schema()
    with TestClient(app) as client:
        student_token = token_for("stu_zhang")
        other_teacher_token = token_for("tea_zhou")

        create_as_student = client.post(
            "/api/teaching/classes/900001/assignments",
            headers={"X-Demo-Token": student_token},
            json={"title": "越权作业", "due_time": "2026-12-31T23:59:00"},
        )
        assert create_as_student.status_code == 403

        grade_other_teacher_submission = client.post(
            "/api/teaching/submissions/900001/grade",
            headers={"X-Demo-Token": other_teacher_token},
            json={"score": 90, "feedback": "越权评分"},
        )
        assert grade_other_teacher_submission.status_code == 403


def test_teacher_workspace_uses_real_class_scope_and_complete_roster():
    ensure_mvp_schema()
    due_time = (datetime.now() + timedelta(days=20)).replace(microsecond=0).isoformat()
    with TestClient(app) as client:
        teacher_token = token_for("tea_li")
        other_teacher_token = token_for("tea_zhou")

        own_classes = client.get("/api/teaching/classes", headers={"X-Demo-Token": teacher_token})
        assert own_classes.status_code == 200
        assert {item["id"] for item in own_classes.json()["items"]} == {900001}

        other_classes = client.get("/api/teaching/classes", headers={"X-Demo-Token": other_teacher_token})
        assert {item["id"] for item in other_classes.json()["items"]} == {900002}

        draft = client.post(
            "/api/teaching/classes/900001/assignments",
            headers={"X-Demo-Token": teacher_token},
            json={"title": "完整花名册测试", "due_time": due_time, "status": "draft"},
        )
        assignment_id = draft.json()["item"]["id"]
        roster = client.get(
            f"/api/teaching/assignments/{assignment_id}/roster",
            headers={"X-Demo-Token": teacher_token},
        )
        assert roster.status_code == 200
        assert len(roster.json()["items"]) == 4
        assert {item["status"] for item in roster.json()["items"]} == {"missing"}

        updated = client.put(
            f"/api/teaching/assignments/{assignment_id}",
            headers={"X-Demo-Token": teacher_token},
            json={"title": "完整花名册测试（已修改）", "due_time": due_time, "status": "draft"},
        )
        assert updated.status_code == 200
        assert updated.json()["item"]["title"].endswith("（已修改）")

        published = client.post(
            f"/api/teaching/assignments/{assignment_id}/publish",
            headers={"X-Demo-Token": teacher_token},
        )
        assert published.status_code == 200
        assert published.json()["item"]["status"] == "published"


def test_real_attachment_is_stored_and_authorized_for_download():
    ensure_mvp_schema()
    due_time = (datetime.now() + timedelta(days=25)).replace(microsecond=0).isoformat()
    content = b"stage2 attachment content"
    with TestClient(app) as client:
        teacher_token = token_for("tea_li")
        student_token = token_for("stu_zhang")
        outsider_token = token_for("stu_zhao")
        created = client.post(
            "/api/teaching/classes/900001/assignments",
            headers={"X-Demo-Token": teacher_token},
            json={"title": "附件上传测试", "due_time": due_time},
        )
        assignment_id = created.json()["item"]["id"]
        submitted = client.post(
            f"/api/teaching/assignments/{assignment_id}/submit",
            headers={"X-Demo-Token": student_token},
            json={
                "content": "见附件",
                "file_name": "answer.txt",
                "file_content_base64": base64.b64encode(content).decode("ascii"),
            },
        )
        submission_id = submitted.json()["item"]["id"]
        student_items = client.get(
            "/api/teaching/assignments/my",
            headers={"X-Demo-Token": student_token},
        ).json()["items"]
        student_item = next(item for item in student_items if item["id"] == assignment_id)
        assert student_item["latest_file_name"] == "answer.txt"
        assert student_item["latest_content"] == "见附件"
        assert student_item["latest_version_no"] == 1

        updated = client.post(
            f"/api/teaching/assignments/{assignment_id}/submit",
            headers={"X-Demo-Token": student_token},
            json={"content": "修改后的提交说明", "retain_existing_file": True},
        )
        assert updated.status_code == 200
        assert updated.json()["item"]["versions"][-1]["version_no"] == 2
        assert updated.json()["item"]["versions"][-1]["file_name"] == "answer.txt"

        downloaded = client.get(
            f"/api/teaching/submissions/{submission_id}/versions/2/file",
            headers={"X-Demo-Token": teacher_token},
        )
        assert downloaded.status_code == 200
        assert downloaded.content == content

        roster = client.get(
            f"/api/teaching/assignments/{assignment_id}/roster",
            headers={"X-Demo-Token": teacher_token},
        )
        teacher_item = next(item for item in roster.json()["items"] if item["submission_id"] == submission_id)
        assert teacher_item["content"] == "修改后的提交说明"
        assert teacher_item["file_name"] == "answer.txt"
        assert teacher_item["file_version_no"] == 2

        denied = client.get(
            f"/api/teaching/submissions/{submission_id}/versions/2/file",
            headers={"X-Demo-Token": outsider_token},
        )
        assert denied.status_code == 403
