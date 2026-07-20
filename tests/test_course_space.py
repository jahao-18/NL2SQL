from __future__ import annotations
import base64
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
from app.core import teaching_migrations
from app.core.business_domains import token_for
from app.main import app


def test_course_space_frontend_has_structured_responsive_workspace():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")
    script = (Path(__file__).parents[1] / "app" / "static" / "app.js").read_text(encoding="utf-8")
    style = (Path(__file__).parents[1] / "app" / "static" / "style.css").read_text(encoding="utf-8")

    assert 'id="course-space-summary"' in html
    assert 'id="course-announcement-form"' in html
    assert 'id="course-resource-form"' in html
    assert 'id="course-resource-file" type="file"' in html
    assert 'data-course-section="announcements"' in html
    assert 'data-course-content="announcements"' in script
    assert "data-delete-announcement" in script
    assert "data-publish-announcement" in script
    assert "publishAnnouncementDraft" in script
    assert "course-space-composer-grid" in style
    assert "@media(max-width:900px)" in style

def test_announcement_notification_and_course_resource_are_member_scoped():
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        row = conn.execute("SELECT tc.id, au.username, tea.username FROM enrollment e JOIN teaching_class tc ON tc.id=e.teaching_class_id JOIN person_identity pi ON pi.person_type='student' AND pi.entity_id=e.student_id AND pi.status='verified' JOIN app_user au ON au.id=pi.user_id JOIN staff st ON st.teacher_id=tc.teacher_id JOIN person_identity tpi ON tpi.entity_id=st.id AND tpi.person_type='staff' AND tpi.status='verified' JOIN app_user tea ON tea.id=tpi.user_id WHERE tea.username='teacher' LIMIT 1").fetchone()
        class_id, student, teacher = row
    with TestClient(app) as client:
        posted = client.post(f"/api/teaching/classes/{class_id}/announcements", headers={"X-Demo-Token": token_for(teacher)}, json={"title":"课程公告测试", "body":"请查看本周资料"})
        assert posted.status_code == 200
        aid = posted.json()["item"]["id"]
        notice = client.get("/api/notifications", headers={"X-Demo-Token": token_for(student)})
        assert notice.status_code == 200 and any(item["resource_id"] == aid for item in notice.json()["items"])
        item = next(item for item in notice.json()["items"] if item["resource_id"] == aid)
        assert client.post(f"/api/notifications/{item['id']}/read", headers={"X-Demo-Token": token_for(student)}).status_code == 200
        assert client.get(f"/api/teaching/announcements/{aid}/receipts", headers={"X-Demo-Token": token_for(teacher)}).json()["item"]["delivered_count"] >= 1
        assert client.delete(f"/api/teaching/announcements/{aid}", headers={"X-Demo-Token": token_for(student)}).status_code == 403
        deleted = client.delete(f"/api/teaching/announcements/{aid}", headers={"X-Demo-Token": token_for(teacher)})
        assert deleted.status_code == 200 and deleted.json()["item"]["deleted"] is True
        assert all(entry["id"] != aid for entry in client.get(f"/api/teaching/classes/{class_id}/space", headers={"X-Demo-Token": token_for(student)}).json()["item"]["announcements"])
        assert all(entry["resource_id"] != aid for entry in client.get("/api/notifications", headers={"X-Demo-Token": token_for(student)}).json()["items"])
        assert client.delete(f"/api/teaching/announcements/{aid}", headers={"X-Demo-Token": token_for(teacher)}).status_code == 400
        content = b"real course attachment"
        resource = client.post(f"/api/teaching/classes/{class_id}/resources", headers={"X-Demo-Token": token_for(teacher)}, json={"title":"课件", "file_name":"week1.pdf", "content_type":"application/pdf", "file_content_base64":base64.b64encode(content).decode("ascii")})
        assert resource.status_code == 200
        resource_id = resource.json()["item"]["id"]
        space = client.get(f"/api/teaching/classes/{class_id}/space", headers={"X-Demo-Token": token_for(student)})
        assert space.status_code == 200
        saved = next(item for item in space.json()["item"]["resources"] if item["id"] == resource_id)
        assert saved["has_attachment"] == 1 and saved["file_size"] == len(content)
        downloaded = client.get(f"/api/teaching/resources/{resource_id}/file", headers={"X-Demo-Token": token_for(student)})
        assert downloaded.status_code == 200 and downloaded.content == content
        assert client.get(f"/api/teaching/resources/{resource_id}/file", headers={"X-Demo-Token": token_for("admin")}).status_code == 403
        unsafe = client.post(f"/api/teaching/classes/{class_id}/resources", headers={"X-Demo-Token": token_for(teacher)}, json={"title":"不安全链接", "resource_url":"javascript:alert(1)"})
        assert unsafe.status_code == 400
