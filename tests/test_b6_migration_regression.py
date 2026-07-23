from __future__ import annotations

import sqlite3

import pytest

from app.core import teaching_migrations
from app.core.business_domains import (
    DEMO_USERS,
    AuthorizationError,
    _hash_password,
    login,
    token_for,
    user_from_token,
)


def test_b6_migration_invariants_are_complete():
    teaching_migrations.ensure_mvp_schema()
    report = teaching_migrations.identity_position_migration_report()

    assert report["applied"] is True
    assert report["active_accounts"] >= len(DEMO_USERS)
    assert report["accounts_without_active_binding"] == 0
    assert report["active_assignments_without_binding"] == 0
    assert report["active_bindings_missing_required_scope"] == 0
    assert report["generic_formal_position_occupants"] == 0


def test_all_legacy_demo_accounts_authenticate_through_role_bindings():
    for username in DEMO_USERS:
        ctx = login(username, "123456")
        assert ctx.role_binding_id is not None, username
        assert ctx.available_roles, username
        restored = user_from_token(token_for(username, ctx.role_binding_id))
        assert restored.role_binding_id == ctx.role_binding_id
        assert restored.role == ctx.role


def test_legacy_app_user_role_and_scope_columns_are_not_authorization_sources():
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        original = conn.execute(
            "SELECT role, student_id, teacher_id, counselor_id, college_id FROM app_user WHERE username = 'stu_zhang'"
        ).fetchone()
        conn.execute(
            """
            UPDATE app_user SET role = 'admin', student_id = 900002, teacher_id = 900001,
                counselor_id = 900001, college_id = 2 WHERE username = 'stu_zhang'
            """
        )
        conn.commit()
    try:
        # Re-running startup migration must not convert a modified legacy column
        # into a new privilege after the one-way migration marker is present.
        teaching_migrations.ensure_mvp_schema()
        ctx = user_from_token(token_for("stu_zhang"))
        assert ctx.role == "student"
        assert ctx.row_scope == {"student_id": 900001}
        assert "organization_management" not in ctx.features
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            admin_grant = conn.execute(
                """
                SELECT 1 FROM user_role_binding urb JOIN app_user au ON au.id = urb.user_id
                WHERE au.username = 'stu_zhang' AND urb.role_code = 'admin' AND urb.status = 'active'
                """
            ).fetchone()
        assert admin_grant is None
    finally:
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            conn.execute(
                """
                UPDATE app_user SET role = ?, student_id = ?, teacher_id = ?, counselor_id = ?, college_id = ?
                WHERE username = 'stu_zhang'
                """,
                original,
            )
            conn.commit()


def test_active_legacy_account_without_binding_is_denied_and_not_remigrated():
    username = "B6LEGACYONLY"
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO app_user
            (username, display_name, role, password_hash, active, status, created_at, updated_at)
            VALUES (?, '遗留字段测试账号', 'admin', ?, 1, 'active', datetime('now'), datetime('now'))
            """,
            (username, _hash_password("Legacy123")),
        )
        conn.commit()
    try:
        teaching_migrations.ensure_mvp_schema()
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            count = conn.execute(
                """
                SELECT count(*) FROM user_role_binding urb JOIN app_user au ON au.id = urb.user_id
                WHERE au.username = ?
                """,
                (username,),
            ).fetchone()[0]
        assert count == 0
        with pytest.raises(ValueError, match="没有有效工作身份"):
            login(username, "Legacy123")
        with pytest.raises(AuthorizationError, match="没有有效工作身份"):
            token_for(username)
    finally:
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            conn.execute("DELETE FROM app_user WHERE username = ?", (username,))
            conn.commit()
