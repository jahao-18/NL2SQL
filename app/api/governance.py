"""Governance review queue and settings routes."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from app.core.business_domains import require_admin, user_from_token

from app.core.governance import (
    accept_review_item,
    create_low_confidence_review,
    list_review_items,
    load_settings,
    patch_review_item,
    reject_review_item,
    save_settings,
)
from app.models.schemas import (
    GovernanceSettingsRequest,
    GovernanceSettingsResponse,
    ReviewAcceptRequest,
    ReviewAcceptResponse,
    ReviewItemPatchRequest,
    ReviewItemResponse,
    ReviewListResponse,
    ReviewRejectRequest,
)

router = APIRouter(prefix="/api/governance")


@router.get("/review-items", response_model=ReviewListResponse)
def get_review_items(
    source: str | None = Query(None),
    status: str | None = Query(None),
    kind: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    ctx=Header(None, alias="X-Demo-Token"),
) -> ReviewListResponse:
    require_admin(ctx)
    return ReviewListResponse(items=list_review_items(source=source, status=status, kind=kind, limit=limit))


@router.patch("/review-items/{item_id}", response_model=ReviewItemResponse)
def update_review_item(item_id: str, req: ReviewItemPatchRequest, ctx=Header(None, alias="X-Demo-Token")) -> ReviewItemResponse:
    require_admin(ctx)
    try:
        return ReviewItemResponse(item=patch_review_item(item_id, req.model_dump(exclude_unset=True, exclude_none=True)))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="review item not found")


@router.post("/review-items/{item_id}/accept", response_model=ReviewAcceptResponse)
def accept_review_item_endpoint(item_id: str, req: ReviewAcceptRequest, ctx=Header(None, alias="X-Demo-Token")) -> ReviewAcceptResponse:
    require_admin(ctx)
    try:
        result = accept_review_item(item_id, req.action, req.payload)
        return ReviewAcceptResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="review item not found")


@router.post("/review-items/{item_id}/reject", response_model=ReviewItemResponse)
def reject_review_item_endpoint(item_id: str, req: ReviewRejectRequest, ctx=Header(None, alias="X-Demo-Token")) -> ReviewItemResponse:
    require_admin(ctx)
    try:
        return ReviewItemResponse(item=reject_review_item(item_id, req.reason))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="review item not found")


@router.post("/review-items/low-confidence")
def create_low_confidence_review_endpoint(payload: dict, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    user_from_token(ctx)
    item = create_low_confidence_review(payload)
    return {"queued": item is not None, "item": item}


@router.get("/settings", response_model=GovernanceSettingsResponse)
def get_governance_settings(ctx=Header(None, alias="X-Demo-Token")) -> GovernanceSettingsResponse:
    require_admin(ctx)
    return GovernanceSettingsResponse(settings=load_settings())


@router.put("/settings", response_model=GovernanceSettingsResponse)
def update_governance_settings(req: GovernanceSettingsRequest, ctx=Header(None, alias="X-Demo-Token")) -> GovernanceSettingsResponse:
    require_admin(ctx)
    return GovernanceSettingsResponse(settings=save_settings(req.model_dump(exclude_unset=True, exclude_none=True)))
