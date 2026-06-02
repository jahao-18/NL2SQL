"""API 请求 / 响应模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Turn(BaseModel):
    """一轮成功的历史对话(用户问题 + 模型生成的最终 SQL)。"""
    question: str = Field(..., min_length=1, max_length=500)
    sql: str = Field(..., min_length=1, max_length=2000)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="用户的自然语言问题")
    history: list[Turn] = Field(default_factory=list, description="历史对话,最近 N 轮,无状态由前端持有")


class AskResponse(BaseModel):
    sql: str | None = Field(None, description="最终执行的 SQL(失败时可能为 None 或上次失败的 SQL)")
    columns: list[str] = Field(default_factory=list)
    column_sources: list[str] = Field(default_factory=list, description="每列对应的源表达式(去掉别名),顺序与 columns 对齐")
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    elapsed_ms: int = 0
    truncated: bool = Field(False, description="用户请求的 LIMIT 是否被收紧到 MAX_ROWS")
    error: str | None = None


class SchemaResponse(BaseModel):
    tables: dict[str, list[str]]
    ddl: str
