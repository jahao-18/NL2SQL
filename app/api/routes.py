"""HTTP 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.data_sources import get_source, load_sources
from app.core.examples import delete_example, list_examples, upsert_example
from app.core.feedback import add_feedback, list_feedback
from app.core.governance import create_feedback_review, create_publish_review, load_settings
from app.core.judge import stashed_status
from app.core.retrieval import retrieve_context
from app.core.schema import count_columns, load_schema
from app.core.schema_profile import (
    delete_profile_version,
    list_profile_versions,
    load_profile_dict,
    publish_profile,
    quality_report,
    rollback_profile,
    save_profile_dict,
    update_profile_version,
)
from app.core.source_router import route
from app.models.schemas import (
    AskRequest,
    AskResponse,
    ConfidenceDetail,
    DebugRequest,
    DebugResponse,
    ExampleListResponse,
    ExampleRequest,
    ExampleResponse,
    FeedbackListResponse,
    FeedbackRequest,
    FeedbackResponse,
    JudgeRequest,
    JudgeResponse,
    ProfileResponse,
    ProfilePublishRequest,
    ProfileRollbackRequest,
    ProfileUpdateRequest,
    ProfileVersionUpdateRequest,
    ProfileVersionsResponse,
    QualityResponse,
    SchemaResponse,
    SourceInfo,
    SourcesResponse,
)
from app.service import ask as ask_service

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/sources", response_model=SourcesResponse)
def list_sources() -> SourcesResponse:
    sources = load_sources()
    items = [
        SourceInfo(name=s.name, label=s.label, dialect=s.dialect)
        for s in sources.values()
    ]
    return SourcesResponse(sources=items, default=items[0].name)


@router.get("/schema", response_model=SchemaResponse)
def get_schema(source: str | None = Query(None)) -> SchemaResponse:
    try:
        info = load_schema(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    # 只返回纯表结构(CREATE TABLE);取值发现/业务词表/派生指标是喂 LLM 的,不展示给用户
    return SchemaResponse(tables=info.tables, ddl=info.pure_ddl, columns=info.columns)


@router.get("/profile", response_model=ProfileResponse)
def get_profile(source: str = Query(...)) -> ProfileResponse:
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ProfileResponse(source=source, profile=load_profile_dict(source))


@router.put("/profile", response_model=ProfileResponse)
def update_profile(req: ProfileUpdateRequest, source: str = Query(...)) -> ProfileResponse:
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    saved = save_profile_dict(source, req.profile)
    return ProfileResponse(source=source, profile=saved)


@router.get("/profile/versions", response_model=ProfileVersionsResponse)
def get_profile_versions(source: str = Query(...)) -> ProfileVersionsResponse:
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ProfileVersionsResponse(items=list_profile_versions(source))


@router.post("/profile/publish")
def publish_profile_endpoint(req: ProfilePublishRequest | None = None, source: str = Query(...)) -> dict:
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    req = req or ProfilePublishRequest()
    settings = load_settings()
    if settings.get("require_publish_note") and not req.description.strip():
        raise HTTPException(status_code=400, detail="发布说明不能为空")
    if settings.get("review_required_for_publish"):
        item = create_publish_review(source, label=req.label, description=req.description)
        return {"published": False, "review_required": True, "item": item}
    return publish_profile(source, label=req.label, description=req.description)


@router.post("/profile/rollback", response_model=ProfileResponse)
def rollback_profile_endpoint(req: ProfileRollbackRequest, source: str = Query(...)) -> ProfileResponse:
    try:
        get_source(source)
        profile = rollback_profile(source, req.version_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"version not found: {e}")
    return ProfileResponse(source=source, profile=profile)


@router.put("/profile/versions/{version_id}")
def update_profile_version_endpoint(
    version_id: str,
    req: ProfileVersionUpdateRequest,
    source: str = Query(...),
) -> dict:
    try:
        get_source(source)
        item = update_profile_version(source, version_id, label=req.label, description=req.description)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"version not found: {e}")
    return {"item": item}


@router.delete("/profile/versions/{version_id}")
def delete_profile_version_endpoint(version_id: str, source: str = Query(...)) -> dict:
    try:
        get_source(source)
        delete_profile_version(source, version_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"version not found: {e}")
    return {"deleted": True}


@router.get("/quality", response_model=QualityResponse)
def get_quality(source: str = Query(...)) -> QualityResponse:
    try:
        info = load_schema(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return QualityResponse(report=quality_report(source, info.tables))


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    try:
        # 校验 source 存在(若给了)
        if req.source is not None:
            get_source(req.source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    result = ask_service(req.question, history=req.history, source=req.source,
                         current_source=req.current_source, user_glossary=req.user_glossary,
                         few_shots=req.few_shots)
    return AskResponse(**result)


@router.post("/judge", response_model=JudgeResponse)
def judge(req: JudgeRequest) -> JudgeResponse:
    """异步准确率评估:凭 /api/ask 返回的 judge_id 取件并跑裁判。best-effort,失败/过期返回空。"""
    status, jr = stashed_status(req.judge_id)
    if jr is None:
        return JudgeResponse(confidence=None, confidence_detail=None, status=status)
    return JudgeResponse(
        confidence=jr.final,
        confidence_detail=ConfidenceDetail(
            retrieval=jr.retrieval, correctness=jr.correctness, reason=jr.reason
        ),
        status="done",
    )


@router.post("/feedback", response_model=FeedbackResponse)
def create_feedback(req: FeedbackRequest) -> FeedbackResponse:
    item = add_feedback(req.model_dump())
    create_feedback_review(item)
    return FeedbackResponse(item=item)


@router.get("/feedback", response_model=FeedbackListResponse)
def get_feedback(source: str | None = Query(None), limit: int = Query(100, ge=1, le=500)) -> FeedbackListResponse:
    return FeedbackListResponse(items=list_feedback(source, limit))


@router.get("/examples", response_model=ExampleListResponse)
def get_examples(source: str = Query(...), limit: int = Query(200, ge=1, le=500)) -> ExampleListResponse:
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ExampleListResponse(items=list_examples(source, limit))


@router.post("/examples", response_model=ExampleResponse)
def save_example(req: ExampleRequest, source: str = Query(...)) -> ExampleResponse:
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ExampleResponse(item=upsert_example(source, req.model_dump()))


@router.delete("/examples/{item_id}")
def remove_example(item_id: str, source: str = Query(...)) -> dict:
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    delete_example(source, item_id)
    return {"deleted": True}


@router.post("/debug/retrieval", response_model=DebugResponse)
def debug_retrieval(req: DebugRequest) -> DebugResponse:
    try:
        if req.source:
            ds = get_source(req.source)
            picked = ds.name
            auto_routed = False
        else:
            picked = route(req.question, req.history, req.current_source)
            if not picked:
                picked = req.current_source or get_source(None).name
            ds = get_source(picked)
            auto_routed = True
        info = load_schema(ds.name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    rc = retrieve_context(req.question, ds.name, info.ddl_text)
    table_count = len(info.tables)
    column_total = count_columns(ds.name)
    if rc is None:
        return DebugResponse(
            source=ds.name,
            source_label=ds.label,
            auto_routed=auto_routed,
            route_reason="手动锁库" if req.source else "自动路由或默认数据源",
            table_count=table_count,
            column_count=column_total,
            retrieval_used=False,
            context_preview=info.ddl_text[:1200],
        )
    return DebugResponse(
        source=ds.name,
        source_label=ds.label,
        auto_routed=auto_routed,
        route_reason="手动锁库" if req.source else "自动路由或默认数据源",
        table_count=table_count,
        column_count=column_total,
        retrieval_used=True,
        retrieval_tables=rc.tables,
        retrievers_used=rc.retrievers_used,
        context_preview=rc.context_text[:2000],
    )
