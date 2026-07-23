"""Role-scoped, deterministic data for the V2 workbench home page."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable

from app.core import teaching_migrations
from app.core.business_domains import AuthContext


ROLE_COPY = {
    "student": ("我的首页", "查看本人的课程任务、成绩和学习支持消息。"),
    "teacher": ("教学首页", "聚焦本人授课课程的批阅、发布和课程运行。"),
    "counselor": ("工作首页", "跟进本人所带行政班的学习支持事项与学生预约。"),
    "academic_office": ("教务首页", "处理全校教学运行中的确定性异常与待办。"),
    "college_manager": ("学院首页", "掌握本学院课程运行、教师工作量和教学异常。"),
    "admin": ("运维首页", "关注平台数据、同步结果和高风险审计事件。"),
}


def _rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def _summary(label: str, value: Any, tone: str = "neutral") -> dict[str, Any]:
    return {"label": label, "value": value, "tone": tone}


def _section(type_: str, title: str, items: list[dict[str, Any]], description: str = "", *, status: bool = False) -> dict[str, Any] | None:
    # Status sections are meaningful even when all values are zero. Ordinary empty
    # sections are removed here so every client gets the same empty-state behavior.
    if not items and not status:
        return None
    return {"type": type_, "title": title, "description": description, "items": items}


def _student(conn: sqlite3.Connection, ctx: AuthContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    student_id = int(ctx.row_scope["student_id"])
    courses = _rows(conn, """
        SELECT tc.id, c.name AS title,
               t.name || ' · ' || tc.classroom AS subtitle,
               tc.year || ' ' || CASE tc.semester WHEN 'spring' THEN '春季' ELSE '秋季' END AS meta,
               'course-analytics-view' AS target
        FROM enrollment e JOIN teaching_class tc ON tc.id = e.teaching_class_id
        JOIN course c ON c.id = tc.course_id JOIN teacher t ON t.id = tc.teacher_id
        WHERE e.student_id = ? ORDER BY tc.year DESC, tc.id DESC LIMIT 6
    """, (student_id,))
    tasks = _rows(conn, """
        SELECT a.id, c.name AS title, a.title AS subtitle, a.due_time AS meta,
               CASE WHEN s.status = 'returned' THEN '已退回'
                    WHEN s.id IS NULL OR s.status IN ('missing', 'not_submitted') THEN '待提交'
                    ELSE '处理中' END AS badge,
               'assignment-workflow-view' AS target
        FROM enrollment e
        JOIN teaching_class tc ON tc.id = e.teaching_class_id
        JOIN course c ON c.id = tc.course_id
        JOIN assignment a ON a.teaching_class_id = tc.id AND a.status = 'published'
        LEFT JOIN assignment_submission s ON s.assignment_id = a.id AND s.student_id = e.student_id
        WHERE e.student_id = ?
          AND (s.id IS NULL OR s.status IN ('missing', 'not_submitted', 'returned'))
        ORDER BY a.due_time, a.id LIMIT 6
    """, (student_id,))
    grades = _rows(conn, """
        SELECT a.id, c.name AS title, a.title AS subtitle,
               printf('%.1f / %.1f', gr.score, a.max_score) AS meta,
               '已发布' AS badge, 'assignment-workflow-view' AS target
        FROM grading_record gr
        JOIN assignment_submission s ON s.id = gr.submission_id
        JOIN assignment a ON a.id = s.assignment_id
        JOIN teaching_class tc ON tc.id = a.teaching_class_id
        JOIN course c ON c.id = tc.course_id
        WHERE s.student_id = ? AND gr.published = 1
        ORDER BY COALESCE(gr.published_at, gr.created_at) DESC, gr.id DESC LIMIT 4
    """, (student_id,))
    support = _rows(conn, """
        SELECT sc.id, sc.title, sc.suggested_action AS subtitle,
               COALESCE(sc.review_at, sc.updated_at, sc.created_at) AS meta,
               CASE sc.status WHEN 'open' THEN '待跟进' WHEN 'contacted' THEN '跟进中' ELSE sc.status END AS badge,
               'support-workbench-view' AS target
        FROM support_case sc
        WHERE sc.student_id = ? AND sc.visible_to_student = 1 AND sc.status <> 'closed'
        ORDER BY COALESCE(sc.review_at, sc.created_at), sc.id LIMIT 4
    """, (student_id,))
    unread = _one(conn, "SELECT count(*) FROM notification WHERE recipient_username = ? AND read_at IS NULL", (ctx.username,))
    sections = [
        _section("pending_assignments", "近期任务", tasks, "只显示本人课程中仍需处理的作业。"),
        _section("published_grades", "最新成绩", grades, "只显示已经向本人发布的成绩。"),
        _section("learning_support", "学习支持", support, "辅导员向本人公开的建议与跟进。"),
        _section("my_courses", "我的课程", courses, "仅显示本人已选课程。"),
    ]
    summary = [_summary("待处理任务", len(tasks), "warning" if tasks else "good"), _summary("未读通知", unread), _summary("我的课程", len(courses), "good")]
    actions = [{"label": "查看作业与任务", "target": "assignment-workflow-view"}, {"label": "进入我的课程分析", "target": "course-analytics-view"}]
    return summary, [s for s in sections if s], actions


def _teacher(conn: sqlite3.Connection, ctx: AuthContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    teacher_id = int(ctx.row_scope["teacher_id"])
    pending = _rows(conn, """
        SELECT a.id, c.name AS title, a.title AS subtitle,
               count(s.id) AS value, '份待批阅' AS unit, a.due_time AS meta,
               'assignment-workflow-view' AS target
        FROM teaching_class tc
        JOIN course c ON c.id = tc.course_id
        JOIN assignment a ON a.teaching_class_id = tc.id
        JOIN assignment_submission s ON s.assignment_id = a.id
        LEFT JOIN grading_record gr ON gr.submission_id = s.id
        WHERE tc.teacher_id = ? AND s.status NOT IN ('missing', 'not_submitted') AND gr.id IS NULL
        GROUP BY a.id, c.name, a.title, a.due_time
        HAVING count(s.id) > 0 ORDER BY a.due_time, a.id LIMIT 6
    """, (teacher_id,))
    classes = _rows(conn, """
        SELECT tc.id, c.name AS title,
               tc.year || ' ' || CASE tc.semester WHEN 'spring' THEN '春季' ELSE '秋季' END AS subtitle,
               count(e.id) AS value, '名学生' AS unit, tc.classroom AS meta,
               'course-analytics-view' AS target
        FROM teaching_class tc JOIN course c ON c.id = tc.course_id
        LEFT JOIN enrollment e ON e.teaching_class_id = tc.id
        WHERE tc.teacher_id = ?
        GROUP BY tc.id, c.name, tc.year, tc.semester, tc.classroom
        ORDER BY tc.year DESC, tc.id DESC LIMIT 6
    """, (teacher_id,))
    unpublished = _one(conn, """
        SELECT count(*) FROM grading_record gr
        JOIN assignment_submission s ON s.id = gr.submission_id
        JOIN assignment a ON a.id = s.assignment_id
        JOIN teaching_class tc ON tc.id = a.teaching_class_id
        WHERE tc.teacher_id = ? AND gr.published = 0
    """, (teacher_id,))
    sections = [
        _section("pending_grading", "待批阅提交", pending, "仅汇总本人授课班级，不展示无关学生。"),
        _section("teaching_classes", "我的课程", classes, "本人当前可管理和分析的授课班级。"),
    ]
    summary = [_summary("待批阅", sum(int(i["value"]) for i in pending), "warning" if pending else "good"), _summary("待发布成绩", unpublished), _summary("授课班级", len(classes))]
    actions = [{"label": "进入作业批阅", "target": "assignment-workflow-view"}, {"label": "查看课程分析", "target": "course-analytics-view"}]
    return summary, [s for s in sections if s], actions


def _counselor(conn: sqlite3.Connection, ctx: AuthContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    counselor_id = int(ctx.row_scope["counselor_id"])
    classes = _rows(conn, """
        SELECT cg.id, cg.name AS title, m.name AS subtitle,
               count(s.id) AS value, '名学生' AS unit, cg.grade_year AS meta,
               'support-workbench-view' AS target
        FROM counselor_class_group ccg JOIN class_group cg ON cg.id = ccg.class_group_id
        JOIN major m ON m.id = cg.major_id LEFT JOIN student s ON s.class_id = cg.id
        WHERE ccg.counselor_id = ?
        GROUP BY cg.id, cg.name, m.name, cg.grade_year ORDER BY cg.grade_year DESC, cg.id
    """, (counselor_id,))
    cases = _rows(conn, """
        SELECT sc.id, s.name AS title, sc.title AS subtitle,
               COALESCE(sc.review_at, sc.updated_at, sc.created_at) AS meta,
               CASE sc.status WHEN 'open' THEN '待联系' WHEN 'contacted' THEN '待复查' ELSE '处理中' END AS badge,
               'support-workbench-view' AS target
        FROM support_case sc JOIN student s ON s.id = sc.student_id
        JOIN counselor_class_group ccg ON ccg.class_group_id = s.class_id AND ccg.counselor_id = sc.counselor_id
        WHERE sc.counselor_id = ? AND sc.status <> 'closed'
        ORDER BY COALESCE(sc.review_at, sc.created_at), sc.id LIMIT 8
    """, (counselor_id,))
    requests = _rows(conn, """
        SELECT sr.id, s.name AS title, sr.message AS subtitle,
               COALESCE(sr.preferred_time, sr.created_at) AS meta,
               CASE sr.status WHEN 'submitted' THEN '新预约' WHEN 'accepted' THEN '已受理' ELSE sr.status END AS badge,
               'support-workbench-view' AS target
        FROM support_request sr JOIN student s ON s.id = sr.student_id
        JOIN counselor_class_group ccg ON ccg.class_group_id = s.class_id
        WHERE ccg.counselor_id = ? AND (sr.counselor_id IS NULL OR sr.counselor_id = ?)
          AND sr.status NOT IN ('completed', 'rejected')
        ORDER BY sr.created_at DESC, sr.id DESC LIMIT 6
    """, (counselor_id, counselor_id))
    class_count = _one(conn, "SELECT count(*) FROM counselor_class_group WHERE counselor_id = ?", (counselor_id,))
    sections = [_section("support_followups", "今日应跟进", cases, "只包含本人所带行政班学生。"), _section("student_appointments", "学生预约", requests), _section("managed_classes", "所带班级", classes, "本人负责的行政班范围。")]
    summary = [_summary("待跟进事项", len(cases), "warning" if cases else "good"), _summary("进行中预约", len(requests)), _summary("所带班级", class_count)]
    actions = [{"label": "进入学习支持", "target": "support-workbench-view"}, {"label": "查看跟进日程", "target": "support-workbench-view"}]
    return summary, [s for s in sections if s], actions


def _operations(conn: sqlite3.Connection, ctx: AuthContext, college_only: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    params: tuple[Any, ...] = ()
    scope = ""
    if college_only:
        scope = " AND c.college_id = ?"
        params = (int(ctx.row_scope["college_id"]),)
    anomalies = _rows(conn, f"""
        SELECT tc.id, c.name AS title,
               CASE WHEN count(e.id) > tc.capacity THEN '选课人数超过容量' ELSE '教学安排待确认' END AS subtitle,
               count(e.id) || ' / ' || tc.capacity AS meta, '待处理' AS badge,
               'teaching-operations-view' AS target
        FROM teaching_class tc JOIN course c ON c.id = tc.course_id
        LEFT JOIN enrollment e ON e.teaching_class_id = tc.id
        WHERE 1=1 {scope}
        GROUP BY tc.id, c.name, tc.capacity
        HAVING count(e.id) > tc.capacity OR tc.classroom IS NULL OR trim(tc.classroom) = ''
        ORDER BY (count(e.id) - tc.capacity) DESC, tc.id LIMIT 8
    """, params)
    aggregate = _rows(conn, f"""
        SELECT tc.id, c.name AS title,
               t.name AS subtitle, count(e.id) AS value, '人次' AS unit,
               tc.year || ' ' || tc.semester AS meta, 'teaching-operations-view' AS target
        FROM teaching_class tc JOIN course c ON c.id = tc.course_id
        JOIN teacher t ON t.id = tc.teacher_id LEFT JOIN enrollment e ON e.teaching_class_id = tc.id
        WHERE 1=1 {scope}
        GROUP BY tc.id, c.name, t.name, tc.year, tc.semester
        ORDER BY count(e.id) DESC, tc.id LIMIT 6
    """, params)
    class_count = _one(conn, f"SELECT count(*) FROM teaching_class tc JOIN course c ON c.id=tc.course_id WHERE 1=1 {scope}", params)
    enrollment_count = _one(conn, f"SELECT count(*) FROM enrollment e JOIN teaching_class tc ON tc.id=e.teaching_class_id JOIN course c ON c.id=tc.course_id WHERE 1=1 {scope}", params)
    title = "学院教学异常" if college_only else "教学运行异常"
    issue_type = "college_teaching_issues" if college_only else "teaching_issues"
    operation_type = "college_course_operations" if college_only else "course_operations"
    sections = [_section(issue_type, title, anomalies, "由容量或教学安排规则确定生成。"), _section(operation_type, "课程运行", aggregate, "按授权范围汇总开课班学生人次。")]
    summary = [_summary("待处理异常", len(anomalies), "warning" if anomalies else "good"), _summary("开课班", class_count), _summary("选课人次", enrollment_count)]
    actions = [{"label": "处理教学异常", "target": "teaching-operations-view"}, {"label": "查看课程运行", "target": "teaching-operations-view"}]
    return summary, [s for s in sections if s], actions


def _admin(conn: sqlite3.Connection, _: AuthContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    sources = [
        {"id": "teaching", "title": "教学业务库", "subtitle": "SQLite 数据源可用", "badge": "正常", "meta": "teaching", "target": "data-access-view"},
    ]
    audits = _rows(conn, """
        SELECT id, actor_user AS title, action AS subtitle, created_at AS meta,
               actor_role AS badge, 'governance-queue-view' AS target
        FROM audit_log ORDER BY created_at DESC, id DESC LIMIT 6
    """)
    table_count = _one(conn, "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    quality_count = _one(conn, "SELECT count(*) FROM support_unassigned_case WHERE status = 'unassigned'")
    sections = [_section("source_health", "数据源健康", sources, status=True), _section("audit_activity", "最近审计活动", audits)]
    summary = [_summary("业务表", table_count), _summary("待处理质量项", quality_count, "warning" if quality_count else "good"), _summary("数据源状态", "正常", "good")]
    actions = [{"label": "管理数据源", "target": "data-access-view"}, {"label": "查看治理队列", "target": "governance-queue-view"}]
    return summary, [s for s in sections if s], actions


def build_workbench(ctx: AuthContext) -> dict[str, Any]:
    builders: dict[str, Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]]] = {
        "student": _student,
        "teacher": _teacher,
        "counselor": _counselor,
        "academic_office": lambda conn, auth: _operations(conn, auth, False),
        "college_manager": lambda conn, auth: _operations(conn, auth, True),
        "admin": _admin,
    }
    title, description = ROLE_COPY[ctx.role]
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        summary, sections, actions = builders[ctx.role](conn, ctx)
    return {
        "role": ctx.role,
        "title": title,
        "description": description,
        "scope_label": ctx.role_label if ctx.role == "admin" else _scope_text(ctx),
        "summary": summary,
        "sections": sections,
        "quick_actions": actions,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _scope_text(ctx: AuthContext) -> str:
    return {
        "student": "仅限本人学习数据",
        "teacher": "仅限本人授课班级",
        "counselor": "仅限本人所带行政班",
        "college_manager": "仅限本学院",
        "academic_office": "教务管理授权范围",
    }.get(ctx.role, "当前岗位授权范围")
