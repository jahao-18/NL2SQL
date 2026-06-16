"""HTTP 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.data_sources import get_source, load_sources
from app.core.feedback import add_feedback, list_feedback
from app.core.judge import stashed_status
from app.core.retrieval import retrieve_context
from app.core.schema import count_columns, load_schema
from app.core.schema_profile import load_profile_dict, save_profile_dict
from app.core.source_router import route
from app.models.schemas import (
    AskRequest,
    AskResponse,
    ConfidenceDetail,
    DebugRequest,
    DebugResponse,
    FeedbackListResponse,
    FeedbackRequest,
    FeedbackResponse,
    JudgeRequest,
    JudgeResponse,
    ProfileResponse,
    ProfileUpdateRequest,
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
    return FeedbackResponse(item=add_feedback(req.model_dump()))


@router.get("/feedback", response_model=FeedbackListResponse)
def get_feedback(source: str | None = Query(None), limit: int = Query(100, ge=1, le=500)) -> FeedbackListResponse:
    return FeedbackListResponse(items=list_feedback(source, limit))


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
