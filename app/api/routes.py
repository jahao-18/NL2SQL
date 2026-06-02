"""HTTP 路由。"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.schema import load_schema
from app.models.schemas import AskRequest, AskResponse, SchemaResponse
from app.service import ask as ask_service

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/schema", response_model=SchemaResponse)
def get_schema() -> SchemaResponse:
    info = load_schema()
    return SchemaResponse(tables=info.tables, ddl=info.ddl_text)


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    result = ask_service(req.question, history=req.history)
    return AskResponse(**result)
