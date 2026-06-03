"""API 请求 / 响应模型。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Turn(BaseModel):
    """一轮历史对话。kind=sql 时 content 是 SQL;kind=clarify 时 content 是模型问用户的澄清问题。"""
    question: str = Field(..., min_length=1, max_length=500)
    sql: str = Field(..., min_length=1, max_length=2000, description="kind=sql 时为 SQL,kind=clarify 时为 'CLARIFY: ...' 文本")
    kind: Literal["sql", "clarify"] = Field("sql", description="本轮模型输出类型")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="用户的自然语言问题")
    history: list[Turn] = Field(default_factory=list, description="历史对话,最近 N 轮,无状态由前端持有")
    source: str | None = Field(None, description="手动选定的数据源(硬锁,跳过自动路由);None=自动路由")
    current_source: str | None = Field(None, description="本会话当前所在数据源,自动路由时作为提示,让追问留在原库、换话题再切库")
    user_glossary: list[str] = Field(default_factory=list, max_length=50,
                                     description="用户为当前数据源补充的术语/取值映射,逐条拼进 schema 喂模型(前端按库存 localStorage)")


class SourceInfo(BaseModel):
    name: str
    label: str
    dialect: str


class SourcesResponse(BaseModel):
    sources: list[SourceInfo]
    default: str


class AskResponse(BaseModel):
    sql: str | None = Field(None, description="最终执行的 SQL(失败时可能为 None 或上次失败的 SQL)")
    columns: list[str] = Field(default_factory=list)
    column_sources: list[str] = Field(default_factory=list, description="每列对应的源表达式(去掉别名),顺序与 columns 对齐")
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    elapsed_ms: int = 0
    truncated: bool = Field(False, description="用户请求的 LIMIT 是否被收紧到 MAX_ROWS")
    error: str | None = None
    clarify: str | None = Field(None, description="LLM 觉得信息模糊,需要用户先回答这个问题再继续")
    source: str | None = Field(None, description="本次实际使用的数据源 name")
    source_label: str | None = Field(None, description="数据源显示名")
    auto_routed: bool = Field(False, description="数据源是否由系统按问题自动选择")
    confidence: int | None = Field(None, description="AI 评估的答案准确率 0-100(召回质量+SQL正确性合成),None=未评估")
    confidence_detail: ConfidenceDetail | None = Field(None, description="准确率分项明细")
    judge_id: str | None = Field(None, description="异步准确率评估的取件号;非空时前端用它请求 /api/judge 补勋章")


class ConfidenceDetail(BaseModel):
    """准确率评估的分项,供前端 tooltip 展示。"""
    retrieval: int = Field(..., description="召回质量 0-100")
    correctness: int = Field(..., description="SQL 正确性 0-100")
    reason: str = Field("", description="裁判 LLM 给的一句话理由")


class JudgeRequest(BaseModel):
    """异步准确率评估请求:凭 /api/ask 返回的 judge_id 取件并评分。"""
    judge_id: str = Field(..., min_length=1, max_length=64)


class JudgeResponse(BaseModel):
    """异步准确率评估结果;judge_id 过期或评估失败时 confidence 为 None。"""
    confidence: int | None = Field(None, description="最终准确率 0-100,None=未评估/已过期")
    confidence_detail: ConfidenceDetail | None = Field(None, description="准确率分项明细")


class SchemaResponse(BaseModel):
    tables: dict[str, list[str]]
    ddl: str
