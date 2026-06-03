"""HTTP 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.data_sources import get_source, load_sources
from app.core.judge import run_stashed as run_stashed_judge
from app.core.schema import load_schema
from app.models.schemas import (
    AskRequest,
    AskResponse,
    ConfidenceDetail,
    JudgeRequest,
    JudgeResponse,
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
    return SchemaResponse(tables=info.tables, ddl=info.ddl_text)


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    try:
        # 校验 source 存在(若给了)
        if req.source is not None:
            get_source(req.source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    result = ask_service(req.question, history=req.history, source=req.source,
                         current_source=req.current_source, user_glossary=req.user_glossary)
    return AskResponse(**result)


@router.post("/judge", response_model=JudgeResponse)
def judge(req: JudgeRequest) -> JudgeResponse:
    """异步准确率评估:凭 /api/ask 返回的 judge_id 取件并跑裁判。best-effort,失败/过期返回空。"""
    jr = run_stashed_judge(req.judge_id)
    if jr is None:
        return JudgeResponse(confidence=None, confidence_detail=None)
    return JudgeResponse(
        confidence=jr.final,
        confidence_detail=ConfidenceDetail(
            retrieval=jr.retrieval, correctness=jr.correctness, reason=jr.reason
        ),
    )
