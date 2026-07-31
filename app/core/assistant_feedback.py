"""Identity-bound feedback for unified assistant NL2SQL turns."""
from __future__ import annotations

from typing import Any, Literal

import sqlparse
from pydantic import BaseModel, Field, model_validator
from sqlparse.tokens import DML

from app.core.assistant_sessions import get_turn
from app.core.business_domains import AuthContext
from app.core.data_sources import get_source
from app.core.feedback import delete_turn_feedback, upsert_turn_feedback
from app.core.governance import (
    create_feedback_review,
    delete_review_items_for_feedback,
)


class AssistantTurnFeedbackRequest(BaseModel):
    kind: Literal["correct", "incorrect"]
    category: str = Field("", max_length=100)
    reason: str = Field("", max_length=1000)
    sql: str = Field(..., min_length=1, max_length=5000)

    @model_validator(mode="after")
    def validate_feedback(self) -> "AssistantTurnFeedbackRequest":
        self.category = self.category.strip()
        self.reason = self.reason.strip()
        self.sql = self.sql.strip()
        if self.kind == "incorrect" and not self.reason:
            raise ValueError("请说明结果需要改进的原因")
        if self.kind == "correct":
            self.category = "confirmed_example"
            self.reason = self.reason or "用户确认结果正确，建议沉淀为标准问法样例"
        _validate_candidate_sql(self.sql)
        return self


def submit_turn_feedback(
    auth: AuthContext,
    turn_id: int,
    payload: AssistantTurnFeedbackRequest | dict[str, Any],
) -> dict[str, Any]:
    request = (
        payload
        if isinstance(payload, AssistantTurnFeedbackRequest)
        else AssistantTurnFeedbackRequest.model_validate(payload)
    )
    turn = get_turn(auth, turn_id)
    if turn["answer_type"] != "nl2sql" or turn["status"] not in {"success", "degraded"}:
        raise ValueError("只有已完成的自然语言问数回答可以提交此类反馈")

    source = str((turn.get("context") or {}).get("source") or "teaching")
    data_source = get_source(source)
    item, created = upsert_turn_feedback(
        {
            "source": source,
            "source_label": data_source.label,
            "kind": request.kind,
            "reason": request.reason,
            "category": request.category,
            "question": turn["question"],
            "sql": request.sql,
            "turn_id": turn_id,
            "submitted_user_id": auth.user_id,
            "role_binding_id": auth.role_binding_id,
            "explanation": {
                "submitted_by": auth.username,
                "role": auth.role,
                "role_label": auth.role_label,
                "turn_id": turn_id,
            },
        }
    )
    if not created:
        delete_review_items_for_feedback(str(item["id"]))
    review = create_feedback_review(item)
    return {
        "item": _public_feedback(item),
        "review": {
            "id": review["id"],
            "status": review["status"],
            "type": review["type"],
        }
        if review
        else None,
        "created": created,
    }


def cancel_turn_feedback(auth: AuthContext, turn_id: int) -> dict[str, Any]:
    turn = get_turn(auth, turn_id)
    source = str((turn.get("context") or {}).get("source") or "teaching")
    deleted = delete_turn_feedback(
        source,
        turn_id=turn_id,
        submitted_user_id=int(auth.user_id or 0),
        role_binding_id=int(auth.role_binding_id or 0),
    )
    deleted_reviews = delete_review_items_for_feedback(str(deleted["id"]))
    return {
        "deleted": True,
        "turn_id": turn_id,
        "feedback_id": deleted["id"],
        "deleted_reviews": deleted_reviews,
    }


def _validate_candidate_sql(sql: str) -> None:
    statements = sqlparse.parse(sql.strip().rstrip(";"))
    if len(statements) != 1:
        raise ValueError("反馈中的 SQL 必须是单条只读查询")
    first_dml = next((token for token in statements[0].flatten() if token.ttype is DML), None)
    if first_dml is None or first_dml.normalized.upper() != "SELECT":
        raise ValueError("反馈中的 SQL 必须是只读 SELECT")


def _public_feedback(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "turn_id": item["turn_id"],
        "kind": item["kind"],
        "category": item["category"],
        "reason": item["reason"],
        "status": item["status"],
        "created_at": item["created_at"],
        "updated_at": item.get("updated_at"),
    }
