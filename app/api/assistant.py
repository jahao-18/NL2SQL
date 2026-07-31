"""Authenticated HTTP API for the V3 unified assistant."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from app.core.assistant_context import AssistantPage, AssistantPageContext
from app.core.action_drafts import (
    ActionDraftConflictError,
    ActionDraftCreate,
    ActionDraftError,
    ActionDraftExpiredError,
    ActionDraftNotFoundError,
    confirm_action_draft,
    create_action_draft,
    get_action_draft,
)
from app.core.assistant_orchestrator import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    query_assistant,
)
from app.core.assistant_feedback import (
    AssistantTurnFeedbackRequest,
    cancel_turn_feedback,
    submit_turn_feedback,
)
from app.core.semantic_metrics import SemanticMetricNotFoundError, metric_results
from app.core.assistant_quality import quality_operations
from app.core.assistant_sessions import (
    AssistantSessionConflictError,
    AssistantSessionCreate,
    AssistantSessionNotFoundError,
    AssistantSessionUpdate,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    update_session,
)
from app.core.business_domains import user_from_token


router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def _auth(token: str | None):
    return user_from_token(token)


@router.post("/query", response_model=AssistantQueryResponse)
def assistant_query(
    request: AssistantQueryRequest,
    token: str | None = Header(None, alias="X-Demo-Token"),
) -> AssistantQueryResponse:
    try:
        return query_assistant(_auth(token), request)
    except AssistantSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AssistantSessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/turns/{turn_id}/feedback")
def assistant_turn_feedback(
    turn_id: int,
    request: AssistantTurnFeedbackRequest,
    token: str | None = Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return submit_turn_feedback(_auth(token), turn_id, request)
    except AssistantSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/turns/{turn_id}/feedback")
def assistant_turn_feedback_cancel(
    turn_id: int,
    token: str | None = Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return cancel_turn_feedback(_auth(token), turn_id)
    except (AssistantSessionNotFoundError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="回答反馈不存在") from exc


@router.get("/metrics")
def assistant_metrics(
    page: AssistantPage = Query(...),
    teaching_class_id: int | None = Query(None, gt=0),
    student_id: int | None = Query(None, gt=0),
    college_id: int | None = Query(None, gt=0),
    academic_year: int | None = Query(None, ge=2000, le=2200),
    semester: str | None = Query(None, min_length=1, max_length=40),
    code: str | None = Query(None, min_length=1, max_length=100),
    token: str | None = Header(None, alias="X-Demo-Token"),
) -> dict:
    """Return role- and page-visible certified metrics using the shared evaluator."""
    try:
        context = AssistantPageContext.model_validate(
            {
                "page": page,
                "teaching_class_id": teaching_class_id,
                "student_id": student_id,
                "college_id": college_id,
                "academic_year": academic_year,
                "semester": semester,
            }
        )
        return metric_results(_auth(token), context, code=code)
    except SemanticMetricNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/quality-operations")
def assistant_quality_operations(
    days: int = Query(30, ge=1, le=90),
    token: str | None = Header(None, alias="X-Demo-Token"),
) -> dict:
    """Return privacy-safe aggregate assistant operations metrics for admins."""
    return quality_operations(_auth(token), days=days)


@router.post("/action-drafts", status_code=201)
def assistant_action_draft_create(
    request: ActionDraftCreate,
    token: str | None = Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return {"item": create_action_draft(_auth(token), request)}
    except ActionDraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionDraftConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ActionDraftError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/action-drafts/{draft_id}")
def assistant_action_draft_detail(
    draft_id: str,
    token: str | None = Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return {"item": get_action_draft(_auth(token), draft_id)}
    except ActionDraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/action-drafts/{draft_id}/confirm")
def assistant_action_draft_confirm(
    draft_id: str,
    token: str | None = Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return {"item": confirm_action_draft(_auth(token), draft_id)}
    except ActionDraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionDraftExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except ActionDraftConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ActionDraftError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sessions")
def assistant_session_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    token: str | None = Header(None, alias="X-Demo-Token"),
) -> dict:
    return list_sessions(_auth(token), page=page, page_size=page_size)


@router.post("/sessions", status_code=201)
def assistant_session_create(
    request: AssistantSessionCreate,
    token: str | None = Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return {"item": create_session(_auth(token), request)}
    except AssistantSessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/sessions/{session_id}")
def assistant_session_detail(
    session_id: int,
    turn_page: int = Query(1, ge=1),
    turn_page_size: int = Query(20, ge=1, le=100),
    token: str | None = Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return get_session(
            _auth(token),
            session_id,
            turn_page=turn_page,
            turn_page_size=turn_page_size,
        )
    except AssistantSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/sessions/{session_id}")
def assistant_session_update(
    session_id: int,
    request: AssistantSessionUpdate,
    token: str | None = Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return {"item": update_session(_auth(token), session_id, request)}
    except AssistantSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/sessions/{session_id}")
def assistant_session_delete(
    session_id: int,
    token: str | None = Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return delete_session(_auth(token), session_id)
    except AssistantSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
