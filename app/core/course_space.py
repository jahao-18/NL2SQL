"""Scoped course announcements, resources and notification center."""
from __future__ import annotations

import base64
import binascii
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core.authorization import connect, forbidden, require_teacher_of_class
from app.core.business_domains import AuthContext
from app.core.teaching_migrations import DB_PATH


RESOURCE_DIR = DB_PATH.parent / "course_resources"
ALLOWED_RESOURCE_SUFFIXES = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".zip", ".png", ".jpg", ".jpeg", ".txt", ".csv"}
MAX_RESOURCE_BYTES = 20 * 1024 * 1024
NOTIFICATION_TARGETS = {
    "course_announcement": "course-space-view",
    "assignment": "assignment-workflow-view",
    "assignment_submission": "assignment-workflow-view",
    "course_question": "course-questions-view",
    "support_case": "support-workbench-view",
    "support_request": "support-workbench-view",
    "grade_submission": "teaching-operations-view",
    "grade_result": "dashboard-view",
}


def _now() -> str: return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _member(conn, ctx: AuthContext, teaching_class_id: int) -> bool:
    if ctx.role == "teacher" and ctx.row_scope.get("teacher_id"):
        return conn.execute("SELECT 1 FROM teaching_class WHERE id = ? AND teacher_id = ?", (teaching_class_id, ctx.row_scope["teacher_id"])).fetchone() is not None
    if ctx.role == "student" and ctx.row_scope.get("student_id"):
        return conn.execute("SELECT 1 FROM enrollment WHERE teaching_class_id = ? AND student_id = ?", (teaching_class_id, ctx.row_scope["student_id"])).fetchone() is not None
    return False


def notifications(ctx: AuthContext, unread_only: bool = False) -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute("SELECT id, type, title, body, resource_type, resource_id, read_at, created_at FROM notification WHERE recipient_username = ? AND (? = 0 OR read_at IS NULL) ORDER BY created_at DESC, id DESC LIMIT 200", (ctx.username, 1 if unread_only else 0)).fetchall()
        unread = int(conn.execute("SELECT count(*) FROM notification WHERE recipient_username = ? AND read_at IS NULL", (ctx.username,)).fetchone()[0])
    items = []
    for row in rows:
        item = dict(row)
        item["target_view"] = NOTIFICATION_TARGETS.get(item["resource_type"])
        items.append(item)
    return {"items": items, "unread_count": unread}


def read_notification(ctx: AuthContext, notification_id: int) -> dict[str, Any]:
    with connect() as conn:
        changed = conn.execute("UPDATE notification SET read_at = COALESCE(read_at, ?) WHERE id = ? AND recipient_username = ?", (_now(), notification_id, ctx.username)).rowcount
        if not changed: raise ValueError("通知不存在或无权访问")
        conn.commit()
    return {"read": True, "id": notification_id}


def course_space(ctx: AuthContext, teaching_class_id: int) -> dict[str, Any]:
    with connect() as conn:
        if not _member(conn, ctx, teaching_class_id): forbidden()
        info = conn.execute("SELECT tc.id, c.name AS course_name, c.course_code, tc.year, tc.semester, tc.classroom FROM teaching_class tc JOIN course c ON c.id = tc.course_id WHERE tc.id = ?", (teaching_class_id,)).fetchone()
        announcements = conn.execute("SELECT id, title, body, published_at FROM course_announcement WHERE teaching_class_id = ? AND status = 'published' ORDER BY published_at DESC, id DESC", (teaching_class_id,)).fetchall()
        drafts = []
        if ctx.role == "teacher":
            drafts = conn.execute(
                "SELECT id, title, body, created_at FROM course_announcement WHERE teaching_class_id = ? AND publisher_user_id = ? AND status = 'draft' ORDER BY created_at DESC, id DESC",
                (teaching_class_id, ctx.user_id),
            ).fetchall()
        resources = conn.execute("SELECT id, title, description, file_name, file_size, content_type, resource_url, CASE WHEN file_key IS NOT NULL AND file_key <> '' THEN 1 ELSE 0 END AS has_attachment, visible_from, visible_until FROM course_resource WHERE teaching_class_id = ? AND status = 'published' AND (visible_from IS NULL OR visible_from <= ?) AND (visible_until IS NULL OR visible_until > ?) ORDER BY id DESC", (teaching_class_id, _now(), _now())).fetchall()
    return {"item": {"course": dict(info), "announcements": [dict(r) for r in announcements], "announcement_drafts": [dict(r) for r in drafts], "resources": [dict(r) for r in resources]}}


def publish_announcement(ctx: AuthContext, teaching_class_id: int, title: str, body: str) -> dict[str, Any]:
    if not title.strip() or not body.strip(): raise ValueError("公告标题和正文不能为空")
    with connect() as conn:
        require_teacher_of_class(ctx, teaching_class_id)
        now = _now(); cur = conn.execute("INSERT INTO course_announcement(teaching_class_id, publisher_user_id, title, body, status, published_at, created_at, updated_at) VALUES (?, ?, ?, ?, 'published', ?, ?, ?)", (teaching_class_id, ctx.user_id, title.strip(), body.strip(), now, now, now)); aid = int(cur.lastrowid)
        students = _deliver_announcement(conn, aid, teaching_class_id, title.strip(), body.strip(), now)
        conn.commit()
    return {"item": {"id": aid, "recipient_count": len(students)}}


def publish_announcement_draft(ctx: AuthContext, announcement_id: int) -> dict[str, Any]:
    """Publish an assistant-created draft only after a teacher explicitly confirms it."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, teaching_class_id, publisher_user_id, title, body, status FROM course_announcement WHERE id = ?",
            (announcement_id,),
        ).fetchone()
        if not row:
            raise ValueError("公告草稿不存在")
        require_teacher_of_class(ctx, row["teaching_class_id"])
        if row["publisher_user_id"] != ctx.user_id:
            forbidden()
        if row["status"] != "draft":
            raise ValueError("该公告草稿已发布或不可发布")
        now = _now()
        changed = conn.execute(
            "UPDATE course_announcement SET status = 'published', published_at = ?, updated_at = ? WHERE id = ? AND status = 'draft'",
            (now, now, announcement_id),
        ).rowcount
        if changed != 1:
            raise ValueError("该公告草稿状态已变化，请刷新后重试")
        students = _deliver_announcement(conn, announcement_id, row["teaching_class_id"], row["title"], row["body"], now)
        conn.commit()
    return {"item": {"id": announcement_id, "published": True, "recipient_count": len(students)}}


def _deliver_announcement(conn, announcement_id: int, teaching_class_id: int, title: str, body: str, delivered_at: str):
    students = conn.execute("SELECT au.id, au.username FROM enrollment e JOIN person_identity pi ON pi.person_type = 'student' AND pi.entity_id = e.student_id AND pi.status = 'verified' JOIN app_user au ON au.id = pi.user_id WHERE e.teaching_class_id = ? AND au.status = 'active'", (teaching_class_id,)).fetchall()
    for row in students:
        conn.execute("INSERT INTO announcement_receipt(announcement_id, recipient_user_id, delivered_at) VALUES (?, ?, ?)", (announcement_id, row["id"], delivered_at))
        conn.execute("INSERT INTO notification(recipient_username, type, title, body, resource_type, resource_id, created_at) VALUES (?, 'course_announcement', ?, ?, 'course_announcement', ?, ?)", (row["username"], title, body, announcement_id, delivered_at))
    return students


def delete_announcement(ctx: AuthContext, announcement_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT teaching_class_id, title, status FROM course_announcement WHERE id = ?", (announcement_id,)).fetchone()
        if not row:
            raise ValueError("公告不存在")
        require_teacher_of_class(ctx, row["teaching_class_id"])
        if row["status"] != "published":
            raise ValueError("公告已经删除")
        now = _now()
        conn.execute("UPDATE course_announcement SET status = 'deleted', updated_at = ? WHERE id = ?", (now, announcement_id))
        removed_notifications = conn.execute("DELETE FROM notification WHERE resource_type = 'course_announcement' AND resource_id = ?", (announcement_id,)).rowcount
        conn.execute("INSERT INTO audit_log(actor_user, actor_role, resource_type, resource_id, action, before_state, after_state, created_at) VALUES (?, ?, 'course_announcement', ?, 'delete_announcement', 'published', 'deleted', ?)", (ctx.username, ctx.role, announcement_id, now))
        conn.commit()
    return {"item": {"id": announcement_id, "deleted": True, "removed_notification_count": removed_notifications}}


def announcement_receipts(ctx: AuthContext, announcement_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT teaching_class_id FROM course_announcement WHERE id = ?", (announcement_id,)).fetchone()
        if not row: raise ValueError("公告不存在")
        require_teacher_of_class(ctx, row["teaching_class_id"])
        total, read = conn.execute("SELECT count(*), sum(CASE WHEN read_at IS NOT NULL THEN 1 ELSE 0 END) FROM announcement_receipt WHERE announcement_id = ?", (announcement_id,)).fetchone()
    return {"item": {"announcement_id": announcement_id, "delivered_count": int(total or 0), "read_count": int(read or 0)}}


def add_resource(ctx: AuthContext, teaching_class_id: int, title: str, description: str, file_name: str, file_content_base64: str | None, content_type: str, resource_url: str, visible_from: str | None, visible_until: str | None) -> dict[str, Any]:
    safe_file_name = Path(file_name or "").name
    file_bytes: bytes | None = None
    resource_url = resource_url.strip()
    if resource_url and urlparse(resource_url).scheme not in {"http", "https"}:
        raise ValueError("外部链接仅支持 HTTP 或 HTTPS")
    if file_content_base64:
        suffix = Path(safe_file_name).suffix.lower()
        if not safe_file_name or suffix not in ALLOWED_RESOURCE_SUFFIXES:
            raise ValueError("附件格式不支持，请上传文档、表格、演示文稿、压缩包、图片或文本文件")
        try:
            file_bytes = base64.b64decode(file_content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("附件内容无效") from exc
        if not file_bytes:
            raise ValueError("附件内容不能为空")
        if len(file_bytes) > MAX_RESOURCE_BYTES:
            raise ValueError("课程资料附件不能超过 20MB")
    elif safe_file_name:
        raise ValueError("选择附件后必须上传文件内容")
    if not title.strip() or not (file_bytes or resource_url):
        raise ValueError("资料标题不能为空，并且必须上传附件或填写外部链接")
    with connect() as conn:
        require_teacher_of_class(ctx, teaching_class_id)
        now = _now()
        file_key = None
        if file_bytes is not None:
            suffix = Path(safe_file_name).suffix.lower()
            target_dir = RESOURCE_DIR / str(teaching_class_id)
            target_dir.mkdir(parents=True, exist_ok=True)
            file_key = f"{teaching_class_id}/{secrets.token_hex(16)}{suffix}"
            (RESOURCE_DIR / file_key).write_bytes(file_bytes)
        try:
            cur = conn.execute("INSERT INTO course_resource(teaching_class_id, publisher_user_id, title, description, file_name, file_key, file_size, content_type, resource_url, visible_from, visible_until, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (teaching_class_id, ctx.user_id, title.strip(), description.strip(), safe_file_name, file_key, len(file_bytes) if file_bytes is not None else None, content_type.strip() if file_bytes is not None else "", resource_url, visible_from, visible_until, now, now))
            conn.commit()
        except Exception:
            if file_key:
                (RESOURCE_DIR / file_key).unlink(missing_ok=True)
            raise
    return {"item": {"id": int(cur.lastrowid), "file_name": safe_file_name, "file_size": len(file_bytes) if file_bytes is not None else None}}


def get_resource_file(ctx: AuthContext, resource_id: int) -> tuple[Path, str, str | None]:
    with connect() as conn:
        row = conn.execute("SELECT teaching_class_id, file_key, file_name, content_type, status, visible_from, visible_until FROM course_resource WHERE id = ?", (resource_id,)).fetchone()
        if not row or not _member(conn, ctx, row["teaching_class_id"]):
            forbidden()
    now = _now()
    if row["status"] != "published" or (ctx.role == "student" and ((row["visible_from"] and row["visible_from"] > now) or (row["visible_until"] and row["visible_until"] <= now))):
        forbidden()
    if not row["file_key"]:
        raise ValueError("该课程资料没有可下载附件")
    path = (RESOURCE_DIR / row["file_key"]).resolve()
    if RESOURCE_DIR.resolve() not in path.parents or not path.is_file():
        raise ValueError("课程资料附件不存在")
    return path, row["file_name"], row["content_type"] or None
