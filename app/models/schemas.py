"""API 请求 / 响应模型。"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class Turn(BaseModel):
    """一轮历史对话。kind=sql 时 content 是 SQL;kind=clarify 时 content 是模型问用户的澄清问题。"""
    question: str = Field(..., min_length=1, max_length=500)
    sql: str = Field(..., min_length=1, max_length=2000, description="kind=sql 时为 SQL,kind=clarify 时为 'CLARIFY: ...' 文本")
    kind: Literal["sql", "clarify"] = Field("sql", description="本轮模型输出类型")


class FewShotExample(BaseModel):
    """用户收藏的问法-SQL 样例,用于按数据源注入 few-shot。"""
    question: str = Field(..., min_length=1, max_length=500)
    sql: str = Field(..., min_length=1, max_length=3000)
    source: str | None = Field(None, max_length=100)
    source_label: str | None = Field(None, max_length=100)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="用户的自然语言问题")
    history: list[Turn] = Field(default_factory=list, max_length=20, description="历史对话,最近 N 轮,无状态由前端持有")
    source: str | None = Field(None, max_length=100, description="手动选定的数据源(硬锁,跳过自动路由);None=自动路由")
    current_source: str | None = Field(None, max_length=100, description="本会话当前所在数据源,自动路由时作为提示,让追问留在原库、换话题再切库")
    user_glossary: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(default_factory=list, max_length=50,
                                     description="用户为当前数据源补充的术语/取值映射,逐条拼进 schema 喂模型(前端按库存 localStorage)")
    few_shots: list[FewShotExample] = Field(default_factory=list, max_length=20,
                                            description="用户收藏的样例 SQL,后端按本次数据源筛选后作为 few-shot 注入")


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=80)


class RoleSwitchRequest(BaseModel):
    role_binding_id: int = Field(..., gt=0)


class RegisterRequest(BaseModel):
    password: str = Field(..., min_length=8, max_length=32)
    display_name: str = Field(..., min_length=2, max_length=40)
    identity_type: Literal["student", "teacher"]
    identifier: str = Field(..., min_length=1, max_length=40)


class IdentityReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = Field("", max_length=500)


class IdentityBatchReviewRequest(IdentityReviewRequest):
    application_ids: list[int] = Field(..., min_length=1, max_length=100)


class PositionAssignmentCreateRequest(BaseModel):
    position_slot_id: int = Field(..., gt=0)
    user_id: int = Field(..., gt=0)
    assignment_type: Literal["primary", "deputy", "acting", "temporary", "reviewer"] = "primary"
    scope_ids: list[int] = Field(default_factory=list, max_length=200)
    valid_from: str = Field(..., min_length=8, max_length=40)
    valid_until: str | None = Field(None, max_length=40)
    reason: str = Field(..., min_length=1, max_length=500)
    reauth_password: str | None = Field(None, max_length=80)


class PositionAssignmentEndRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    reauth_password: str | None = Field(None, max_length=80)


class PositionAssignmentUpdateRequest(BaseModel):
    scope_ids: list[int] | None = Field(None, max_length=200)
    valid_until: str | None = Field(None, max_length=40)
    reason: str = Field(..., min_length=1, max_length=500)
    reauth_password: str | None = Field(None, max_length=80)


class PositionAssignmentTransferRequest(BaseModel):
    successor_user_id: int = Field(..., gt=0)
    assignment_type: Literal["primary", "deputy", "acting", "temporary", "reviewer"] = "primary"
    scope_ids: list[int] | None = Field(None, max_length=200)
    valid_from: str = Field(..., min_length=8, max_length=40)
    valid_until: str | None = Field(None, max_length=40)
    reason: str = Field(..., min_length=1, max_length=500)
    reauth_password: str | None = Field(None, max_length=80)


class AccountSecurityActionRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    reauth_password: str = Field(..., min_length=1, max_length=80)


class StudentLifecycleActionRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class StudentBatchGraduationRequest(StudentLifecycleActionRequest):
    person_identity_ids: list[int] = Field(..., min_length=1, max_length=500)


class StaffLifecycleRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    reauth_password: str = Field(..., min_length=1, max_length=80)


class StaffTransferRequest(StaffLifecycleRequest):
    destination_college_id: int = Field(..., gt=0)

class AnnouncementRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    body: str = Field(..., min_length=1, max_length=4000)

class CourseResourceRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    description: str = Field("", max_length=1000)
    file_name: str = Field("", max_length=255)
    file_content_base64: str | None = None
    content_type: str = Field("", max_length=160)
    resource_url: str = Field("", max_length=1000)
    visible_from: str | None = Field(None, max_length=40)
    visible_until: str | None = Field(None, max_length=40)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=80)
    new_password: str = Field(..., min_length=6, max_length=32)


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
    route_reason: str | None = Field(None, description="数据源选择原因说明")
    confidence: int | None = Field(None, description="AI 评估的答案准确率 0-100(召回质量+SQL正确性合成),None=未评估")
    confidence_detail: ConfidenceDetail | None = Field(None, description="准确率分项明细")
    judge_id: str | None = Field(None, description="异步准确率评估的取件号;非空时前端用它请求 /api/judge 补勋章")
    explanation: dict[str, Any] = Field(default_factory=dict, description="面向业务用户的口径/关系/路由解释")
    trace: dict[str, Any] = Field(default_factory=dict, description="面向治理和调试的链路证据")


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
    status: Literal["pending", "done", "failed", "missing"] = Field(
        "done", description="裁判任务状态: pending=仍在评估,done=已完成,failed=评估失败,missing=无此任务"
    )


class ColumnMetadata(BaseModel):
    table_name: str
    column_name: str
    data_type: str = ""
    nullable: bool = True
    default_value: str | None = None
    business_name: str = ""
    description: str = ""
    example_values: list[str] = Field(default_factory=list)
    enum_values: list[str] = Field(default_factory=list)
    unit: str = ""
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_metric: bool = False
    is_dimension: bool = False
    semantic_type: str = ""
    default_aggregation: str = ""
    enabled_for_query: bool = True
    sensitive: bool = False
    deprecated: bool = False
    default_filter: str = ""


class SchemaResponse(BaseModel):
    tables: dict[str, list[str]]
    ddl: str
    columns: dict[str, list[ColumnMetadata]] = Field(default_factory=dict)


class ProfileResponse(BaseModel):
    source: str
    profile: dict[str, Any] = Field(default_factory=dict)


class ProfileUpdateRequest(BaseModel):
    profile: dict[str, Any] = Field(default_factory=dict)


class ProfileVersionsResponse(BaseModel):
    items: list[dict[str, Any]]


class ProfilePublishRequest(BaseModel):
    label: str = Field("", max_length=120)
    description: str = Field("", max_length=1000)


class ProfileRollbackRequest(BaseModel):
    version_id: str = Field(..., min_length=1)


class ProfileVersionUpdateRequest(BaseModel):
    label: str = Field("", max_length=120)
    description: str = Field("", max_length=1000)


class QualityResponse(BaseModel):
    report: dict[str, Any]


class FeedbackRequest(BaseModel):
    kind: Literal["correct", "incorrect"] = "incorrect"
    reason: str = Field("", max_length=2000)
    category: str = Field("", max_length=100)
    question: str = Field("", max_length=500)
    sql: str = Field("", max_length=5000)
    source: str = Field("", max_length=100)
    source_label: str = Field("", max_length=120)
    explanation: dict[str, Any] = Field(default_factory=dict)


class FeedbackResponse(BaseModel):
    item: dict[str, Any]


class FeedbackListResponse(BaseModel):
    items: list[dict[str, Any]]


class ReviewItemPatchRequest(BaseModel):
    status: Literal["open", "in_progress", "accepted", "rejected", "closed"] | None = None
    assignee: str = Field("", max_length=100)
    priority: str = Field("", max_length=40)
    resolution: str = Field("", max_length=1000)


class ReviewAcceptRequest(BaseModel):
    action: Literal["example", "field_profile", "relation", "metric", "publish_profile"]
    payload: dict[str, Any] = Field(default_factory=dict)


class ReviewRejectRequest(BaseModel):
    reason: str = Field("", max_length=1000)


class ReviewItemResponse(BaseModel):
    item: dict[str, Any]


class ReviewAcceptResponse(BaseModel):
    item: dict[str, Any]
    action: str
    result: dict[str, Any]


class ReviewListResponse(BaseModel):
    items: list[dict[str, Any]]


class GovernanceSettingsRequest(BaseModel):
    review_required_for_publish: bool | None = None
    auto_queue_error_feedback: bool | None = None
    low_confidence_threshold: int | None = Field(None, ge=0, le=100)
    require_publish_note: bool | None = None
    default_status_filter: str | None = Field(None, max_length=40)
    page_size: int | None = Field(None, ge=10, le=200)


class GovernanceSettingsResponse(BaseModel):
    settings: dict[str, Any]


class ExampleRequest(BaseModel):
    id: str | None = None
    question: str = Field(..., min_length=1, max_length=500)
    sql: str = Field(..., min_length=1, max_length=3000)
    source_label: str = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class ExampleResponse(BaseModel):
    item: dict[str, Any]


class ExampleListResponse(BaseModel):
    items: list[dict[str, Any]]


class DebugRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    source: str | None = None
    current_source: str | None = None
    history: list[Turn] = Field(default_factory=list)


class DebugResponse(BaseModel):
    source: str | None = None
    source_label: str | None = None
    auto_routed: bool = False
    route_reason: str = ""
    table_count: int = 0
    column_count: int = 0
    retrieval_used: bool = False
    retrieval_tables: list[str] = Field(default_factory=list)
    retrievers_used: list[str] = Field(default_factory=list)
    context_preview: str = ""
