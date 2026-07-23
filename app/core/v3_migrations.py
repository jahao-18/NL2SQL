"""Versioned, transactional database migrations introduced for V3.

The legacy ``ensure_mvp_schema`` function remains responsible for the existing
schema.  All schema changes added from V3 onward must be declared here so they
are ordered, checksummed, repeatable, and applied in one transaction.
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


V3_SCHEMA_BASE_VERSION = 3000
LEDGER_TABLE = "v3_schema_migration"


class MigrationError(RuntimeError):
    """Raised when the V3 migration history is invalid or cannot be applied."""


@dataclass(frozen=True)
class Migration:
    version: int
    key: str
    description: str
    statements: tuple[str, ...] = ()

    @property
    def checksum(self) -> str:
        payload = "\n-- statement --\n".join(
            (str(self.version), self.key, self.description, *self.statements)
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


V3_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        key="v3_0001_migration_foundation",
        description="建立 V3 版本化、可校验且事务化的迁移账本",
        statements=(
            "CREATE INDEX IF NOT EXISTS idx_v3_schema_migration_applied_at "
            "ON v3_schema_migration(applied_at)",
        ),
    ),
    Migration(
        version=2,
        key="v3_0002_assistant_sessions",
        description="建立按用户和当前工作身份隔离的助手会话、轮次与收藏查询",
        statements=(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_role_binding_id_user ON user_role_binding(id, user_id)",
            """
            CREATE TABLE assistant_session (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                role_binding_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                page TEXT NOT NULL CHECK(page IN (
                    'dashboard','assistant','course_space','assignment_workflow',
                    'attendance','course_analytics','support_workbench',
                    'teaching_operations','notifications','governance','data_access','profile'
                )),
                context_summary TEXT NOT NULL,
                last_question TEXT,
                is_favorite INTEGER NOT NULL DEFAULT 0 CHECK(is_favorite IN (0, 1)),
                client_request_id TEXT,
                deleted_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES app_user(id),
                FOREIGN KEY (role_binding_id, user_id) REFERENCES user_role_binding(id, user_id)
            )
            """,
            "CREATE INDEX idx_assistant_session_owner ON assistant_session(user_id, role_binding_id, deleted_at, updated_at)",
            "CREATE UNIQUE INDEX uq_assistant_session_request ON assistant_session(user_id, role_binding_id, client_request_id) WHERE client_request_id IS NOT NULL",
            """
            CREATE TABLE assistant_turn (
                id INTEGER PRIMARY KEY,
                session_id INTEGER NOT NULL,
                sequence_no INTEGER NOT NULL CHECK(sequence_no > 0),
                question TEXT NOT NULL,
                answer_type TEXT NOT NULL CHECK(answer_type IN (
                    'metric','business_state','nl2sql','navigation','knowledge',
                    'hybrid','unsupported'
                )),
                status TEXT NOT NULL CHECK(status IN (
                    'success','clarify','rejected','failed','degraded'
                )),
                safe_answer_summary TEXT NOT NULL DEFAULT '',
                context_summary TEXT NOT NULL,
                error_code TEXT,
                client_request_id TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(session_id, sequence_no),
                FOREIGN KEY (session_id) REFERENCES assistant_session(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX idx_assistant_turn_session ON assistant_turn(session_id, sequence_no)",
            "CREATE UNIQUE INDEX uq_assistant_turn_request ON assistant_turn(session_id, client_request_id) WHERE client_request_id IS NOT NULL",
            """
            CREATE TABLE assistant_saved_query (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                role_binding_id INTEGER NOT NULL,
                session_id INTEGER,
                turn_id INTEGER,
                title TEXT NOT NULL,
                question TEXT NOT NULL,
                context_summary TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, role_binding_id, title),
                FOREIGN KEY (user_id) REFERENCES app_user(id),
                FOREIGN KEY (role_binding_id, user_id) REFERENCES user_role_binding(id, user_id),
                FOREIGN KEY (session_id) REFERENCES assistant_session(id) ON DELETE SET NULL,
                FOREIGN KEY (turn_id) REFERENCES assistant_turn(id) ON DELETE SET NULL
            )
            """,
            "CREATE INDEX idx_assistant_saved_query_owner ON assistant_saved_query(user_id, role_binding_id, updated_at)",
        ),
    ),
    Migration(
        version=3,
        key="v3_0003_query_execution_trace",
        description="建立不保存问题正文、SQL 和结果行的统一助手执行轨迹",
        statements=(
            """
            CREATE TABLE query_execution_trace (
                id INTEGER PRIMARY KEY,
                turn_id INTEGER NOT NULL UNIQUE,
                route TEXT NOT NULL,
                retrieval_status TEXT NOT NULL DEFAULT 'not_applicable' CHECK(retrieval_status IN (
                    'used','not_used','degraded','not_applicable'
                )),
                retrievers_json TEXT NOT NULL DEFAULT '[]',
                stages_json TEXT NOT NULL DEFAULT '{}',
                degraded INTEGER NOT NULL DEFAULT 0 CHECK(degraded IN (0, 1)),
                degradation_reason TEXT,
                total_elapsed_ms INTEGER NOT NULL CHECK(total_elapsed_ms >= 0),
                confidence_score REAL,
                confidence_status TEXT,
                result_row_count INTEGER NOT NULL DEFAULT 0 CHECK(result_row_count >= 0),
                truncated INTEGER NOT NULL DEFAULT 0 CHECK(truncated IN (0, 1)),
                failed_stage TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (turn_id) REFERENCES assistant_turn(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX idx_query_execution_trace_route ON query_execution_trace(route, created_at)",
            "CREATE INDEX idx_query_execution_trace_quality ON query_execution_trace(degraded, confidence_score, created_at)",
        ),
    ),
    Migration(
        version=4,
        key="v3_0004_assistant_action_drafts",
        description="建立按当前工作身份隔离、短期有效且仅可确认一次的助手动作草稿",
        statements=(
            """
            CREATE TABLE assistant_action_draft (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                role_binding_id INTEGER NOT NULL,
                session_id INTEGER,
                turn_id INTEGER,
                action_type TEXT NOT NULL CHECK(action_type IN (
                    'open_assignment_roster','open_course','open_support_case',
                    'open_teaching_issue','apply_safe_filter',
                    'draft_course_notification','submit_governance_feedback',
                    'export_current_result'
                )),
                parameters_json TEXT NOT NULL,
                preview_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN (
                    'pending','confirmed','expired','failed','canceled'
                )),
                client_request_id TEXT,
                expires_at TEXT NOT NULL,
                confirmed_at TEXT,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES app_user(id),
                FOREIGN KEY (role_binding_id, user_id) REFERENCES user_role_binding(id, user_id),
                FOREIGN KEY (session_id) REFERENCES assistant_session(id) ON DELETE SET NULL,
                FOREIGN KEY (turn_id) REFERENCES assistant_turn(id) ON DELETE SET NULL
            )
            """,
            "CREATE INDEX idx_assistant_action_draft_owner ON assistant_action_draft(user_id, role_binding_id, status, expires_at)",
            "CREATE UNIQUE INDEX uq_assistant_action_draft_request ON assistant_action_draft(user_id, role_binding_id, client_request_id) WHERE client_request_id IS NOT NULL",
        ),
    ),
    Migration(
        version=5,
        key="v3_0005_query_trace_retrieval_backend",
        description="为助手质量运营记录每次检索实际使用的后端类型",
        statements=(
            """
            ALTER TABLE query_execution_trace
            ADD COLUMN retrieval_backend TEXT NOT NULL DEFAULT 'none'
            CHECK(retrieval_backend IN ('none','local','server'))
            """,
            "CREATE INDEX idx_query_execution_trace_backend ON query_execution_trace(retrieval_backend, created_at)",
        ),
    ),
)


def apply_v3_migrations(
    db_path: Path,
    migrations: Sequence[Migration] = V3_MIGRATIONS,
) -> list[str]:
    """Apply pending V3 migrations atomically and return their keys.

    The ledger bootstrap and every pending migration share one transaction. If
    any statement fails, SQLite rolls back both the partial schema and ledger
    writes, so the next startup can retry from a clean state.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    ordered = _validate_migrations(migrations)
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        _create_ledger(conn)
        applied = {
            int(row[0]): (str(row[1]), str(row[2]))
            for row in conn.execute(
                f"SELECT version, migration_key, checksum FROM {LEDGER_TABLE}"
            ).fetchall()
        }
        applied_keys = {
            str(row[0]): int(row[1])
            for row in conn.execute(
                f"SELECT migration_key, version FROM {LEDGER_TABLE}"
            ).fetchall()
        }
        completed: list[str] = []
        for migration in ordered:
            current = applied.get(migration.version)
            if current is not None:
                if current != (migration.key, migration.checksum):
                    raise MigrationError(
                        f"迁移版本 {migration.version} 的名称或校验值与账本不一致"
                    )
                continue
            if migration.key in applied_keys:
                raise MigrationError(
                    f"迁移名称 {migration.key} 已被版本 {applied_keys[migration.key]} 使用"
                )
            started = time.perf_counter()
            for statement in migration.statements:
                conn.execute(statement)
            elapsed_ms = max(0, round((time.perf_counter() - started) * 1000))
            conn.execute(
                f"""
                INSERT INTO {LEDGER_TABLE}
                    (version, migration_key, description, checksum, execution_ms,
                     applied_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'))
                """,
                (
                    migration.version,
                    migration.key,
                    migration.description,
                    migration.checksum,
                    elapsed_ms,
                ),
            )
            completed.append(migration.key)
        schema_version = V3_SCHEMA_BASE_VERSION + max(
            (migration.version for migration in ordered), default=0
        )
        conn.execute(f"PRAGMA user_version = {schema_version}")
        conn.execute("COMMIT")
        return completed
    except Exception as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        if isinstance(exc, MigrationError):
            raise
        raise MigrationError(f"V3 数据库迁移失败：{exc}") from exc
    finally:
        conn.close()


def migration_status(db_path: Path) -> dict[str, object]:
    """Return read-only V3 migration status for diagnostics and tests."""
    db_path = Path(db_path)
    if not db_path.exists():
        return {"database_exists": False, "schema_version": 0, "applied": []}
    with sqlite3.connect(db_path) as conn:
        schema_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        ledger_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (LEDGER_TABLE,),
        ).fetchone()
        rows = [] if not ledger_exists else conn.execute(
            f"""
            SELECT version, migration_key, description, checksum, applied_at
            FROM {LEDGER_TABLE} ORDER BY version
            """
        ).fetchall()
    return {
        "database_exists": True,
        "schema_version": schema_version,
        "applied": [
            {
                "version": int(row[0]),
                "key": str(row[1]),
                "description": str(row[2]),
                "checksum": str(row[3]),
                "applied_at": str(row[4]),
            }
            for row in rows
        ],
    }


def _validate_migrations(migrations: Sequence[Migration]) -> tuple[Migration, ...]:
    ordered = tuple(sorted(migrations, key=lambda item: item.version))
    versions = [item.version for item in ordered]
    keys = [item.key for item in ordered]
    if any(version <= 0 for version in versions):
        raise MigrationError("迁移版本必须是正整数")
    if len(versions) != len(set(versions)):
        raise MigrationError("迁移版本必须唯一")
    if len(keys) != len(set(keys)):
        raise MigrationError("迁移名称必须唯一")
    if any(not key.strip() for key in keys):
        raise MigrationError("迁移名称不能为空")
    return ordered


def _create_ledger(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
            version INTEGER PRIMARY KEY,
            migration_key TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            checksum TEXT NOT NULL,
            execution_ms INTEGER NOT NULL CHECK(execution_ms >= 0),
            applied_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
