"""Repeatable schema/data setup for the MVP teaching workflow."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.config import ROOT_DIR


DB_PATH = ROOT_DIR / "data" / "teaching.db"

DEMO_STUDENT_IDS = {
    "stu_zhang": 900001,
    "stu_wang": 900002,
    "stu_liu": 900003,
    "stu_chen": 900004,
    "stu_zhao": 900005,
    "stu_sun": 900006,
}
DEMO_TEACHER_IDS = {"tea_li": 900001, "tea_zhou": 900002}
DEMO_COUNSELOR_IDS = {"counselor_chen": 900001, "counselor_lin": 900002}
DEMO_CLASS_IDS = {"se_2023_1": 900001, "se_2023_2": 900002, "ai_2023_1": 900003}
DEMO_COURSE_IDS = {"db": 900001, "web": 900002}
DEMO_TEACHING_CLASS_IDS = {"db_2025_sp_01": 900001, "web_2025_sp_01": 900002}
DEMO_ASSIGNMENT_IDS = {"db_a1": 900001, "db_a2": 900002, "db_a3": 900003, "web_a1": 900004}
DEMO_SUPPORT_CASE_IDS = {"sup_001": 900001, "sup_002": 900002}


def ensure_mvp_schema(db_path: Path = DB_PATH) -> None:
    """Create MVP business tables and deterministic demo rows if the teaching DB exists."""
    if not db_path.exists():
        return
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _create_tables(conn)
        _seed_demo_scope(conn)
        conn.commit()


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_user (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            student_id INTEGER,
            teacher_id INTEGER,
            counselor_id INTEGER,
            college_id INTEGER,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS role (
            id INTEGER PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_role (
            user_id INTEGER NOT NULL,
            role_code TEXT NOT NULL,
            PRIMARY KEY (user_id, role_code),
            FOREIGN KEY (user_id) REFERENCES app_user(id)
        );

        CREATE TABLE IF NOT EXISTS counselor (
            id INTEGER PRIMARY KEY,
            counselor_no TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            college_id INTEGER NOT NULL,
            FOREIGN KEY (college_id) REFERENCES college(id)
        );

        CREATE TABLE IF NOT EXISTS counselor_class_group (
            counselor_id INTEGER NOT NULL,
            class_group_id INTEGER NOT NULL,
            PRIMARY KEY (counselor_id, class_group_id),
            FOREIGN KEY (counselor_id) REFERENCES counselor(id),
            FOREIGN KEY (class_group_id) REFERENCES class_group(id)
        );

        CREATE TABLE IF NOT EXISTS support_case (
            id INTEGER PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            student_id INTEGER NOT NULL,
            counselor_id INTEGER NOT NULL,
            rule_code TEXT NOT NULL,
            title TEXT NOT NULL,
            evidence TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            review_at TEXT,
            closed_reason TEXT,
            FOREIGN KEY (student_id) REFERENCES student(id),
            FOREIGN KEY (counselor_id) REFERENCES counselor(id)
        );

        CREATE TABLE IF NOT EXISTS support_case_log (
            id INTEGER PRIMARY KEY,
            case_id INTEGER NOT NULL,
            actor_user TEXT NOT NULL,
            action TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (case_id) REFERENCES support_case(id)
        );

        CREATE TABLE IF NOT EXISTS support_request (
            id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL,
            counselor_id INTEGER,
            request_type TEXT NOT NULL,
            message TEXT NOT NULL,
            preferred_time TEXT,
            status TEXT NOT NULL DEFAULT 'submitted',
            counselor_response TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES student(id),
            FOREIGN KEY (counselor_id) REFERENCES counselor(id)
        );

        CREATE TABLE IF NOT EXISTS support_unassigned_case (
            id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL,
            rule_code TEXT NOT NULL,
            trigger_key TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            evidence TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'unassigned',
            created_at TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES student(id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY,
            actor_user TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            before_state TEXT,
            after_state TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS submission_version (
            id INTEGER PRIMARY KEY,
            submission_id INTEGER NOT NULL,
            version_no INTEGER NOT NULL,
            content TEXT NOT NULL,
            file_name TEXT,
            submitted_at TEXT NOT NULL,
            submitter_user TEXT NOT NULL,
            FOREIGN KEY (submission_id) REFERENCES assignment_submission(id)
        );

        CREATE TABLE IF NOT EXISTS grading_record (
            id INTEGER PRIMARY KEY,
            submission_id INTEGER NOT NULL,
            grader_teacher_id INTEGER NOT NULL,
            score REAL,
            feedback TEXT NOT NULL,
            status TEXT NOT NULL,
            published INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            published_at TEXT,
            FOREIGN KEY (submission_id) REFERENCES assignment_submission(id),
            FOREIGN KEY (grader_teacher_id) REFERENCES teacher(id)
        );

        CREATE TABLE IF NOT EXISTS notification (
            id INTEGER PRIMARY KEY,
            recipient_username TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            read_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS course_assignment_analytics (
            assignment_id INTEGER PRIMARY KEY,
            teaching_class_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            course_code TEXT NOT NULL,
            course_name TEXT NOT NULL,
            year INTEGER NOT NULL,
            semester TEXT NOT NULL,
            assignment_title TEXT NOT NULL,
            due_time TEXT NOT NULL,
            max_score REAL NOT NULL,
            enrolled_count INTEGER NOT NULL,
            submitted_count INTEGER NOT NULL,
            on_time_count INTEGER NOT NULL,
            late_count INTEGER NOT NULL,
            missing_count INTEGER NOT NULL,
            pending_grade_count INTEGER NOT NULL,
            graded_count INTEGER NOT NULL,
            published_grade_count INTEGER NOT NULL,
            average_score REAL,
            score_lt_60_count INTEGER NOT NULL DEFAULT 0,
            score_60_69_count INTEGER NOT NULL DEFAULT 0,
            score_70_79_count INTEGER NOT NULL DEFAULT 0,
            score_80_89_count INTEGER NOT NULL DEFAULT 0,
            score_90_plus_count INTEGER NOT NULL DEFAULT 0,
            completion_rate REAL NOT NULL,
            late_rate REAL NOT NULL,
            refreshed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS student_task_analytics (
            assignment_id INTEGER NOT NULL,
            teaching_class_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            course_code TEXT NOT NULL,
            course_name TEXT NOT NULL,
            assignment_title TEXT NOT NULL,
            due_time TEXT NOT NULL,
            max_score REAL NOT NULL,
            task_status TEXT NOT NULL,
            submitted_at TEXT,
            late INTEGER NOT NULL DEFAULT 0,
            published_score REAL,
            refreshed_at TEXT NOT NULL,
            PRIMARY KEY (assignment_id, student_id)
        );

        CREATE TABLE IF NOT EXISTS analytics_query_log (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            teaching_class_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            generated_sql TEXT,
            status TEXT NOT NULL,
            row_count INTEGER NOT NULL DEFAULT 0,
            confidence INTEGER,
            query_mode TEXT NOT NULL,
            error TEXT,
            scope_json TEXT NOT NULL,
            user_feedback TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_app_user_student ON app_user(student_id);
        CREATE INDEX IF NOT EXISTS idx_app_user_teacher ON app_user(teacher_id);
        CREATE INDEX IF NOT EXISTS idx_support_case_student ON support_case(student_id);
        CREATE INDEX IF NOT EXISTS idx_support_case_counselor ON support_case(counselor_id);
        CREATE INDEX IF NOT EXISTS idx_support_request_student ON support_request(student_id);
        CREATE INDEX IF NOT EXISTS idx_support_request_counselor ON support_request(counselor_id);
        CREATE INDEX IF NOT EXISTS idx_submission_version_submission ON submission_version(submission_id);
        CREATE INDEX IF NOT EXISTS idx_grading_submission ON grading_record(submission_id);
        CREATE INDEX IF NOT EXISTS idx_notification_recipient ON notification(recipient_username);
        CREATE INDEX IF NOT EXISTS idx_course_analytics_class ON course_assignment_analytics(teaching_class_id, teacher_id);
        CREATE INDEX IF NOT EXISTS idx_student_analytics_scope ON student_task_analytics(teaching_class_id, student_id);
        CREATE INDEX IF NOT EXISTS idx_analytics_log_user ON analytics_query_log(username, teaching_class_id, created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_enrollment_class_student ON enrollment(teaching_class_id, student_id);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_submission_assignment_student ON assignment_submission(assignment_id, student_id);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_submission_version_no ON submission_version(submission_id, version_no);
        """
    )
    _ensure_column(conn, "assignment", "status", "TEXT NOT NULL DEFAULT 'published'")
    _ensure_column(conn, "assignment", "instructions", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "assignment", "allow_late", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "assignment_submission", "feedback", "TEXT")
    _ensure_column(conn, "submission_version", "file_key", "TEXT")
    _ensure_column(conn, "submission_version", "file_size", "INTEGER")
    _ensure_column(conn, "support_case", "visible_to_student", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "support_case", "suggested_action", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "support_case", "updated_at", "TEXT")
    _ensure_column(conn, "support_case_log", "contact_method", "TEXT")
    _ensure_column(conn, "support_case_log", "student_feedback", "TEXT")
    _ensure_column(conn, "support_case_log", "follow_up_at", "TEXT")
    _ensure_column(conn, "support_case_log", "visible_to_student", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "course_assignment_analytics", "score_lt_60_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "course_assignment_analytics", "score_60_69_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "course_assignment_analytics", "score_70_79_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "course_assignment_analytics", "score_80_89_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "course_assignment_analytics", "score_90_plus_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "analytics_query_log", "user_feedback", "TEXT")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _seed_demo_scope(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO role(id, code, label) VALUES (?, ?, ?)",
        [
            (1, "student", "学生"),
            (2, "teacher", "任课教师"),
            (3, "counselor", "辅导员"),
            (4, "admin", "系统管理员"),
        ],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO class_group(id, major_id, name, grade_year) VALUES (?, ?, ?, ?)",
        [
            (DEMO_CLASS_IDS["se_2023_1"], 1, "软件工程2023-1班", 2023),
            (DEMO_CLASS_IDS["se_2023_2"], 1, "软件工程2023-2班", 2023),
            (DEMO_CLASS_IDS["ai_2023_1"], 3, "人工智能2023-1班", 2023),
        ],
    )
    conn.executemany(
        """
        INSERT OR REPLACE INTO student
        (id, student_no, name, gender, college_id, major_id, class_id, enrollment_year, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (900001, "2023010101", "张同学", "female", 1, 1, DEMO_CLASS_IDS["se_2023_1"], 2023, "active"),
            (900002, "2023010102", "王同学", "male", 1, 1, DEMO_CLASS_IDS["se_2023_1"], 2023, "active"),
            (900003, "2023010103", "刘同学", "female", 1, 1, DEMO_CLASS_IDS["se_2023_1"], 2023, "active"),
            (900004, "2023010104", "陈同学", "male", 1, 1, DEMO_CLASS_IDS["se_2023_1"], 2023, "active"),
            (900005, "2023010201", "赵同学", "female", 1, 1, DEMO_CLASS_IDS["se_2023_2"], 2023, "active"),
            (900006, "2023030101", "孙同学", "male", 1, 3, DEMO_CLASS_IDS["ai_2023_1"], 2023, "active"),
        ],
    )
    conn.executemany(
        """
        INSERT OR REPLACE INTO teacher
        (id, teacher_no, name, gender, college_id, title, hire_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (900001, "T900001", "李老师", "female", 1, "副教授", "2016-09-01"),
            (900002, "T900002", "周老师", "male", 1, "讲师", "2019-09-01"),
        ],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO counselor(id, counselor_no, name, college_id) VALUES (?, ?, ?, ?)",
        [
            (900001, "C900001", "陈辅导员", 1),
            (900002, "C900002", "林辅导员", 1),
        ],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO counselor_class_group(counselor_id, class_group_id) VALUES (?, ?)",
        [
            (900001, DEMO_CLASS_IDS["se_2023_1"]),
            (900002, DEMO_CLASS_IDS["se_2023_2"]),
        ],
    )
    conn.executemany(
        """
        INSERT OR REPLACE INTO course
        (id, course_code, name, credit, course_type, college_id, difficulty)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (900001, "MVP-DB", "数据库系统", 3.0, "required", 1, 0.72),
            (900002, "MVP-WEB", "Web 开发技术", 3.0, "required", 1, 0.66),
        ],
    )
    conn.executemany(
        """
        INSERT OR REPLACE INTO teaching_class
        (id, course_id, teacher_id, year, semester, capacity, classroom)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (900001, 900001, 900001, 2025, "spring", 60, "A101"),
            (900002, 900002, 900002, 2025, "spring", 60, "B202"),
        ],
    )
    enrollments = [
        (900001, 900001, 900001, "2025-03-01T09:00:00"),
        (900002, 900001, 900002, "2025-03-01T09:00:00"),
        (900003, 900001, 900003, "2025-03-01T09:00:00"),
        (900004, 900001, 900004, "2025-03-01T09:00:00"),
        (900005, 900002, 900005, "2025-03-01T09:00:00"),
        (900006, 900002, 900006, "2025-03-01T09:00:00"),
    ]
    conn.executemany("INSERT OR REPLACE INTO enrollment VALUES (?, ?, ?, ?)", enrollments)
    conn.executemany(
        """
        INSERT OR REPLACE INTO assignment
        (id, teaching_class_id, title, assignment_type, publish_time, due_time, max_score, weight)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (900001, 900001, "数据库系统第 1 次作业", "homework", "2025-03-10T08:00:00", "2025-03-17T23:59:00", 100.0, 0.1),
            (900002, 900001, "数据库系统第 2 次作业", "homework", "2025-03-18T08:00:00", "2025-03-25T23:59:00", 100.0, 0.1),
            (900003, 900001, "数据库系统第 3 次作业", "homework", "2025-03-26T08:00:00", "2026-12-31T23:59:00", 100.0, 0.1),
            (900004, 900002, "Web 开发第 1 次作业", "homework", "2025-03-26T08:00:00", "2026-12-31T23:59:00", 100.0, 0.1),
        ],
    )
    conn.executemany(
        "UPDATE assignment SET status = ?, instructions = ?, allow_late = ? WHERE id = ?",
        [
            ("closed", "完成课程资料阅读并提交简答。", 1, 900001),
            ("closed", "提交 SQL 设计说明。", 1, 900002),
            ("published", "提交 ER 图、建表 SQL 和简短说明。", 1, 900003),
            ("published", "提交一个课程首页原型。", 1, 900004),
        ],
    )
    submissions = [
        (900001, 900001, 900001, "2025-03-16T20:10:00", 88.0, 0, "submitted"),
        (900002, 900002, 900001, "2025-03-24T21:00:00", 90.0, 0, "submitted"),
        (900003, 900001, 900002, None, None, 0, "missing"),
        (900004, 900002, 900002, None, None, 0, "missing"),
        (900005, 900001, 900003, "2025-03-18T09:00:00", 75.0, 1, "late"),
        (900006, 900002, 900003, "2025-03-27T09:00:00", 78.0, 1, "late"),
        (900007, 900001, 900004, "2025-03-15T18:30:00", 92.0, 0, "submitted"),
        (900008, 900002, 900004, "2025-03-24T19:15:00", 94.0, 0, "submitted"),
        (900009, 900003, 900004, "2025-03-28T20:00:00", 91.0, 0, "submitted"),
        (900010, 900004, 900005, "2025-03-29T20:00:00", None, 0, "submitted"),
    ]
    conn.executemany(
        """
        INSERT OR REPLACE INTO assignment_submission
        (id, assignment_id, student_id, submit_time, score, late, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        submissions,
    )
    conn.executemany(
        "UPDATE assignment_submission SET feedback = ? WHERE id = ?",
        [
            ("基础部分完成较好。", 900001),
            ("SQL 说明清晰。", 900002),
            ("历史未提交。", 900003),
            ("历史未提交。", 900004),
            ("迟交，已记录。", 900005),
            ("迟交，已记录。", 900006),
            ("完成度较高。", 900007),
            ("完成度较高。", 900008),
            ("等待成绩发布。", 900009),
            ("等待批阅。", 900010),
        ],
    )
    conn.executemany(
        """
        INSERT OR REPLACE INTO submission_version
        (id, submission_id, version_no, content, file_name, submitted_at, submitter_user)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (900001, 900001, 1, "第 1 次作业提交内容", "db-a1-zhang.pdf", "2025-03-16T20:10:00", "stu_zhang"),
            (900002, 900002, 1, "第 2 次作业提交内容", "db-a2-zhang.pdf", "2025-03-24T21:00:00", "stu_zhang"),
            (900003, 900005, 1, "第 1 次作业迟交内容", "db-a1-liu.pdf", "2025-03-18T09:00:00", "stu_liu"),
            (900004, 900006, 1, "第 2 次作业迟交内容", "db-a2-liu.pdf", "2025-03-27T09:00:00", "stu_liu"),
            (900005, 900009, 1, "第 3 次作业已提交内容", "db-a3-chen.pdf", "2025-03-28T20:00:00", "stu_chen"),
            (900006, 900010, 1, "Web 第 1 次作业提交内容", "web-a1-zhao.pdf", "2025-03-29T20:00:00", "stu_zhao"),
        ],
    )
    conn.executemany(
        """
        INSERT OR REPLACE INTO grading_record
        (id, submission_id, grader_teacher_id, score, feedback, status, published, created_at, published_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (900001, 900001, 900001, 88.0, "基础部分完成较好。", "graded_published", 1, "2025-03-17T10:00:00", "2025-03-17T12:00:00"),
            (900002, 900002, 900001, 90.0, "SQL 说明清晰。", "graded_published", 1, "2025-03-25T10:00:00", "2025-03-25T12:00:00"),
            (900003, 900009, 900001, 91.0, "完成度较高，待统一发布。", "graded_unpublished", 0, "2025-03-29T10:00:00", None),
        ],
    )
    conn.executemany(
        """
        INSERT OR REPLACE INTO support_case
        (id, code, student_id, counselor_id, rule_code, title, evidence, status, created_at, review_at, closed_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                900001,
                "SUP-001",
                900002,
                900001,
                "two_missing_assignments_same_course",
                "连续未提交课程作业",
                "数据库系统第 1、2 次作业均未提交",
                "open",
                "2025-03-26T09:00:00",
                "2025-04-02",
                None,
            ),
            (
                900002,
                "SUP-002",
                900003,
                900001,
                "two_late_submissions_same_course",
                "多次迟交课程作业",
                "数据库系统第 1、2 次作业均迟交",
                "contacted",
                "2025-03-27T09:00:00",
                "2025-04-03",
                None,
            ),
        ],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO support_case_log(id, case_id, actor_user, action, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (900001, 900002, "counselor_chen", "contacted", "已联系学生确认迟交原因，约定下次作业提前一天提交。", "2025-03-27T15:00:00"),
        ],
    )
    conn.executemany(
        "UPDATE support_case SET visible_to_student = ?, suggested_action = ?, updated_at = ? WHERE id = ?",
        [
            (0, "先确认未提交原因，再与学生约定补交和后续学习计划。", "2025-03-26T09:00:00", 900001),
            (1, "建议提前拆分作业任务，并在截止前一天检查提交状态。", "2025-03-27T15:00:00", 900002),
        ],
    )
    conn.execute(
        """
        UPDATE support_case_log
        SET contact_method = 'phone', student_feedback = '近期课程任务集中，已同意调整时间安排。',
            follow_up_at = '2025-04-03', visible_to_student = 1
        WHERE id = 900001
        """
    )
    conn.executemany(
        "INSERT OR REPLACE INTO attendance(id, teaching_class_id, student_id, session_no, class_date, status) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (990001, 900001, 900004, 1, "2025-03-10", "absent"),
            (990002, 900001, 900004, 2, "2025-03-17", "absent"),
            (990003, 900001, 900001, 1, "2025-03-10", "present"),
            (990004, 900001, 900001, 2, "2025-03-17", "present"),
        ],
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO support_request
        (id, student_id, counselor_id, request_type, message, preferred_time, status, counselor_response, created_at, updated_at)
        VALUES (900001, 900003, 900001, 'appointment', '希望沟通近期课程任务安排。',
                '2025-04-03T15:30:00', 'accepted', '已预约 4 月 3 日下午沟通。',
                '2025-03-28T10:00:00', '2025-03-28T14:00:00')
        """
    )

    default_hash = "pbkdf2_sha256$260000$demo$8xwSFNNYzfn1zs9ldG0SOxgUay68z1Hir9P0W+Y3BEg="
    users = [
        (900001, "stu_zhang", "张同学", "student", default_hash, 900001, None, None, 1),
        (900002, "stu_wang", "王同学", "student", default_hash, 900002, None, None, 1),
        (900003, "stu_liu", "刘同学", "student", default_hash, 900003, None, None, 1),
        (900004, "stu_chen", "陈同学", "student", default_hash, 900004, None, None, 1),
        (900005, "stu_zhao", "赵同学", "student", default_hash, 900005, None, None, 1),
        (900006, "stu_sun", "孙同学", "student", default_hash, 900006, None, None, 1),
        (900101, "tea_li", "李老师", "teacher", default_hash, None, 900001, None, 1),
        (900102, "tea_zhou", "周老师", "teacher", default_hash, None, 900002, None, 1),
        (900201, "counselor_chen", "陈辅导员", "counselor", default_hash, None, None, 900001, 1),
        (900202, "counselor_lin", "林辅导员", "counselor", default_hash, None, None, 900002, 1),
    ]
    conn.executemany(
        """
        INSERT OR REPLACE INTO app_user
        (id, username, display_name, role, password_hash, student_id, teacher_id, counselor_id, college_id, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        users,
    )
    conn.executemany(
        "INSERT OR REPLACE INTO user_role(user_id, role_code) VALUES (?, ?)",
        [(row[0], row[3]) for row in users],
    )
