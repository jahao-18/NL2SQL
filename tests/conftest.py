from __future__ import annotations

import shutil
import sqlite3

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolated_teaching_database(tmp_path_factory: pytest.TempPathFactory):
    """Keep workflow tests away from the shared demo database and upload files."""
    from app.core import assignment_workflow, authorization, course_space, teaching_migrations

    runtime_dir = tmp_path_factory.mktemp("teaching-runtime")
    db_path = runtime_dir / "teaching.db"
    submission_dir = runtime_dir / "submissions"
    course_resource_dir = runtime_dir / "course_resources"
    submission_dir.mkdir(parents=True, exist_ok=True)
    course_resource_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(teaching_migrations.DB_PATH, db_path)

    patcher = pytest.MonkeyPatch()
    patcher.setattr(teaching_migrations, "DB_PATH", db_path)
    patcher.setattr(authorization, "DB_PATH", db_path)
    patcher.setattr(assignment_workflow, "SUBMISSION_DIR", submission_dir)
    patcher.setattr(course_space, "RESOURCE_DIR", course_resource_dir)
    teaching_migrations.ensure_mvp_schema()

    # The checked-in demo database can contain records from manual acceptance runs.
    # Remove only generated test ranges from the private copy used by this session.
    with sqlite3.connect(db_path) as conn:
        generated_submissions = (
            "SELECT id FROM assignment_submission "
            "WHERE id > 900021 OR assignment_id > 900015"
        )
        conn.execute(f"DELETE FROM grading_record WHERE submission_id IN ({generated_submissions})")
        conn.execute(f"DELETE FROM submission_version WHERE submission_id IN ({generated_submissions})")
        conn.execute("DELETE FROM assignment_submission WHERE id > 900021 OR assignment_id > 900015")
        conn.execute("DELETE FROM assignment WHERE id > 900015")
        conn.execute("DELETE FROM analytics_query_log")
        conn.execute("DELETE FROM course_assignment_analytics")
        conn.execute("DELETE FROM student_task_analytics")
        conn.commit()

    yield
    patcher.undo()
