from __future__ import annotations

import shutil
import sqlite3

import pytest

from app.core import teaching_migrations
from app.core.v3_migrations import (
    LEDGER_TABLE,
    Migration,
    MigrationError,
    V3_MIGRATIONS,
    apply_v3_migrations,
    migration_status,
)


def _empty_database(path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE legacy_record (id INTEGER PRIMARY KEY, value TEXT)")
        # V3 migrations run after the legacy MVP schema has been established.
        conn.execute("CREATE TABLE app_user (id INTEGER PRIMARY KEY)")
        conn.execute(
            """
            CREATE TABLE user_role_binding (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES app_user(id)
            )
            """
        )


def test_first_execution_creates_versioned_ledger(tmp_path):
    db_path = tmp_path / "fresh.db"
    _empty_database(db_path)

    assert apply_v3_migrations(db_path) == [item.key for item in V3_MIGRATIONS]

    status = migration_status(db_path)
    assert status["schema_version"] == 3005
    assert [item["key"] for item in status["applied"]] == [
        item.key for item in V3_MIGRATIONS
    ]
    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1]: row for row in conn.execute(f"PRAGMA table_info({LEDGER_TABLE})")
        }
        indexes = {
            row[1] for row in conn.execute(f"PRAGMA index_list({LEDGER_TABLE})")
        }
    assert {"version", "migration_key", "checksum", "created_at", "updated_at"} <= set(columns)
    assert "idx_v3_schema_migration_applied_at" in indexes


def test_repeated_execution_is_idempotent(tmp_path):
    db_path = tmp_path / "repeat.db"
    _empty_database(db_path)

    apply_v3_migrations(db_path)
    assert apply_v3_migrations(db_path) == []

    with sqlite3.connect(db_path) as conn:
        count = conn.execute(f"SELECT count(*) FROM {LEDGER_TABLE}").fetchone()[0]
    assert count == len(V3_MIGRATIONS)


def test_existing_teaching_database_upgrades_without_changing_legacy_history(tmp_path):
    db_path = tmp_path / "teaching-copy.db"
    shutil.copy2(teaching_migrations.DB_PATH, db_path)
    with sqlite3.connect(db_path) as conn:
        legacy_rows_before = conn.execute("SELECT count(*) FROM schema_migration").fetchone()[0]
        # The session fixture has already started the current application once.
        # Remove only the V3 ledger from this private copy to reconstruct a V2-era
        # teaching database and exercise the real upgrade path.
        conn.execute("DROP TABLE IF EXISTS query_execution_trace")
        conn.execute("DROP TABLE IF EXISTS assistant_action_draft")
        conn.execute("DROP TABLE IF EXISTS assistant_saved_query")
        conn.execute("DROP TABLE IF EXISTS assistant_turn")
        conn.execute("DROP TABLE IF EXISTS assistant_session")
        conn.execute(f"DROP TABLE IF EXISTS {LEDGER_TABLE}")
        conn.execute("PRAGMA user_version = 0")

    apply_v3_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        legacy_rows_after = conn.execute("SELECT count(*) FROM schema_migration").fetchone()[0]
        v3_rows = conn.execute(f"SELECT count(*) FROM {LEDGER_TABLE}").fetchone()[0]
    assert legacy_rows_after == legacy_rows_before
    assert v3_rows == len(V3_MIGRATIONS)


def test_failed_migration_rolls_back_ledger_and_partial_schema(tmp_path):
    db_path = tmp_path / "failure.db"
    _empty_database(db_path)
    migrations = (
        Migration(1, "test_0001", "create first table", ("CREATE TABLE first_v3_table (id INTEGER PRIMARY KEY)",)),
        Migration(2, "test_0002", "fail after partial DDL", (
            "CREATE TABLE partial_v3_table (id INTEGER PRIMARY KEY)",
            "INSERT INTO table_that_does_not_exist(id) VALUES (1)",
        )),
    )

    with pytest.raises(MigrationError, match="V3 数据库迁移失败"):
        apply_v3_migrations(db_path, migrations)

    with sqlite3.connect(db_path) as conn:
        names = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert LEDGER_TABLE not in names
    assert "first_v3_table" not in names
    assert "partial_v3_table" not in names
    assert version == 0


def test_changed_applied_migration_is_rejected(tmp_path):
    db_path = tmp_path / "drift.db"
    _empty_database(db_path)
    apply_v3_migrations(db_path)
    changed = Migration(1, V3_MIGRATIONS[0].key, "changed history")

    with pytest.raises(MigrationError, match="校验值与账本不一致"):
        apply_v3_migrations(db_path, (changed,))

    assert migration_status(db_path)["applied"][0]["checksum"] == V3_MIGRATIONS[0].checksum
