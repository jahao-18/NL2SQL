"""Identity-isolated server-side sessions for the V3 assistant."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core import teaching_migrations
from app.core.assistant_context import (
    AssistantPageContext,
    resolve_assistant_context,
    validate_assistant_identity,
)
from app.core.business_domains import AuthContext


AnswerType = Literal[
    "metric",
    "business_state",
    "nl2sql",
    "navigation",
    "knowledge",
    "hybrid",
    "unsupported",
]
TurnStatus = Literal["success", "clarify", "rejected", "failed", "degraded"]


class AssistantSessionNotFoundError(LookupError):
    """Returned for missing sessions and sessions owned by another identity."""


class AssistantSessionConflictError(ValueError):
    """Raised when an idempotency key conflicts with deleted or changed state."""


class AssistantSessionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    context: AssistantPageContext
    client_request_id: str | None = Field(None, min_length=8, max_length=100)

    @field_validator("title", "client_request_id", mode="before")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class AssistantSessionUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=120)
    is_favorite: bool | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_change(self) -> "AssistantSessionUpdate":
        if self.title is None and self.is_favorite is None:
            raise ValueError("至少提供一个允许修改的字段")
        return self


class AssistantTurnCreate(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    answer_type: AnswerType
    status: TurnStatus
    context: AssistantPageContext
    safe_answer_summary: str = Field("", max_length=1000)
    error_code: str | None = Field(None, max_length=100)
    client_request_id: str | None = Field(None, min_length=8, max_length=100)

    @field_validator(
        "question", "safe_answer_summary", "error_code", "client_request_id", mode="before"
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


def create_session(
    auth: AuthContext, payload: AssistantSessionCreate | dict[str, Any]
) -> dict[str, Any]:
    request = (
        payload
        if isinstance(payload, AssistantSessionCreate)
        else AssistantSessionCreate.model_validate(payload)
    )
    resolution = resolve_assistant_context(auth, request.context)
    context_json = _context_json(resolution.effective_context)
    title = request.title.strip()
    request_id = request.client_request_id.strip() if request.client_request_id else None
    with _connect() as conn:
        if request_id:
            existing = conn.execute(
                """
                SELECT * FROM assistant_session
                WHERE user_id = ? AND role_binding_id = ? AND client_request_id = ?
                """,
                (auth.user_id, auth.role_binding_id, request_id),
            ).fetchone()
            if existing:
                if existing["deleted_at"] is not None:
                    raise AssistantSessionConflictError("该请求对应的会话已经删除")
                return _session_item(existing)
        cursor = conn.execute(
            """
            INSERT INTO assistant_session
                (user_id, role_binding_id, title, page, context_summary,
                 client_request_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                auth.user_id,
                auth.role_binding_id,
                title,
                resolution.effective_context["page"],
                context_json,
                request_id,
            ),
        )
        row = conn.execute(
            "SELECT * FROM assistant_session WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        conn.commit()
    return _session_item(row)


def list_sessions(
    auth: AuthContext, *, page: int = 1, page_size: int = 20
) -> dict[str, Any]:
    validate_assistant_identity(auth)
    page, page_size = _pagination(page, page_size)
    offset = (page - 1) * page_size
    with _connect() as conn:
        total = int(
            conn.execute(
                """
                SELECT count(*) FROM assistant_session
                WHERE user_id = ? AND role_binding_id = ? AND deleted_at IS NULL
                """,
                (auth.user_id, auth.role_binding_id),
            ).fetchone()[0]
        )
        rows = conn.execute(
            """
            SELECT * FROM assistant_session
            WHERE user_id = ? AND role_binding_id = ? AND deleted_at IS NULL
            ORDER BY is_favorite DESC, updated_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (auth.user_id, auth.role_binding_id, page_size, offset),
        ).fetchall()
    return {
        "items": [_session_item(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def get_session(
    auth: AuthContext,
    session_id: int,
    *,
    turn_page: int = 1,
    turn_page_size: int = 20,
) -> dict[str, Any]:
    validate_assistant_identity(auth)
    turn_page, turn_page_size = _pagination(turn_page, turn_page_size)
    with _connect() as conn:
        session = _owned_session(conn, auth, session_id)
        total = int(
            conn.execute(
                "SELECT count(*) FROM assistant_turn WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
        )
        rows = conn.execute(
            """
            SELECT * FROM assistant_turn WHERE session_id = ?
            ORDER BY sequence_no ASC LIMIT ? OFFSET ?
            """,
            (session_id, turn_page_size, (turn_page - 1) * turn_page_size),
        ).fetchall()
    return {
        "item": _session_item(session),
        "turns": {
            "items": [_turn_item(row) for row in rows],
            "page": turn_page,
            "page_size": turn_page_size,
            "total": total,
        },
    }


def recent_turns(
    auth: AuthContext,
    session_id: int,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return a bounded, chronological history owned by the current work identity."""
    validate_assistant_identity(auth)
    if limit < 1 or limit > 20:
        raise ValueError("历史轮数必须在 1 到 20 之间")
    with _connect() as conn:
        _owned_session(conn, auth, session_id)
        rows = conn.execute(
            """
            SELECT * FROM assistant_turn
            WHERE session_id = ? AND status IN ('success', 'clarify', 'degraded')
            ORDER BY sequence_no DESC LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [_turn_item(row) for row in reversed(rows)]


def get_turn(auth: AuthContext, turn_id: int) -> dict[str, Any]:
    """Return one assistant turn owned by the current work identity."""
    validate_assistant_identity(auth)
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT t.*
            FROM assistant_turn t
            JOIN assistant_session s ON s.id = t.session_id
            WHERE t.id = ?
              AND s.user_id = ?
              AND s.role_binding_id = ?
              AND s.deleted_at IS NULL
            """,
            (turn_id, auth.user_id, auth.role_binding_id),
        ).fetchone()
    if row is None:
        raise AssistantSessionNotFoundError("助手回答不存在")
    return _turn_item(row)


def update_session(
    auth: AuthContext,
    session_id: int,
    payload: AssistantSessionUpdate | dict[str, Any],
) -> dict[str, Any]:
    validate_assistant_identity(auth)
    request = (
        payload
        if isinstance(payload, AssistantSessionUpdate)
        else AssistantSessionUpdate.model_validate(payload)
    )
    with _connect() as conn:
        _owned_session(conn, auth, session_id)
        fields: list[str] = []
        values: list[Any] = []
        if request.title is not None:
            fields.append("title = ?")
            values.append(request.title.strip())
        if request.is_favorite is not None:
            fields.append("is_favorite = ?")
            values.append(int(request.is_favorite))
        fields.append("updated_at = datetime('now')")
        conn.execute(
            f"UPDATE assistant_session SET {', '.join(fields)} WHERE id = ?",
            (*values, session_id),
        )
        row = conn.execute(
            "SELECT * FROM assistant_session WHERE id = ?", (session_id,)
        ).fetchone()
        conn.commit()
    return _session_item(row)


def delete_session(auth: AuthContext, session_id: int) -> dict[str, Any]:
    validate_assistant_identity(auth)
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, deleted_at FROM assistant_session
            WHERE id = ? AND user_id = ? AND role_binding_id = ?
            """,
            (session_id, auth.user_id, auth.role_binding_id),
        ).fetchone()
        if row is None:
            raise AssistantSessionNotFoundError("助手会话不存在")
        already_deleted = row["deleted_at"] is not None
        if not already_deleted:
            conn.execute(
                """
                UPDATE assistant_session
                SET deleted_at = datetime('now'), updated_at = datetime('now')
                WHERE id = ?
                """,
                (session_id,),
            )
            conn.execute(
                """
                UPDATE assistant_action_draft
                SET status = 'canceled', updated_at = datetime('now')
                WHERE session_id = ? AND status = 'pending'
                """,
                (session_id,),
            )
            conn.commit()
    return {"deleted": True, "already_deleted": already_deleted, "id": session_id}


def append_turn(
    auth: AuthContext,
    session_id: int,
    payload: AssistantTurnCreate | dict[str, Any],
) -> dict[str, Any]:
    request = (
        payload
        if isinstance(payload, AssistantTurnCreate)
        else AssistantTurnCreate.model_validate(payload)
    )
    resolution = resolve_assistant_context(auth, request.context)
    context_json = _context_json(resolution.effective_context)
    request_id = request.client_request_id.strip() if request.client_request_id else None
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        session = _owned_session(conn, auth, session_id)
        if resolution.effective_context["page"] != session["page"]:
            conn.rollback()
            raise AssistantSessionConflictError("本轮页面与会话页面不一致")
        if request_id:
            existing = conn.execute(
                """
                SELECT * FROM assistant_turn
                WHERE session_id = ? AND client_request_id = ?
                """,
                (session_id, request_id),
            ).fetchone()
            if existing:
                conn.rollback()
                return _turn_item(existing)
        sequence_no = int(
            conn.execute(
                "SELECT COALESCE(max(sequence_no), 0) + 1 FROM assistant_turn WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
        )
        cursor = conn.execute(
            """
            INSERT INTO assistant_turn
                (session_id, sequence_no, question, answer_type, status,
                 safe_answer_summary, context_summary, error_code, client_request_id,
                 started_at, completed_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'),
                    datetime('now'), datetime('now'))
            """,
            (
                session_id,
                sequence_no,
                request.question.strip(),
                request.answer_type,
                request.status,
                request.safe_answer_summary.strip(),
                context_json,
                request.error_code,
                request_id,
            ),
        )
        conn.execute(
            """
            UPDATE assistant_session
            SET last_question = ?, updated_at = datetime('now') WHERE id = ?
            """,
            (request.question.strip(), session_id),
        )
        row = conn.execute(
            "SELECT * FROM assistant_turn WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        conn.commit()
    return _turn_item(row)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(teaching_migrations.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _owned_session(
    conn: sqlite3.Connection, auth: AuthContext, session_id: int
) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT * FROM assistant_session
        WHERE id = ? AND user_id = ? AND role_binding_id = ? AND deleted_at IS NULL
        """,
        (session_id, auth.user_id, auth.role_binding_id),
    ).fetchone()
    if row is None:
        raise AssistantSessionNotFoundError("助手会话不存在")
    return row


def _pagination(page: int, page_size: int) -> tuple[int, int]:
    if page < 1:
        raise ValueError("page 必须大于等于 1")
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size 必须在 1 到 100 之间")
    return page, page_size


def _context_json(context: dict[str, Any]) -> str:
    encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 8192:
        raise ValueError("生效上下文不能超过 8 KB")
    return encoded


def _session_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "title": str(row["title"]),
        "page": str(row["page"]),
        "context": json.loads(row["context_summary"]),
        "last_question": row["last_question"],
        "is_favorite": bool(row["is_favorite"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _turn_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "sequence_no": int(row["sequence_no"]),
        "question": str(row["question"]),
        "answer_type": str(row["answer_type"]),
        "status": str(row["status"]),
        "answer_summary": str(row["safe_answer_summary"]),
        "context": json.loads(row["context_summary"]),
        "error_code": row["error_code"],
        "started_at": str(row["started_at"]),
        "completed_at": row["completed_at"],
    }
