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
IDENTITY_POSITION_MIGRATION = "b6_identity_position_authorization_v1"


def ensure_mvp_schema(db_path: Path | None = None) -> None:
    """Create MVP business tables and deterministic demo rows if the teaching DB exists."""
    db_path = db_path or DB_PATH
    if not db_path.exists():
        return
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _create_tables(conn)
        _seed_demo_scope(conn)
        if not _migration_applied(conn, IDENTITY_POSITION_MIGRATION):
            _seed_organization_model(conn)
            _mark_migration(conn, IDENTITY_POSITION_MIGRATION)
        else:
            # The staff directory is a projection of authoritative teaching and
            # counselor identities and may receive new rows after the migration.
            # Formal positions and legacy role grants must never be re-seeded.
            _sync_staff_directory(conn)
        _seed_lifecycle_baseline(conn)
        conn.commit()
    # V3 and later schema changes use an ordered, checksummed transaction ledger.
    # Keep this outside the legacy connection so a V3 failure is rolled back as
    # one independent unit and can be retried safely on the next startup.
    from app.core.v3_migrations import apply_v3_migrations

    apply_v3_migrations(db_path)


def identity_position_migration_report(db_path: Path | None = None) -> dict[str, int | bool | str]:
    """Return machine-checkable B.6 migration invariants without mutating data."""
    db_path = db_path or DB_PATH
    if not db_path.exists():
        return {"migration_key": IDENTITY_POSITION_MIGRATION, "applied": False, "database_missing": True}
    with sqlite3.connect(db_path) as conn:
        applied = _migration_applied(conn, IDENTITY_POSITION_MIGRATION)
        active_accounts = int(conn.execute(
            "SELECT count(*) FROM app_user WHERE active = 1 AND status = 'active'"
        ).fetchone()[0])
        accounts_without_binding = int(conn.execute(
            """
            SELECT count(*) FROM app_user au
            WHERE au.active = 1 AND au.status = 'active' AND NOT EXISTS (
                SELECT 1 FROM user_role_binding urb
                LEFT JOIN position_assignment pa ON pa.id = urb.position_assignment_id
                WHERE urb.user_id = au.id AND urb.status = 'active'
                  AND datetime(urb.valid_from) <= datetime('now')
                  AND (urb.valid_until IS NULL OR datetime(urb.valid_until) > datetime('now'))
                  AND (pa.id IS NULL OR (pa.status = 'active'
                       AND (pa.valid_until IS NULL OR datetime(pa.valid_until) > datetime('now'))))
            )
            """
        ).fetchone()[0])
        assignments_without_binding = int(conn.execute(
            """
            SELECT count(*) FROM position_assignment pa
            WHERE pa.status = 'active'
              AND (pa.valid_until IS NULL OR datetime(pa.valid_until) > datetime('now'))
              AND NOT EXISTS (
                  SELECT 1 FROM user_role_binding urb
                  WHERE urb.position_assignment_id = pa.id AND urb.status = 'active'
                    AND (urb.valid_until IS NULL OR datetime(urb.valid_until) > datetime('now'))
              )
            """
        ).fetchone()[0])
        required_scope_missing = int(conn.execute(
            """
            SELECT count(*) FROM user_role_binding urb
            WHERE urb.status = 'active'
              AND urb.role_code IN ('student','teacher','counselor','college_manager',
                                    'identity_reviewer','academic_office','admin')
              AND NOT EXISTS (
                  SELECT 1 FROM role_scope_binding rsb
                  WHERE rsb.role_binding_id = urb.id AND rsb.scope_type = CASE urb.role_code
                      WHEN 'student' THEN 'self'
                      WHEN 'teacher' THEN 'teacher'
                      WHEN 'counselor' THEN 'class_group'
                      WHEN 'college_manager' THEN 'college'
                      WHEN 'identity_reviewer' THEN 'college'
                      WHEN 'academic_office' THEN 'academic_office'
                      WHEN 'admin' THEN 'platform' END
              )
            """
        ).fetchone()[0])
        generic_formal_occupants = int(conn.execute(
            """
            SELECT count(*) FROM position_assignment pa
            JOIN app_user au ON au.id = pa.user_id
            WHERE pa.status = 'active' AND lower(au.username) IN ('admin','jwc','college')
            """
        ).fetchone()[0])
    return {
        "migration_key": IDENTITY_POSITION_MIGRATION,
        "applied": applied,
        "active_accounts": active_accounts,
        "accounts_without_active_binding": accounts_without_binding,
        "active_assignments_without_binding": assignments_without_binding,
        "active_bindings_missing_required_scope": required_scope_missing,
        "generic_formal_position_occupants": generic_formal_occupants,
    }


def expire_due_position_assignments(db_path: Path | None = None) -> int:
    """Persist due position/binding expiry and revoke all sessions for affected users."""
    db_path = db_path or DB_PATH
    if not db_path.exists():
        return 0
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT pa.id, pa.user_id, pa.valid_until, ops.position_code
            FROM position_assignment pa
            JOIN organization_position_slot ops ON ops.id = pa.position_slot_id
            WHERE pa.status = 'active' AND pa.valid_until IS NOT NULL
              AND datetime(pa.valid_until) <= datetime('now')
            ORDER BY pa.id
            """
        ).fetchall()
        if not rows:
            return 0
        now = conn.execute("SELECT datetime('now')").fetchone()[0]
        assignment_ids = [int(row["id"]) for row in rows]
        marks = ",".join("?" for _ in assignment_ids)
        conn.execute(
            f"UPDATE position_assignment SET status = 'expired', ended_at = ?, end_reason = '任期到期自动失效', updated_at = ? WHERE id IN ({marks})",
            (now, now, *assignment_ids),
        )
        conn.execute(
            f"UPDATE user_role_binding SET status = 'expired', revoked_at = ?, revoke_reason = '任期到期自动失效', updated_at = ? WHERE position_assignment_id IN ({marks}) AND status = 'active'",
            (now, now, *assignment_ids),
        )
        user_ids = sorted({int(row["user_id"]) for row in rows})
        user_marks = ",".join("?" for _ in user_ids)
        conn.execute(
            f"UPDATE app_user SET session_version = session_version + 1, updated_at = ? WHERE id IN ({user_marks})",
            (now, *user_ids),
        )
        conn.executemany(
            """
            INSERT INTO audit_log(actor_user, actor_role, resource_type, resource_id, action,
                                  before_state, after_state, created_at)
            VALUES ('system', 'system', 'position_assignment', ?, 'expired', 'active', ?, ?)
            """,
            [
                (int(row["id"]), f"expired_at={now};valid_until={row['valid_until']}", now)
                for row in rows
            ],
        )
        conn.commit()
        return len(rows)


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

        CREATE TABLE IF NOT EXISTS schema_migration (
            migration_key TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS identity_application (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            identity_type TEXT NOT NULL CHECK(identity_type IN ('student', 'teacher')),
            submitted_identifier TEXT NOT NULL,
            submitted_name TEXT NOT NULL,
            matched_entity_id INTEGER NOT NULL,
            matched_college_id INTEGER,
            matched_class_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected', 'withdrawn')),
            assigned_approver_user_id INTEGER,
            assigned_approver_role TEXT NOT NULL,
            reviewed_by_user_id INTEGER,
            review_note TEXT,
            submitted_at TEXT NOT NULL,
            reviewed_at TEXT,
            FOREIGN KEY (user_id) REFERENCES app_user(id),
            FOREIGN KEY (assigned_approver_user_id) REFERENCES app_user(id),
            FOREIGN KEY (reviewed_by_user_id) REFERENCES app_user(id)
        );

        CREATE TABLE IF NOT EXISTS identity_binding (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE,
            identity_type TEXT NOT NULL CHECK(identity_type IN ('student', 'teacher', 'counselor')),
            entity_id INTEGER NOT NULL,
            verified_by_user_id INTEGER,
            verified_at TEXT NOT NULL,
            UNIQUE(identity_type, entity_id),
            FOREIGN KEY (user_id) REFERENCES app_user(id),
            FOREIGN KEY (verified_by_user_id) REFERENCES app_user(id)
        );

        CREATE TABLE IF NOT EXISTS organization_unit (
            id INTEGER PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            unit_type TEXT NOT NULL CHECK(unit_type IN ('school', 'academic_office', 'college', 'department', 'platform')),
            parent_id INTEGER,
            source_college_id INTEGER UNIQUE,
            status TEXT NOT NULL DEFAULT 'active',
            valid_from TEXT,
            valid_until TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (parent_id) REFERENCES organization_unit(id)
        );

        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY,
            staff_no TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            college_id INTEGER,
            department_code TEXT,
            employment_status TEXT NOT NULL DEFAULT 'active',
            staff_type TEXT NOT NULL DEFAULT 'staff',
            teacher_id INTEGER UNIQUE,
            counselor_id INTEGER UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (college_id) REFERENCES college(id)
        );

        CREATE TABLE IF NOT EXISTS person_identity (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE,
            person_type TEXT NOT NULL CHECK(person_type IN ('student', 'staff')),
            entity_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'verified',
            verified_by_user_id INTEGER,
            verified_at TEXT NOT NULL,
            UNIQUE(person_type, entity_id),
            FOREIGN KEY (user_id) REFERENCES app_user(id),
            FOREIGN KEY (verified_by_user_id) REFERENCES app_user(id)
        );

        CREATE TABLE IF NOT EXISTS organization_position_slot (
            id INTEGER PRIMARY KEY,
            organization_unit_id INTEGER NOT NULL,
            position_code TEXT NOT NULL,
            title TEXT NOT NULL,
            min_occupants INTEGER NOT NULL DEFAULT 0,
            max_occupants INTEGER,
            approval_policy TEXT NOT NULL DEFAULT 'manager',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(organization_unit_id, position_code),
            FOREIGN KEY (organization_unit_id) REFERENCES organization_unit(id)
        );

        CREATE TABLE IF NOT EXISTS position_assignment (
            id INTEGER PRIMARY KEY,
            position_slot_id INTEGER NOT NULL,
            staff_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            assignment_type TEXT NOT NULL DEFAULT 'primary' CHECK(assignment_type IN ('primary', 'deputy', 'acting', 'temporary', 'reviewer')),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('pending', 'active', 'suspended', 'ended', 'expired')),
            valid_from TEXT NOT NULL,
            valid_until TEXT,
            appointed_by_user_id INTEGER,
            appointment_reason TEXT NOT NULL,
            ended_by_user_id INTEGER,
            ended_at TEXT,
            end_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (position_slot_id) REFERENCES organization_position_slot(id),
            FOREIGN KEY (staff_id) REFERENCES staff(id),
            FOREIGN KEY (user_id) REFERENCES app_user(id),
            FOREIGN KEY (appointed_by_user_id) REFERENCES app_user(id),
            FOREIGN KEY (ended_by_user_id) REFERENCES app_user(id)
        );

        CREATE TABLE IF NOT EXISTS user_role_binding (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            role_code TEXT NOT NULL,
            position_assignment_id INTEGER,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('pending', 'active', 'suspended', 'revoked', 'expired')),
            source TEXT NOT NULL,
            granted_by_user_id INTEGER,
            grant_reason TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_until TEXT,
            revoked_by_user_id INTEGER,
            revoked_at TEXT,
            revoke_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES app_user(id),
            FOREIGN KEY (position_assignment_id) REFERENCES position_assignment(id),
            FOREIGN KEY (granted_by_user_id) REFERENCES app_user(id),
            FOREIGN KEY (revoked_by_user_id) REFERENCES app_user(id)
        );

        CREATE TABLE IF NOT EXISTS role_scope_binding (
            id INTEGER PRIMARY KEY,
            role_binding_id INTEGER NOT NULL,
            scope_type TEXT NOT NULL,
            scope_id INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(role_binding_id, scope_type, scope_id),
            FOREIGN KEY (role_binding_id) REFERENCES user_role_binding(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS organization_review_queue (
            id INTEGER PRIMARY KEY,
            organization_unit_id INTEGER NOT NULL,
            queue_type TEXT NOT NULL,
            scope_type TEXT NOT NULL,
            scope_id INTEGER,
            name TEXT NOT NULL,
            escalation_queue_id INTEGER,
            sla_hours INTEGER NOT NULL DEFAULT 48,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(queue_type, scope_type, scope_id),
            FOREIGN KEY (organization_unit_id) REFERENCES organization_unit(id),
            FOREIGN KEY (escalation_queue_id) REFERENCES organization_review_queue(id)
        );

        CREATE TABLE IF NOT EXISTS review_task (
            id INTEGER PRIMARY KEY,
            queue_id INTEGER NOT NULL,
            task_type TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'claimed', 'approved', 'rejected', 'escalated', 'cancelled')),
            claimed_by_user_id INTEGER,
            claimed_at TEXT,
            processed_by_user_id INTEGER,
            processed_at TEXT,
            due_at TEXT,
            escalated_from_queue_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(task_type, resource_type, resource_id),
            FOREIGN KEY (queue_id) REFERENCES organization_review_queue(id),
            FOREIGN KEY (claimed_by_user_id) REFERENCES app_user(id),
            FOREIGN KEY (processed_by_user_id) REFERENCES app_user(id)
        );

        CREATE TABLE IF NOT EXISTS password_reset_request (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            requested_by_user_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES app_user(id),
            FOREIGN KEY (requested_by_user_id) REFERENCES app_user(id)
        );

        CREATE TABLE IF NOT EXISTS person_affiliation (
            id INTEGER PRIMARY KEY,
            person_identity_id INTEGER NOT NULL,
            affiliation_type TEXT NOT NULL CHECK(affiliation_type IN ('student', 'staff')),
            source_entity_id INTEGER NOT NULL,
            organization_unit_id INTEGER,
            status TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_until TEXT,
            source_system TEXT NOT NULL DEFAULT 'local',
            source_event_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(person_identity_id, affiliation_type, source_entity_id, valid_from),
            UNIQUE(source_system, source_event_id),
            FOREIGN KEY (person_identity_id) REFERENCES person_identity(id),
            FOREIGN KEY (organization_unit_id) REFERENCES organization_unit(id)
        );

        CREATE TABLE IF NOT EXISTS identity_lifecycle_event (
            id INTEGER PRIMARY KEY,
            event_type TEXT NOT NULL,
            target_user_id INTEGER NOT NULL,
            person_identity_id INTEGER NOT NULL,
            affiliation_id INTEGER,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN
                ('draft','pending_approval','approved','scheduled','executing','completed','failed','canceled')),
            effective_at TEXT,
            reason TEXT NOT NULL,
            evidence TEXT,
            requested_by_user_id INTEGER,
            approved_by_user_id INTEGER,
            executed_by_user_id INTEGER,
            idempotency_key TEXT UNIQUE,
            before_snapshot TEXT,
            after_snapshot TEXT,
            impact_snapshot TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (target_user_id) REFERENCES app_user(id),
            FOREIGN KEY (person_identity_id) REFERENCES person_identity(id),
            FOREIGN KEY (affiliation_id) REFERENCES person_affiliation(id),
            FOREIGN KEY (requested_by_user_id) REFERENCES app_user(id),
            FOREIGN KEY (approved_by_user_id) REFERENCES app_user(id),
            FOREIGN KEY (executed_by_user_id) REFERENCES app_user(id)
        );

        CREATE TABLE IF NOT EXISTS account_closure_request (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            lifecycle_event_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','cooling_off','canceled','completed','rejected')),
            requested_at TEXT NOT NULL,
            cooling_off_until TEXT NOT NULL,
            verification_hash TEXT,
            blocked_reason TEXT,
            canceled_at TEXT,
            completed_at TEXT,
            processed_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES app_user(id),
            FOREIGN KEY (lifecycle_event_id) REFERENCES identity_lifecycle_event(id),
            FOREIGN KEY (processed_by_user_id) REFERENCES app_user(id)
        );

        CREATE TABLE IF NOT EXISTS responsibility_handover (
            id INTEGER PRIMARY KEY,
            lifecycle_event_id INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            from_user_id INTEGER NOT NULL,
            to_user_id INTEGER,
            to_queue_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','assigned','confirmed','exception','canceled')),
            note TEXT,
            assigned_at TEXT,
            confirmed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(lifecycle_event_id, resource_type, resource_id),
            FOREIGN KEY (lifecycle_event_id) REFERENCES identity_lifecycle_event(id),
            FOREIGN KEY (from_user_id) REFERENCES app_user(id),
            FOREIGN KEY (to_user_id) REFERENCES app_user(id),
            FOREIGN KEY (to_queue_id) REFERENCES organization_review_queue(id)
        );

        CREATE TABLE IF NOT EXISTS account_status_history (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            lifecycle_event_id INTEGER,
            from_status TEXT,
            to_status TEXT NOT NULL,
            actor_user_id INTEGER,
            reason TEXT NOT NULL,
            session_version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES app_user(id),
            FOREIGN KEY (lifecycle_event_id) REFERENCES identity_lifecycle_event(id),
            FOREIGN KEY (actor_user_id) REFERENCES app_user(id)
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

        CREATE TABLE IF NOT EXISTS course_announcement (
            id INTEGER PRIMARY KEY, teaching_class_id INTEGER NOT NULL, publisher_user_id INTEGER NOT NULL,
            title TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
            published_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS announcement_receipt (
            id INTEGER PRIMARY KEY, announcement_id INTEGER NOT NULL, recipient_user_id INTEGER NOT NULL,
            delivered_at TEXT NOT NULL, read_at TEXT, UNIQUE(announcement_id, recipient_user_id)
        );
        CREATE TABLE IF NOT EXISTS course_resource (
            id INTEGER PRIMARY KEY, teaching_class_id INTEGER NOT NULL, publisher_user_id INTEGER NOT NULL,
            title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', file_name TEXT NOT NULL DEFAULT '',
            resource_url TEXT NOT NULL DEFAULT '', file_key TEXT, file_size INTEGER, content_type TEXT,
            visible_from TEXT, visible_until TEXT,
            status TEXT NOT NULL DEFAULT 'published', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS course_session (
            id INTEGER PRIMARY KEY,
            teaching_class_id INTEGER NOT NULL,
            session_no INTEGER NOT NULL,
            session_date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            classroom TEXT NOT NULL DEFAULT '',
            topic TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'scheduled',
            created_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(teaching_class_id, session_no, session_date)
        );

        CREATE TABLE IF NOT EXISTS course_question (
            id INTEGER PRIMARY KEY,
            teaching_class_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            visibility TEXT NOT NULL DEFAULT 'public',
            status TEXT NOT NULL DEFAULT 'open',
            pinned INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS course_question_reply (
            id INTEGER PRIMARY KEY,
            question_id INTEGER NOT NULL,
            reply_user_id INTEGER NOT NULL,
            reply_role TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS teaching_issue (
            id INTEGER PRIMARY KEY, issue_key TEXT NOT NULL UNIQUE, issue_type TEXT NOT NULL,
            teaching_class_id INTEGER NOT NULL, college_id INTEGER NOT NULL, evidence TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', resolution TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, resolved_at TEXT
        );
        CREATE TABLE IF NOT EXISTS grade_submission (
            id INTEGER PRIMARY KEY, teaching_class_id INTEGER NOT NULL UNIQUE, submitter_user_id INTEGER NOT NULL,
            version_no INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'draft', returned_reason TEXT NOT NULL DEFAULT '',
            submitted_at TEXT, reviewed_by_user_id INTEGER, reviewed_at TEXT, published_at TEXT, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS grade_submission_detail (
            id INTEGER PRIMARY KEY,
            grade_submission_id INTEGER NOT NULL,
            version_no INTEGER NOT NULL,
            enrollment_id INTEGER NOT NULL,
            student_no_snapshot TEXT NOT NULL,
            student_name_snapshot TEXT NOT NULL,
            final_score REAL NOT NULL CHECK(final_score >= 0 AND final_score <= 100),
            import_row_no INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(grade_submission_id, version_no, enrollment_id)
        );
        CREATE TABLE IF NOT EXISTS academic_teaching_operations_summary (
            teaching_class_id INTEGER PRIMARY KEY, college_id INTEGER NOT NULL, college_name TEXT NOT NULL,
            course_name TEXT NOT NULL, teacher_name TEXT NOT NULL, year INTEGER NOT NULL, semester TEXT NOT NULL,
            classroom TEXT NOT NULL, capacity INTEGER NOT NULL, enrolled_count INTEGER NOT NULL, issue_count INTEGER NOT NULL,
            grade_status TEXT NOT NULL, refreshed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS college_teacher_workload_summary (
            college_id INTEGER NOT NULL, teacher_name TEXT NOT NULL, class_count INTEGER NOT NULL,
            student_count INTEGER NOT NULL, refreshed_at TEXT NOT NULL, PRIMARY KEY(college_id, teacher_name)
        );
        CREATE TABLE IF NOT EXISTS college_quality_summary (
            college_id INTEGER NOT NULL, course_name TEXT NOT NULL, class_count INTEGER NOT NULL,
            enrolled_count INTEGER NOT NULL, sample_size INTEGER NOT NULL, average_score REAL, pass_rate REAL,
            refreshed_at TEXT NOT NULL, PRIMARY KEY(college_id, course_name)
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
        CREATE INDEX IF NOT EXISTS idx_identity_application_user ON identity_application(user_id, submitted_at);
        CREATE INDEX IF NOT EXISTS idx_identity_application_status ON identity_application(status, assigned_approver_role);
        CREATE INDEX IF NOT EXISTS idx_identity_application_student_scope ON identity_application(identity_type, matched_class_id, status);
        CREATE INDEX IF NOT EXISTS idx_identity_application_teacher_scope ON identity_application(identity_type, matched_college_id, status);
        CREATE INDEX IF NOT EXISTS idx_staff_college ON staff(college_id, employment_status);
        CREATE INDEX IF NOT EXISTS idx_position_assignment_slot ON position_assignment(position_slot_id, status, valid_until);
        CREATE INDEX IF NOT EXISTS idx_role_binding_user ON user_role_binding(user_id, status, valid_until);
        CREATE INDEX IF NOT EXISTS idx_role_scope_binding ON role_scope_binding(role_binding_id, scope_type, scope_id);
        CREATE INDEX IF NOT EXISTS idx_person_affiliation_identity ON person_affiliation(person_identity_id, status, valid_until);
        CREATE INDEX IF NOT EXISTS idx_lifecycle_event_target ON identity_lifecycle_event(target_user_id, status, effective_at);
        CREATE INDEX IF NOT EXISTS idx_handover_event ON responsibility_handover(lifecycle_event_id, status);
        CREATE INDEX IF NOT EXISTS idx_account_status_history_user ON account_status_history(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_review_task_queue ON review_task(queue_id, status, due_at);
        CREATE INDEX IF NOT EXISTS idx_support_case_student ON support_case(student_id);
        CREATE INDEX IF NOT EXISTS idx_support_case_counselor ON support_case(counselor_id);
        CREATE INDEX IF NOT EXISTS idx_support_request_student ON support_request(student_id);
        CREATE INDEX IF NOT EXISTS idx_support_request_counselor ON support_request(counselor_id);
        CREATE INDEX IF NOT EXISTS idx_submission_version_submission ON submission_version(submission_id);
        CREATE INDEX IF NOT EXISTS idx_grading_submission ON grading_record(submission_id);
        CREATE INDEX IF NOT EXISTS idx_notification_recipient ON notification(recipient_username);
        CREATE INDEX IF NOT EXISTS idx_course_session_class ON course_session(teaching_class_id, session_date, session_no);
        CREATE INDEX IF NOT EXISTS idx_course_question_class ON course_question(teaching_class_id, status, pinned, created_at);
        CREATE INDEX IF NOT EXISTS idx_course_question_reply ON course_question_reply(question_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_teaching_issue_scope ON teaching_issue(college_id, status, issue_type);
        CREATE INDEX IF NOT EXISTS idx_grade_submission_status ON grade_submission(status, teaching_class_id);
        CREATE INDEX IF NOT EXISTS idx_grade_submission_detail_version ON grade_submission_detail(grade_submission_id, version_no);
        CREATE INDEX IF NOT EXISTS idx_course_analytics_class ON course_assignment_analytics(teaching_class_id, teacher_id);
        CREATE INDEX IF NOT EXISTS idx_student_analytics_scope ON student_task_analytics(teaching_class_id, student_id);
        CREATE INDEX IF NOT EXISTS idx_analytics_log_user ON analytics_query_log(username, teaching_class_id, created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_enrollment_class_student ON enrollment(teaching_class_id, student_id);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_submission_assignment_student ON assignment_submission(assignment_id, student_id);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_submission_version_no ON submission_version(submission_id, version_no);
        """
    )
    # Legacy Stage E records only changed workflow status and did not contain
    # any student scores. They are not valid submissions under the current
    # snapshot workflow, so reopen them as drafts for an explicit CSV import.
    conn.execute(
        """UPDATE grade_submission
           SET status='draft',returned_reason='',submitted_at=NULL,
               reviewed_by_user_id=NULL,reviewed_at=NULL,published_at=NULL
           WHERE NOT EXISTS (
               SELECT 1 FROM grade_submission_detail gd
               WHERE gd.grade_submission_id=grade_submission.id
                 AND gd.version_no=grade_submission.version_no
           )"""
    )
    _ensure_column(conn, "assignment", "status", "TEXT NOT NULL DEFAULT 'published'")
    _ensure_column(conn, "assignment", "instructions", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "assignment", "allow_late", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "assignment_submission", "feedback", "TEXT")
    _ensure_column(conn, "submission_version", "file_key", "TEXT")
    _ensure_column(conn, "submission_version", "file_size", "INTEGER")
    _ensure_column(conn, "course_resource", "file_key", "TEXT")
    _ensure_column(conn, "course_resource", "file_size", "INTEGER")
    _ensure_column(conn, "course_resource", "content_type", "TEXT")
    _ensure_column(conn, "attendance", "course_session_id", "INTEGER")
    _ensure_column(conn, "attendance", "note", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "attendance", "recorded_by_user_id", "INTEGER")
    _ensure_column(conn, "attendance", "updated_at", "TEXT")
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
    _ensure_column(conn, "app_user", "status", "TEXT NOT NULL DEFAULT 'active'")
    _ensure_column(conn, "app_user", "created_at", "TEXT")
    _ensure_column(conn, "app_user", "updated_at", "TEXT")
    _ensure_column(conn, "app_user", "session_version", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "app_user", "failed_login_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "app_user", "locked_until", "TEXT")
    _ensure_column(conn, "app_user", "must_reset_password", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "app_user", "last_login_at", "TEXT")
    _ensure_column(conn, "user_role_binding", "selectable", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "identity_application", "review_queue_id", "INTEGER")
    _ensure_column(conn, "identity_application", "review_task_id", "INTEGER")
    _ensure_column(conn, "identity_application", "matched_staff_id", "INTEGER")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_session_student ON attendance(course_session_id, student_id) WHERE course_session_id IS NOT NULL")
    _link_legacy_attendance_sessions(conn)


def _link_legacy_attendance_sessions(conn: sqlite3.Connection) -> None:
    """Give legacy attendance rows a real course-session identity without changing facts."""
    rows = conn.execute(
        "SELECT DISTINCT teaching_class_id, session_no, class_date FROM attendance WHERE course_session_id IS NULL"
    ).fetchall()
    for teaching_class_id, session_no, class_date in rows:
        classroom_row = conn.execute("SELECT classroom FROM teaching_class WHERE id = ?", (teaching_class_id,)).fetchone()
        now = f"{class_date}T00:00:00+00:00"
        conn.execute(
            "INSERT OR IGNORE INTO course_session(teaching_class_id, session_no, session_date, classroom, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'completed', ?, ?)",
            (teaching_class_id, session_no, class_date, classroom_row[0] if classroom_row else "", now, now),
        )
        session = conn.execute(
            "SELECT id FROM course_session WHERE teaching_class_id = ? AND session_no = ? AND session_date = ?",
            (teaching_class_id, session_no, class_date),
        ).fetchone()
        conn.execute(
            "UPDATE attendance SET course_session_id = ?, updated_at = COALESCE(updated_at, ?) WHERE teaching_class_id = ? AND session_no = ? AND class_date = ? AND course_session_id IS NULL AND NOT EXISTS (SELECT 1 FROM attendance current WHERE current.course_session_id = ? AND current.student_id = attendance.student_id)",
            (session[0], now, teaching_class_id, session_no, class_date, session[0]),
        )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migration_applied(conn: sqlite3.Connection, migration_key: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM schema_migration WHERE migration_key = ?", (migration_key,)
    ).fetchone() is not None


def _mark_migration(conn: sqlite3.Connection, migration_key: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO schema_migration(migration_key, applied_at) VALUES (?, datetime('now'))",
        (migration_key,),
    )


def _sync_staff_directory(conn: sqlite3.Connection) -> None:
    """Project authoritative teacher/counselor identities into the staff directory."""
    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    conn.execute(
        """
        INSERT OR IGNORE INTO staff
        (staff_no, name, college_id, department_code, employment_status, staff_type,
         teacher_id, counselor_id, created_at, updated_at)
        SELECT teacher_no, name, college_id, 'TEACHING', 'active', 'teacher', id, NULL, ?, ?
        FROM teacher
        """,
        (now, now),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO staff
        (staff_no, name, college_id, department_code, employment_status, staff_type,
         teacher_id, counselor_id, created_at, updated_at)
        SELECT counselor_no, name, college_id, 'STUDENT_AFFAIRS', 'active', 'counselor', NULL, id, ?, ?
        FROM counselor
        """,
        (now, now),
    )


def _ensure_lifecycle_identity(conn: sqlite3.Connection, user_id: int) -> None:
    """Create the B.7 base affiliation and hidden self-service binding for one verified person."""
    row = conn.execute(
        """
        SELECT pi.id, pi.person_type, pi.entity_id, pi.verified_at, au.status AS account_status
        FROM person_identity pi JOIN app_user au ON au.id = pi.user_id
        WHERE pi.user_id = ? AND pi.status = 'verified'
        """,
        (user_id,),
    ).fetchone()
    if not row:
        return
    person_identity_id, person_type, entity_id, verified_at, account_status = row
    organization_unit_id: int | None = None
    if person_type == "student":
        source = conn.execute("SELECT college_id, status FROM student WHERE id = ?", (entity_id,)).fetchone()
        if not source:
            return
        college_id, raw_status = source
        affiliation_status = {
            "active": "active", "leave": "leave", "graduated": "graduated",
            "withdrawn": "withdrawn", "dismissed": "dismissed",
        }.get(str(raw_status), "active")
        affiliation_type = "student"
    else:
        source = conn.execute("SELECT college_id, employment_status FROM staff WHERE id = ?", (entity_id,)).fetchone()
        if not source:
            return
        college_id, raw_status = source
        affiliation_status = {
            "active": "active", "leave": "leave", "seconded": "seconded",
            "transferred": "transferred", "retired": "retired", "terminated": "terminated",
        }.get(str(raw_status), "active")
        affiliation_type = "staff"
    if college_id is not None:
        organization_unit_id = _college_unit_id(int(college_id))
    exists = conn.execute(
        """
        SELECT 1 FROM person_affiliation
        WHERE person_identity_id = ? AND affiliation_type = ? AND source_entity_id = ?
        LIMIT 1
        """,
        (person_identity_id, affiliation_type, entity_id),
    ).fetchone()
    if not exists:
        created_at = str(verified_at or ORG_SEED_TIME)
        conn.execute(
            """
            INSERT INTO person_affiliation
            (person_identity_id, affiliation_type, source_entity_id, organization_unit_id,
             status, valid_from, source_system, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'migration', ?, ?)
            """,
            (person_identity_id, affiliation_type, entity_id, organization_unit_id,
             affiliation_status, created_at, created_at, created_at),
        )
    _ensure_role_binding(
        conn, int(user_id), "self_service", "identity",
        [("person_identity", int(person_identity_id))], None,
        "已核验自然人基础自助身份", selectable=False,
    )
    if not conn.execute(
        "SELECT 1 FROM account_status_history WHERE user_id = ? LIMIT 1", (user_id,)
    ).fetchone():
        session_version = int(conn.execute(
            "SELECT session_version FROM app_user WHERE id = ?", (user_id,)
        ).fetchone()[0])
        conn.execute(
            """
            INSERT INTO account_status_history
            (user_id, from_status, to_status, reason, session_version, created_at)
            VALUES (?, NULL, ?, 'B.7-0 生命周期基线', ?, datetime('now'))
            """,
            (user_id, str(account_status), session_version),
        )


def _seed_lifecycle_baseline(conn: sqlite3.Connection) -> None:
    user_ids = [int(row[0]) for row in conn.execute(
        "SELECT user_id FROM person_identity WHERE status = 'verified' ORDER BY user_id"
    ).fetchall()]
    for user_id in user_ids:
        _ensure_lifecycle_identity(conn, user_id)


def _seed_demo_scope(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO role(id, code, label) VALUES (?, ?, ?)",
        [
            (1, "student", "学生"),
            (2, "teacher", "任课教师"),
            (3, "counselor", "辅导员"),
            (4, "admin", "系统管理员"),
            (5, "academic_office", "教务处老师"),
            (6, "college_manager", "学院负责人"),
            (7, "pending", "待审核账号"),
            (8, "staff", "已验证教职工"),
            (9, "identity_reviewer", "身份审核员"),
            (10, "self_service", "个人自助"),
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

    legacy_default_hash = "pbkdf2_sha256$260000$demo$8xwSFNNYzfn1zs9ldG0SOxgUay68z1Hir9P0W+Y3BEg="
    default_hash = "pbkdf2_sha256$260000$Dj8GCQTWQUI-ZwaZ$tHkbJQ+5WRN/VByU9Ryl4+YVC2dh1KFHBpjeTeq7H7A="
    users = [
        (910001, "admin", "校级管理员", "admin", default_hash, None, None, None, None),
        (910002, "jwc", "教务处老师", "academic_office", default_hash, None, None, None, None),
        (910003, "college", "学院负责人", "college_manager", default_hash, None, None, None, 1),
        (910004, "teacher", "任课教师", "teacher", default_hash, None, 37, None, None),
        (910005, "student", "学生用户", "student", default_hash, 1, None, None, None),
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
        INSERT OR IGNORE INTO app_user
        (id, username, display_name, role, password_hash, student_id, teacher_id, counselor_id, college_id, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        users,
    )
    conn.execute(
        "UPDATE app_user SET password_hash = ? WHERE password_hash = ?",
        (default_hash, legacy_default_hash),
    )
    conn.executemany(
        "INSERT OR REPLACE INTO user_role(user_id, role_code) VALUES (?, ?)",
        [(row[0], row[3]) for row in users],
    )
    conn.execute("UPDATE app_user SET status = CASE WHEN active = 1 THEN 'active' ELSE 'disabled' END WHERE status IS NULL OR status = ''")
    conn.execute("UPDATE app_user SET created_at = COALESCE(created_at, '2026-07-16T00:00:00+00:00'), updated_at = COALESCE(updated_at, '2026-07-16T00:00:00+00:00')")
    for user_id, _username, _name, _role, _password, student_id, teacher_id, counselor_id, _college_id in users:
        identity_type = "student" if student_id else "teacher" if teacher_id else "counselor" if counselor_id else None
        entity_id = student_id or teacher_id or counselor_id
        if identity_type and entity_id:
            conn.execute(
                """
                INSERT OR IGNORE INTO identity_binding
                (user_id, identity_type, entity_id, verified_by_user_id, verified_at)
                VALUES (?, ?, ?, NULL, '2026-07-16T00:00:00+00:00')
                """,
                (user_id, identity_type, entity_id),
            )


ORG_SEED_TIME = "2026-07-16T00:00:00+00:00"
ORG_SCHOOL_ID = 100000
ORG_ACADEMIC_ID = 100001
ORG_PLATFORM_ID = 100002


def _college_unit_id(college_id: int) -> int:
    return 110000 + int(college_id)


def _ensure_role_binding(
    conn: sqlite3.Connection,
    user_id: int,
    role_code: str,
    source: str,
    scopes: list[tuple[str, int | None]],
    position_assignment_id: int | None = None,
    reason: str = "初始化迁移",
    selectable: bool = True,
) -> int:
    row = conn.execute(
        """
        SELECT id FROM user_role_binding
        WHERE user_id = ? AND role_code = ? AND status = 'active'
          AND COALESCE(position_assignment_id, 0) = COALESCE(?, 0)
        ORDER BY id LIMIT 1
        """,
        (user_id, role_code, position_assignment_id),
    ).fetchone()
    if row:
        binding_id = int(row[0])
    else:
        cursor = conn.execute(
            """
            INSERT INTO user_role_binding
            (user_id, role_code, position_assignment_id, status, source, granted_by_user_id,
             grant_reason, valid_from, valid_until, created_at, updated_at, selectable)
            VALUES (?, ?, ?, 'active', ?, NULL, ?, ?, NULL, ?, ?, ?)
            """,
            (user_id, role_code, position_assignment_id, source, reason, ORG_SEED_TIME,
             ORG_SEED_TIME, ORG_SEED_TIME, 1 if selectable else 0),
        )
        binding_id = int(cursor.lastrowid)
    if not selectable:
        conn.execute("UPDATE user_role_binding SET selectable = 0 WHERE id = ?", (binding_id,))
    for scope_type, scope_id in scopes:
        conn.execute(
            """
            INSERT OR IGNORE INTO role_scope_binding(role_binding_id, scope_type, scope_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (binding_id, scope_type, scope_id, ORG_SEED_TIME),
        )
    return binding_id


def _ensure_position_assignment(
    conn: sqlite3.Connection,
    slot_id: int,
    staff_id: int,
    user_id: int,
    assignment_type: str,
    reason: str,
) -> int:
    row = conn.execute(
        """
        SELECT id FROM position_assignment
        WHERE position_slot_id = ? AND user_id = ? AND status = 'active'
        ORDER BY id LIMIT 1
        """,
        (slot_id, user_id),
    ).fetchone()
    if row:
        return int(row[0])
    cursor = conn.execute(
        """
        INSERT INTO position_assignment
        (position_slot_id, staff_id, user_id, assignment_type, status, valid_from, valid_until,
         appointed_by_user_id, appointment_reason, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'active', ?, NULL, NULL, ?, ?, ?)
        """,
        (slot_id, staff_id, user_id, assignment_type, ORG_SEED_TIME, reason, ORG_SEED_TIME, ORG_SEED_TIME),
    )
    return int(cursor.lastrowid)


def _seed_organization_model(conn: sqlite3.Connection) -> None:
    """Seed organization structure, coverage slots, named demo staff and role bindings."""
    conn.executemany(
        """
        INSERT OR IGNORE INTO organization_unit
        (id, code, name, unit_type, parent_id, source_college_id, status, valid_from, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """,
        [
            (ORG_SCHOOL_ID, "SCHOOL", "教学示范大学", "school", None, None, ORG_SEED_TIME, ORG_SEED_TIME, ORG_SEED_TIME),
            (ORG_ACADEMIC_ID, "ACADEMIC", "教务处", "academic_office", ORG_SCHOOL_ID, None, ORG_SEED_TIME, ORG_SEED_TIME, ORG_SEED_TIME),
            (ORG_PLATFORM_ID, "PLATFORM", "平台运维中心", "platform", ORG_SCHOOL_ID, None, ORG_SEED_TIME, ORG_SEED_TIME, ORG_SEED_TIME),
        ],
    )
    colleges = conn.execute("SELECT id, name FROM college ORDER BY id").fetchall()
    for college_id, college_name in colleges:
        conn.execute(
            """
            INSERT OR IGNORE INTO organization_unit
            (id, code, name, unit_type, parent_id, source_college_id, status, valid_from, created_at, updated_at)
            VALUES (?, ?, ?, 'college', ?, ?, 'active', ?, ?, ?)
            """,
            (_college_unit_id(college_id), f"COLLEGE-{college_id}", college_name, ORG_SCHOOL_ID,
             college_id, ORG_SEED_TIME, ORG_SEED_TIME, ORG_SEED_TIME),
        )

    slot_rows: list[tuple] = [
        (210001, ORG_ACADEMIC_ID, "academic_officer", "教务处老师", 2, None, "admin"),
        (220001, ORG_PLATFORM_ID, "platform_admin", "平台管理员", 2, None, "admin_reauth"),
    ]
    for college_id, _college_name in colleges:
        base = 200000 + int(college_id) * 10
        unit_id = _college_unit_id(college_id)
        slot_rows.extend([
            (base + 1, unit_id, "college_primary_manager", "学院主要负责人", 1, 1, "academic_or_admin"),
            (base + 2, unit_id, "college_deputy_manager", "学院分管负责人", 0, None, "academic_or_admin"),
            (base + 3, unit_id, "identity_reviewer", "学院身份审核员", 1, None, "college_manager"),
            (base + 4, unit_id, "counselor", "辅导员", 1, None, "college_manager"),
        ])
    conn.executemany(
        """
        INSERT OR IGNORE INTO organization_position_slot
        (id, organization_unit_id, position_code, title, min_occupants, max_occupants,
         approval_policy, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """,
        [(*row, ORG_SEED_TIME, ORG_SEED_TIME) for row in slot_rows],
    )

    # Staff directory: teachers and counselors are different natural persons even
    # when their source-table integer ids happen to overlap.
    conn.execute(
        """
        INSERT OR IGNORE INTO staff
        (staff_no, name, college_id, department_code, employment_status, staff_type,
         teacher_id, counselor_id, created_at, updated_at)
        SELECT teacher_no, name, college_id, 'TEACHING', 'active', 'teacher', id, NULL, ?, ? FROM teacher
        """,
        (ORG_SEED_TIME, ORG_SEED_TIME),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO staff
        (staff_no, name, college_id, department_code, employment_status, staff_type,
         teacher_id, counselor_id, created_at, updated_at)
        SELECT counselor_no, name, college_id, 'STUDENT_AFFAIRS', 'active', 'counselor', NULL, id, ?, ? FROM counselor
        """,
        (ORG_SEED_TIME, ORG_SEED_TIME),
    )

    # Named administrative demo people. Generic admin/jwc/college accounts remain
    # compatible but are not used as formal position occupants.
    admin_staff = [
        ("JWC001", "林教务", None, "ACADEMIC", "academic"),
        ("JWC002", "赵教务", None, "ACADEMIC", "academic"),
        ("SYS001", "周运维", None, "PLATFORM", "platform"),
        ("SYS002", "陈运维", None, "PLATFORM", "platform"),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO staff
        (staff_no, name, college_id, department_code, employment_status, staff_type,
         teacher_id, counselor_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'active', ?, NULL, NULL, ?, ?)
        """,
        [(*row, ORG_SEED_TIME, ORG_SEED_TIME) for row in admin_staff],
    )

    default_hash = "pbkdf2_sha256$260000$Dj8GCQTWQUI-ZwaZ$tHkbJQ+5WRN/VByU9Ryl4+YVC2dh1KFHBpjeTeq7H7A="
    for staff_no, name, _college_id, department, _staff_type in admin_staff:
        role = "academic_office" if department == "ACADEMIC" else "admin"
        conn.execute(
            """
            INSERT OR IGNORE INTO app_user
            (username, display_name, role, password_hash, active, status, created_at, updated_at, must_reset_password)
            VALUES (?, ?, ?, ?, 1, 'active', ?, ?, 1)
            """,
            (staff_no, name, role, default_hash, ORG_SEED_TIME, ORG_SEED_TIME),
        )
        user_id = int(conn.execute("SELECT id FROM app_user WHERE username = ?", (staff_no,)).fetchone()[0])
        staff_id = int(conn.execute("SELECT id FROM staff WHERE staff_no = ?", (staff_no,)).fetchone()[0])
        conn.execute(
            "INSERT OR IGNORE INTO person_identity(user_id, person_type, entity_id, status, verified_at) VALUES (?, 'staff', ?, 'verified', ?)",
            (user_id, staff_id, ORG_SEED_TIME),
        )
        slot_id = 210001 if role == "academic_office" else 220001
        assignment_type = "primary" if staff_no.endswith("1") else "deputy"
        assignment_id = _ensure_position_assignment(conn, slot_id, staff_id, user_id, assignment_type, "确定性组织演示数据")
        scope = [("academic_office", ORG_ACADEMIC_ID)] if role == "academic_office" else [("platform", ORG_PLATFORM_ID)]
        _ensure_role_binding(conn, user_id, role, "position", scope, assignment_id, "确定性组织演示数据")
        conn.execute("INSERT OR IGNORE INTO user_role(user_id, role_code) VALUES (?, ?)", (user_id, role))

    # One named primary manager and reviewer per college, selected from an
    # unbound teacher in that college.
    for college_id, _college_name in colleges:
        primary_slot = 200000 + int(college_id) * 10 + 1
        reviewer_slot = 200000 + int(college_id) * 10 + 3
        existing_primary = conn.execute(
            """
            SELECT pa.id AS assignment_id, pa.user_id, pa.staff_id, st.teacher_id
            FROM position_assignment pa JOIN staff st ON st.id = pa.staff_id
            WHERE pa.position_slot_id = ? AND pa.status = 'active'
            ORDER BY pa.id LIMIT 1
            """,
            (primary_slot,),
        ).fetchone()
        if existing_primary:
            primary_assignment = int(existing_primary[0])
            user_id = int(existing_primary[1])
            staff_id = int(existing_primary[2])
            teacher_id = int(existing_primary[3]) if existing_primary[3] is not None else None
            reviewer_assignment = _ensure_position_assignment(
                conn, reviewer_slot, staff_id, user_id, "reviewer", "学院身份审核员兼任"
            )
            _ensure_role_binding(
                conn, user_id, "college_manager", "position", [("college", int(college_id))],
                primary_assignment, "学院负责人确定性演示任命"
            )
            _ensure_role_binding(
                conn, user_id, "identity_reviewer", "position", [("college", int(college_id))],
                reviewer_assignment, "学院身份审核员兼任"
            )
            if teacher_id is not None:
                _ensure_role_binding(
                    conn, user_id, "teacher", "identity", [("teacher", teacher_id)], None, "教师自然身份"
                )
            conn.execute("INSERT OR IGNORE INTO user_role(user_id, role_code) VALUES (?, 'college_manager')", (user_id,))
            conn.execute("INSERT OR IGNORE INTO user_role(user_id, role_code) VALUES (?, 'identity_reviewer')", (user_id,))
            continue
        candidate = conn.execute(
            """
            SELECT t.id, t.teacher_no, t.name, s.id AS staff_id
            FROM teacher t JOIN staff s ON s.teacher_id = t.id
            LEFT JOIN app_user au ON au.teacher_id = t.id
            WHERE t.college_id = ? AND au.id IS NULL
            ORDER BY t.id LIMIT 1
            """,
            (college_id,),
        ).fetchone()
        if not candidate:
            continue
        teacher_id, staff_no, name, staff_id = int(candidate[0]), str(candidate[1]), str(candidate[2]), int(candidate[3])
        conn.execute(
            """
            INSERT OR IGNORE INTO app_user
            (username, display_name, role, password_hash, teacher_id, college_id, active,
             status, created_at, updated_at, must_reset_password)
            VALUES (?, ?, 'college_manager', ?, ?, ?, 1, 'active', ?, ?, 1)
            """,
            (staff_no, name, default_hash, teacher_id, college_id, ORG_SEED_TIME, ORG_SEED_TIME),
        )
        user_id = int(conn.execute("SELECT id FROM app_user WHERE username = ?", (staff_no,)).fetchone()[0])
        conn.execute(
            "INSERT OR IGNORE INTO identity_binding(user_id, identity_type, entity_id, verified_at) VALUES (?, 'teacher', ?, ?)",
            (user_id, teacher_id, ORG_SEED_TIME),
        )
        conn.execute(
            "INSERT OR IGNORE INTO person_identity(user_id, person_type, entity_id, status, verified_at) VALUES (?, 'staff', ?, 'verified', ?)",
            (user_id, staff_id, ORG_SEED_TIME),
        )
        primary_assignment = _ensure_position_assignment(conn, primary_slot, staff_id, user_id, "primary", "学院负责人确定性演示任命")
        reviewer_assignment = _ensure_position_assignment(
            conn, reviewer_slot, staff_id, user_id, "reviewer", "学院身份审核员兼任"
        )
        _ensure_role_binding(conn, user_id, "college_manager", "position", [("college", int(college_id))], primary_assignment, "学院负责人确定性演示任命")
        _ensure_role_binding(conn, user_id, "identity_reviewer", "position", [("college", int(college_id))], reviewer_assignment, "学院身份审核员兼任")
        _ensure_role_binding(conn, user_id, "teacher", "identity", [("teacher", teacher_id)], None, "教师自然身份")
        conn.execute("INSERT OR IGNORE INTO user_role(user_id, role_code) VALUES (?, 'college_manager')", (user_id,))
        conn.execute("INSERT OR IGNORE INTO user_role(user_id, role_code) VALUES (?, 'identity_reviewer')", (user_id,))
        conn.execute("INSERT OR IGNORE INTO user_role(user_id, role_code) VALUES (?, 'teacher')", (user_id,))

    # A named multi-role demo person: the existing teacher account also holds a
    # counselor appointment, so role switching can be exercised end to end.
    multi_role = conn.execute(
        """
        SELECT au.id AS user_id, au.teacher_id, au.counselor_id, au.college_id,
               st.id AS staff_id, st.staff_no, st.name, st.counselor_id AS staff_counselor_id
        FROM app_user au JOIN staff st ON st.teacher_id = au.teacher_id
        WHERE au.username = 'tea_li' AND au.active = 1 AND au.status = 'active'
        """
    ).fetchone()
    if multi_role:
        counselor_id = multi_role[2] or multi_role[7]
        if counselor_id is None:
            counselor = conn.execute(
                "SELECT id FROM counselor WHERE counselor_no = ?", (multi_role[5],)
            ).fetchone()
            if counselor:
                counselor_id = int(counselor[0])
            else:
                cursor = conn.execute(
                    "INSERT INTO counselor(counselor_no, name, college_id) VALUES (?, ?, ?)",
                    (multi_role[5], multi_role[6], multi_role[3]),
                )
                counselor_id = int(cursor.lastrowid)
        conn.execute("UPDATE staff SET counselor_id = ?, updated_at = ? WHERE id = ?", (counselor_id, ORG_SEED_TIME, multi_role[4]))
        conn.execute("UPDATE app_user SET counselor_id = ?, updated_at = ? WHERE id = ?", (counselor_id, ORG_SEED_TIME, multi_role[0]))
        demo_class = conn.execute(
            """
            SELECT cg.id FROM class_group cg JOIN major m ON m.id = cg.major_id
            WHERE m.college_id = ? ORDER BY CASE WHEN cg.id = 900003 THEN 0 ELSE 1 END, cg.id LIMIT 1
            """,
            (multi_role[3],),
        ).fetchone()
        if demo_class:
            conn.execute(
                "INSERT OR IGNORE INTO counselor_class_group(counselor_id, class_group_id) VALUES (?, ?)",
                (counselor_id, int(demo_class[0])),
            )

    # Existing counselors occupy their college counselor slot and retain their
    # exact administrative-class scopes.
    for row in conn.execute(
        """
        SELECT au.id AS user_id, au.counselor_id, co.college_id, st.id AS staff_id
        FROM app_user au JOIN counselor co ON co.id = au.counselor_id
        JOIN staff st ON st.counselor_id = co.id
        WHERE au.active = 1 AND au.status = 'active'
        """
    ).fetchall():
        user_id, counselor_id, college_id, staff_id = map(int, row)
        slot_id = 200000 + college_id * 10 + 4
        assignment_id = _ensure_position_assignment(conn, slot_id, staff_id, user_id, "primary", "现有辅导员岗位迁移")
        scopes = [("class_group", int(item[0])) for item in conn.execute(
            "SELECT class_group_id FROM counselor_class_group WHERE counselor_id = ?", (counselor_id,)
        ).fetchall()]
        _ensure_role_binding(conn, user_id, "counselor", "position", scopes, assignment_id, "现有辅导员岗位迁移")

    # Migrate every existing active account into the role-binding model.
    for row in conn.execute(
        "SELECT id, role, student_id, teacher_id, counselor_id, college_id FROM app_user WHERE active = 1 AND role <> 'pending'"
    ).fetchall():
        user_id, role, student_id, teacher_id, counselor_id, college_id = row
        if conn.execute(
            "SELECT 1 FROM user_role_binding WHERE user_id = ? AND role_code = ? AND status = 'active' LIMIT 1",
            (user_id, role),
        ).fetchone():
            continue
        scopes: list[tuple[str, int | None]] = []
        if role == "student" and student_id:
            scopes = [("self", int(student_id))]
        elif role == "teacher" and teacher_id:
            scopes = [("teacher", int(teacher_id))]
        elif role == "counselor" and counselor_id:
            scopes = [("class_group", int(r[0])) for r in conn.execute(
                "SELECT class_group_id FROM counselor_class_group WHERE counselor_id = ?", (counselor_id,)
            ).fetchall()]
        elif role == "college_manager" and college_id:
            scopes = [("college", int(college_id))]
        elif role == "academic_office":
            scopes = [("academic_office", ORG_ACADEMIC_ID)]
        elif role == "admin":
            scopes = [("platform", ORG_PLATFORM_ID)]
        _ensure_role_binding(conn, int(user_id), str(role), "migration", scopes, None, "现有账号角色迁移")

    # Person identities for existing bound accounts.
    for row in conn.execute("SELECT id, student_id, teacher_id, counselor_id FROM app_user WHERE active = 1").fetchall():
        user_id, student_id, teacher_id, counselor_id = row
        if student_id:
            conn.execute(
                "INSERT OR IGNORE INTO person_identity(user_id, person_type, entity_id, status, verified_at) VALUES (?, 'student', ?, 'verified', ?)",
                (user_id, student_id, ORG_SEED_TIME),
            )
        elif teacher_id:
            staff_row = conn.execute("SELECT id FROM staff WHERE teacher_id = ?", (teacher_id,)).fetchone()
            if staff_row:
                conn.execute(
                    "INSERT OR IGNORE INTO person_identity(user_id, person_type, entity_id, status, verified_at) VALUES (?, 'staff', ?, 'verified', ?)",
                    (user_id, staff_row[0], ORG_SEED_TIME),
                )
        elif counselor_id:
            staff_row = conn.execute("SELECT id FROM staff WHERE counselor_id = ?", (counselor_id,)).fetchone()
            if staff_row:
                conn.execute(
                    "INSERT OR IGNORE INTO person_identity(user_id, person_type, entity_id, status, verified_at) VALUES (?, 'staff', ?, 'verified', ?)",
                    (user_id, staff_row[0], ORG_SEED_TIME),
                )

    # Organization queues: escalation first, then college and class queues.
    conn.executemany(
        """
        INSERT OR IGNORE INTO organization_review_queue
        (id, organization_unit_id, queue_type, scope_type, scope_id, name, escalation_queue_id,
         sla_hours, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 'active', ?, ?)
        """,
        [
            (300001, ORG_ACADEMIC_ID, "identity_escalation", "academic_office", ORG_ACADEMIC_ID, "教务身份异常升级队列", 24, ORG_SEED_TIME, ORG_SEED_TIME),
            (300002, ORG_PLATFORM_ID, "high_risk_account", "platform", ORG_PLATFORM_ID, "平台高风险账号队列", 12, ORG_SEED_TIME, ORG_SEED_TIME),
        ],
    )
    for college_id, college_name in colleges:
        conn.execute(
            """
            INSERT OR IGNORE INTO organization_review_queue
            (id, organization_unit_id, queue_type, scope_type, scope_id, name, escalation_queue_id,
             sla_hours, status, created_at, updated_at)
            VALUES (?, ?, 'staff_identity', 'college', ?, ?, 300001, 48, 'active', ?, ?)
            """,
            (310000 + int(college_id), _college_unit_id(college_id), college_id,
             f"{college_name}教职工身份审核队列", ORG_SEED_TIME, ORG_SEED_TIME),
        )
    for class_id, class_name, college_id in conn.execute(
        """
        SELECT cg.id, cg.name, m.college_id FROM class_group cg
        JOIN major m ON m.id = cg.major_id
        """
    ).fetchall():
        conn.execute(
            """
            INSERT OR IGNORE INTO organization_review_queue
            (organization_unit_id, queue_type, scope_type, scope_id, name, escalation_queue_id,
             sla_hours, status, created_at, updated_at)
            VALUES (?, 'student_identity', 'class_group', ?, ?, 300001, 48, 'active', ?, ?)
            """,
            (_college_unit_id(college_id), class_id, f"{class_name}学生身份审核队列", ORG_SEED_TIME, ORG_SEED_TIME),
        )

    # Attach existing pending applications to their organization queue and task.
    for app in conn.execute(
        "SELECT id, identity_type, matched_college_id, matched_class_id, submitted_at FROM identity_application WHERE status = 'pending'"
    ).fetchall():
        app_id, identity_type, college_id, class_id, submitted_at = app
        if identity_type == "student":
            queue = conn.execute(
                "SELECT id FROM organization_review_queue WHERE queue_type = 'student_identity' AND scope_type = 'class_group' AND scope_id = ?",
                (class_id,),
            ).fetchone()
        else:
            queue = conn.execute(
                "SELECT id FROM organization_review_queue WHERE queue_type = 'staff_identity' AND scope_type = 'college' AND scope_id = ?",
                (college_id,),
            ).fetchone()
        if not queue:
            queue = (300001,)
        conn.execute(
            """
            INSERT OR IGNORE INTO review_task
            (queue_id, task_type, resource_type, resource_id, status, due_at, created_at, updated_at)
            VALUES (?, 'identity_review', 'identity_application', ?, 'pending', datetime(?, '+48 hours'), ?, ?)
            """,
            (queue[0], app_id, submitted_at, submitted_at, ORG_SEED_TIME),
        )
        task_id = conn.execute(
            "SELECT id FROM review_task WHERE task_type = 'identity_review' AND resource_type = 'identity_application' AND resource_id = ?",
            (app_id,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE identity_application SET review_queue_id = ?, review_task_id = ? WHERE id = ?",
            (queue[0], task_id, app_id),
        )
