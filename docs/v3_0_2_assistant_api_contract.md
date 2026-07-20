# V3-0.2 统一智能助手 API 契约

> 任务编号：V3-0.2
> 契约版本：V3 Assistant Contract v1
> 冻结日期：2026-07-18
> 任务状态：已完成
> 实现状态：契约已冻结，API 尚未实现。后续实现从 V3-0.3 和 V3-1.1 开始。

## 1. 契约目标

本契约定义 V3 统一智能助手的：

- 入口 API。
- 请求与响应结构。
- 页面上下文和权限语义。
- 会话与工作身份隔离规则。
- 回答状态和错误语义。
- 认证指标、证据和执行链路摘要。
- 白名单动作草稿及确认机制。
- 与现有 `/api/ask` 的兼容策略。

后续实现不得在未更新本契约并重新审核的情况下实质改变字段含义、权限或状态机。

## 2. 设计原则

1. **一个统一查询入口，多种确定性执行路径。** 智能助手可以选择认证指标、业务状态 API、NL2SQL、导航或知识检索。
2. **服务端权限是唯一事实源。** 前端传递的页面上下文不能扩大权限。
3. **业务失败结构化返回。** 模型、检索、SQL 或知识源失败不会导致 FastAPI 进程异常。
4. **认证授权错误使用 HTTP 状态码。** 不把未登录、越权和请求格式错误包装成普通回答。
5. **AI 不直接执行高风险写操作。** AI 只能建议白名单动作，动作必须生成服务端草稿并人工确认。
6. **兼容现有接口。** V3 首版保留 `/api/ask`，不要求旧前端一次性迁移。
7. **响应对普通用户可解释，对管理员可治理。** 普通响应不暴露完整 Prompt、密钥、内部连接地址或敏感日志。

## 3. 认证与公共约定

### 3.1 认证

V3 首版继续沿用当前认证方式：

```http
X-Demo-Token: <session-token>
```

后续如迁移到标准 `Authorization: Bearer`，应作为独立认证升级任务处理，不能在 V3 助手实现中隐式改变。

### 3.2 内容类型

```http
Content-Type: application/json
Accept: application/json
```

### 3.3 时间

- API 时间统一使用带时区的 ISO 8601 字符串。
- 前端只负责本地化展示，不使用客户端时间决定截止、过期或有效状态。

### 3.4 ID

- 业务对象继续使用现有整数 ID。
- 会话、轮次和动作草稿可以使用整数 ID 或不可猜测字符串 ID；具体数据库实现需在 V3-0.3 固定。
- 无论采用何种 ID，都不能依赖 ID 不可猜测替代授权校验。

### 3.5 幂等性

- 查询请求本身只读，不强制客户端提供幂等键。
- 动作确认必须具备一次性执行语义。
- 通知等可能产生写操作的动作草稿必须防止重复确认。

## 4. 回答状态与类型

### 4.1 `status`

| 值 | 含义 | 是否包含业务结果 |
|---|---|---|
| `success` | 成功完成 | 是 |
| `clarify` | 需要用户补充信息 | 否 |
| `rejected` | 问题触发权限或安全边界 | 否 |
| `failed` | 模型、检索、SQL、指标或知识执行失败 | 否或只有安全的部分结果 |
| `degraded` | 降级完成，例如缺少向量检索但固定指标或关键词路径成功 | 是 |

### 4.2 `answer_type`

| 值 | 含义 |
|---|---|
| `metric` | 认证指标或固定统计 |
| `business_state` | 当前待办、状态或业务对象查询 |
| `nl2sql` | 通过现有 NL2SQL 链路完成 |
| `navigation` | 主要结果为安全业务导航 |
| `knowledge` | 受控制度或知识文档回答 |
| `hybrid` | 结构化数据与制度知识联合回答 |
| `unsupported` | 当前助手无法处理 |

V3-1.3 首版只要求实现：

```text
metric / business_state / nl2sql / navigation / unsupported
```

`knowledge` 和 `hybrid` 在 V3-4 实现前必须返回未实现或不可用，不得伪造完成状态。

## 5. 页面上下文契约

### 5.1 请求结构

```json
{
  "page": "course_space",
  "teaching_class_id": 101,
  "student_id": null,
  "college_id": null,
  "academic_year": 2025,
  "semester": "spring",
  "time_range": {
    "start": "2026-07-11T00:00:00+08:00",
    "end": "2026-07-18T23:59:59+08:00"
  },
  "filters": {
    "assignment_status": "missing"
  }
}
```

### 5.2 建议模型

```text
AssistantPageContext
├─ page: string, required, max 80
├─ teaching_class_id: integer | null
├─ student_id: integer | null
├─ college_id: integer | null
├─ academic_year: integer | null
├─ semester: string | null
├─ time_range: AssistantTimeRange | null
└─ filters: object, default {}, maximum serialized size 4 KB
```

### 5.3 权限语义

后端处理顺序：

1. 通过 token 恢复当前 `AuthContext`。
2. 验证账号、会话版本和当前角色绑定仍有效。
3. 根据 `page` 确认当前角色是否具有页面能力。
4. 根据课程成员、任课关系、行政班或学院范围验证对象 ID。
5. 将客户端上下文与服务端授权范围求交集。
6. 生成 `effective_context`。
7. 无权上下文直接返回 HTTP 403，不进入 LLM、检索或 SQL 执行。

### 5.4 页面标识

首版可接受页面标识：

```text
dashboard
assistant
course_space
assignment_workflow
attendance
course_analytics
support_workbench
teaching_operations
notifications
governance
data_access
profile
```

新增页面标识必须同时更新后端枚举、前端调用、权限测试和功能目录。

## 6. 统一查询 API

### 6.1 `POST /api/assistant/query`

用途：统一处理认证指标、业务状态、NL2SQL、导航和后续知识问答。

#### 请求

```json
{
  "session_id": 1001,
  "question": "哪些学生同时存在两次缺勤和本次作业未交？",
  "context": {
    "page": "course_space",
    "teaching_class_id": 101,
    "academic_year": 2025,
    "semester": "spring",
    "filters": {}
  },
  "options": {
    "preferred_answer_type": null,
    "include_sql": true,
    "include_trace": false,
    "max_rows": null
  }
}
```

#### 请求字段

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `session_id` | integer/string/null | 否 | 不提供时后端可创建会话 |
| `question` | string | 是 | 1–500 字符，去除首尾空白后不能为空 |
| `context` | object | 是 | 必须包含合法 `page` |
| `options` | object | 否 | 只能影响展示和缩小结果，不得扩大权限 |
| `preferred_answer_type` | enum/null | 否 | 仅为偏好，后端可选择更安全路径 |
| `include_sql` | boolean | 否 | 默认 true；无 SQL 的回答返回 null |
| `include_trace` | boolean | 否 | 普通用户只返回安全摘要，管理员可获得更多治理字段 |
| `max_rows` | integer/null | 否 | 必须小于等于服务端 `MAX_ROWS` |

#### 成功或降级响应

```json
{
  "session_id": 1001,
  "turn_id": 2001,
  "status": "success",
  "answer_type": "nl2sql",
  "answer": "本次作业有 5 名学生未提交，其中 2 人同时存在两次缺勤。",
  "data": {
    "columns": ["student_id", "missing_count", "absence_count"],
    "rows": [[10001, 1, 2]],
    "row_count": 1,
    "truncated": false
  },
  "sql": "SELECT ...",
  "scope": {
    "role": "teacher",
    "teaching_class_ids": [101],
    "description": "仅统计本人授课的当前课程"
  },
  "time_range": {
    "start": "2026-07-11T00:00:00+08:00",
    "end": "2026-07-18T23:59:59+08:00",
    "description": "最近 7 天"
  },
  "evidence": [
    {
      "kind": "data",
      "label": "作业提交与课程场次考勤",
      "source": "teaching",
      "updated_at": "2026-07-18T21:00:00+08:00"
    }
  ],
  "metric_definitions": [],
  "warnings": [],
  "confidence": {
    "score": 88,
    "status": "done",
    "reason": "范围和结果与问题一致"
  },
  "trace_summary": {
    "route": "nl2sql",
    "retrievers_used": ["vector", "keyword", "glossary", "graph"],
    "degraded": false,
    "elapsed_ms": 860
  },
  "suggested_questions": [
    "这 5 名学生分别缺交了哪些作业？"
  ],
  "suggested_actions": [
    {
      "draft_id": "act_01",
      "type": "open_assignment_roster",
      "label": "查看未交名单",
      "requires_confirmation": false,
      "expires_at": "2026-07-18T22:00:00+08:00"
    }
  ],
  "error": null,
  "clarify": null
}
```

#### 澄清响应

```json
{
  "session_id": 1001,
  "turn_id": 2002,
  "status": "clarify",
  "answer_type": "unsupported",
  "answer": "",
  "data": null,
  "sql": null,
  "scope": {},
  "time_range": null,
  "evidence": [],
  "metric_definitions": [],
  "warnings": [],
  "confidence": null,
  "trace_summary": {},
  "suggested_questions": [],
  "suggested_actions": [],
  "error": null,
  "clarify": "请说明要查询的学期。"
}
```

#### 业务失败响应

模型、检索、SQL、指标或知识源执行失败时，首版沿用当前 `/api/ask` 的兼容思路：HTTP 200，响应 `status=failed`，并且不返回不安全的部分结果。

```json
{
  "session_id": 1001,
  "turn_id": 2003,
  "status": "failed",
  "answer_type": "nl2sql",
  "answer": "",
  "data": null,
  "sql": null,
  "scope": {
    "role": "teacher",
    "teaching_class_ids": [101]
  },
  "time_range": null,
  "evidence": [],
  "metric_definitions": [],
  "warnings": [],
  "confidence": null,
  "trace_summary": {
    "failed_stage": "llm"
  },
  "suggested_questions": [],
  "suggested_actions": [],
  "error": {
    "code": "ASSISTANT_LLM_UNAVAILABLE",
    "message": "智能问数服务暂时不可用，请稍后重试。",
    "retryable": true
  },
  "clarify": null
}
```

### 6.2 响应字段稳定性

- 所有状态下顶层字段保持稳定，缺失内容使用 null、空数组或空对象。
- `data.rows` 只允许 JSON 标量，不返回数据库游标、ORM 对象或二进制内容。
- `sql` 只在安全校验通过后返回最终 SQL；权限前置拒绝时必须为 null。
- `scope` 返回最终生效范围摘要，不返回内部权限实现细节或完整允许表清单。
- `trace_summary` 对普通用户隐藏 Prompt、连接地址、密钥、原始异常堆栈和敏感 Schema。

## 7. 会话 API

### 7.1 `GET /api/assistant/sessions`

查询当前用户当前工作身份的会话列表。

查询参数：

```text
page=1
page_size=20
```

响应：

```json
{
  "items": [
    {
      "id": 1001,
      "title": "数据库系统课程分析",
      "page": "course_space",
      "last_question": "哪些学生未交作业？",
      "created_at": "2026-07-18T20:00:00+08:00",
      "updated_at": "2026-07-18T21:00:00+08:00"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

### 7.2 `POST /api/assistant/sessions`

请求：

```json
{
  "title": "数据库系统课程分析",
  "context": {
    "page": "course_space",
    "teaching_class_id": 101
  }
}
```

创建时保存经过服务端校验的上下文摘要，不保存未经验证的权限范围。

### 7.3 `GET /api/assistant/sessions/{session_id}`

返回当前工作身份会话及分页轮次。其他用户、其他角色绑定或已失效角色绑定访问时返回 404，不暴露对象是否存在。

### 7.4 `PATCH /api/assistant/sessions/{session_id}`

首版只允许：

- 修改标题。
- 收藏/取消收藏。

不允许通过 PATCH 修改会话所属用户、工作身份或扩大上下文范围。

### 7.5 `DELETE /api/assistant/sessions/{session_id}`

首版采用软删除。删除后：

- 不出现在本人列表。
- 不能继续提交问题。
- 关联未执行动作草稿立即失效。
- 治理所需的脱敏执行统计可以按保留策略继续存在。

## 8. 回答反馈 API

### 8.1 `POST /api/assistant/turns/{turn_id}/feedback`

请求：

```json
{
  "rating": "correct",
  "reason_code": null,
  "comment": "口径和结果符合预期"
}
```

`rating`：

```text
correct
incorrect
unclear_metric
incomplete
unsafe
```

约束：

- 用户只能反馈本人当前工作身份的回答。
- `comment` 最大 1000 字符。
- 反馈不能直接修改指标或知识库。
- 是否进入治理队列由现有治理规则决定。

## 9. 认证指标 API

### 9.1 `GET /api/assistant/metrics`

按当前角色、页面和上下文返回允许使用的认证指标。

查询参数：

```text
page=course_space
teaching_class_id=101
```

响应：

```json
{
  "items": [
    {
      "code": "assignment_completion_rate",
      "name": "作业完成率",
      "description": "已提交人数占当前作业应提交人数的比例",
      "formula": "submitted_count / expected_count",
      "time_semantics": "按作业截止时间与当前提交状态",
      "minimum_sample_size": 1,
      "supports_drilldown": true,
      "updated_at": "2026-07-18T21:00:00+08:00"
    }
  ]
}
```

普通用户不得通过该接口读取不属于当前角色的数据表、SQL 模板或内部范围规则。

## 10. 动作草稿 API

### 10.1 动作类型

首批白名单：

| 类型 | 用途 | 是否需要确认 |
|---|---|---:|
| `open_assignment_roster` | 打开作业名单 | 否 |
| `open_course` | 打开课程 | 否 |
| `open_support_case` | 打开支持事项 | 否 |
| `open_teaching_issue` | 打开教学异常 | 否 |
| `apply_safe_filter` | 在指定业务页面应用后端认可筛选 | 否 |
| `draft_course_notification` | 生成课程提醒草稿 | 是 |
| `submit_governance_feedback` | 将问题提交治理 | 是 |
| `export_current_result` | 导出当前结果 | 是 |

### 10.2 草稿结构

```json
{
  "draft_id": "act_01",
  "type": "draft_course_notification",
  "label": "生成课程提醒",
  "preview": {
    "title": "作业提交提醒",
    "recipient_count": 5,
    "body": "请在截止时间前完成本次作业。"
  },
  "requires_confirmation": true,
  "expires_at": "2026-07-18T22:00:00+08:00"
}
```

服务端保存真实结构化参数；前端不得通过修改 preview 改变执行对象。

### 10.3 `POST /api/assistant/actions/{draft_id}/confirm`

请求：

```json
{
  "confirmation": true
}
```

执行前必须重新校验：

- 当前账号和 token 有效。
- 当前工作身份与创建草稿时一致。
- 草稿未过期、未取消、未执行。
- 业务对象仍在当前权限范围内。
- 业务状态仍允许执行。
- 当前用户拥有目标业务 API 的写权限。

响应：

```json
{
  "draft_id": "act_01",
  "status": "executed",
  "result": {
    "resource_type": "notification",
    "resource_id": 501,
    "page_target": "notifications-view"
  },
  "executed_at": "2026-07-18T21:30:00+08:00"
}
```

重复确认返回 HTTP 409；过期草稿返回 HTTP 410；越权返回 403 或不暴露资源存在性的 404。

## 11. 管理员质量运营 API

### 11.1 `GET /api/assistant/operations/quality`

权限：仅平台管理员。

查询参数：

```text
start=2026-07-11T00:00:00+08:00
end=2026-07-18T23:59:59+08:00
role=teacher
answer_type=nl2sql
```

首版响应指标：

- 查询总数。
- 成功、澄清、拒绝、失败和降级数量。
- P50/P95 总响应时间。
- 路由、检索、模型、校验、执行各阶段失败数量。
- local/server 检索使用率和降级率。
- 低置信和负反馈数量。
- 越权问题拒绝数量。
- 待治理项数量。

隐私限制：

- 默认不返回完整问题正文。
- 高频问题使用脱敏归一化文本或分类标签。
- 不返回 SQL 结果行、作业正文、私密答疑和辅导记录。

## 12. HTTP 状态与错误码

### 12.1 HTTP 状态

| HTTP | 场景 |
|---:|---|
| 200 | 查询成功、澄清、权限词前置拒绝、可控执行失败或降级完成 |
| 201 | 创建会话成功 |
| 204 | 删除会话成功且无需响应体 |
| 400 | 语义上非法的请求组合 |
| 401 | 未登录、token 无效、会话版本失效 |
| 403 | 当前身份明确无页面、指标或动作权限 |
| 404 | 资源不存在，或为避免越权枚举而隐藏存在性 |
| 409 | 状态冲突、重复动作确认、会话不可继续 |
| 410 | 动作草稿已过期 |
| 413 | 请求或导出体积超过限制 |
| 422 | Pydantic 参数校验失败 |
| 429 | 超过问数或动作频率限制 |
| 500 | 未被结构化处理的服务端缺陷；正常模型失败不应使用 500 |

### 12.2 业务错误码

| 错误码 | 含义 | 可重试 |
|---|---|---:|
| `ASSISTANT_UNSUPPORTED` | 当前问题类型不支持 | 否 |
| `ASSISTANT_NEEDS_CLARIFICATION` | 需要补充信息 | 否 |
| `ASSISTANT_SCOPE_REJECTED` | 问题或上下文超出授权范围 | 否 |
| `ASSISTANT_METRIC_UNAVAILABLE` | 指标暂不可用 | 视情况 |
| `ASSISTANT_ROUTER_UNAVAILABLE` | 意图路由不可用 | 是 |
| `ASSISTANT_RETRIEVAL_UNAVAILABLE` | 检索不可用且无法完成 | 是 |
| `ASSISTANT_LLM_UNAVAILABLE` | 模型不可用 | 是 |
| `ASSISTANT_SQL_REJECTED` | SQL 未通过安全校验 | 否或改写问题 |
| `ASSISTANT_SQL_EXECUTION_FAILED` | 只读执行失败 | 是 |
| `ASSISTANT_KNOWLEDGE_UNAVAILABLE` | 制度知识源不可用 | 是 |
| `ACTION_DRAFT_EXPIRED` | 动作草稿过期 | 否，需重新生成 |
| `ACTION_DRAFT_CONFLICT` | 草稿已执行或状态冲突 | 否 |

普通用户错误消息不得包含堆栈、内部主机、数据库 URL、Prompt 或密钥。详细异常只进入服务端日志和脱敏执行追踪。

## 13. 请求限制

首版限制：

| 项目 | 限制 |
|---|---:|
| 问题长度 | 500 字符 |
| 页面筛选序列化大小 | 4 KB |
| 会话标题 | 100 字符 |
| 单页会话数 | 最大 100 |
| 单页轮次数 | 最大 100 |
| 反馈说明 | 1000 字符 |
| SQL 结果行数 | 不超过服务端 `MAX_ROWS` |
| 动作草稿默认有效期 | 30 分钟 |

实际实现可以选择更小限制；扩大限制需要评估 Prompt 注入、资源消耗和隐私风险。

## 14. `/api/ask` 兼容策略

### 14.1 V3 首版

- 保留 `POST /api/ask`。
- 保留当前 `AskRequest` 和 `AskResponse` 字段语义。
- 现有智能问数页面在迁移完成前可以继续调用旧接口。
- `/api/assistant/query` 的 `nl2sql` 分支复用 `app.service.ask()`，不复制另一套 SQL 生成和安全校验。
- 新接口负责上下文、会话、意图编排、证据和动作；旧服务继续负责 NL2SQL 核心链路。

### 14.2 前端迁移顺序

1. 先实现统一助手 API，但不删除旧接口。
2. 接入课程空间和教师/学生场景。
3. 接入辅导员、学院和教务。
4. 迁移独立智能问数页面。
5. 完成回归后再评估 `/api/ask` 是否标记 deprecated。

### 14.3 禁止事项

- 不允许为新助手复制一套弱化版 SQL 校验器。
- 不允许新接口绕过现有角色、字段和行级范围。
- 不允许在旧页面尚未迁移时删除 `/api/ask`。
- 不允许把旧前端传来的历史直接视为可信服务端会话。

## 15. 数据保留与隐私

### 15.1 会话可保存

- 用户问题。
- 回答摘要。
- 回答类型和状态。
- 生效上下文摘要。
- 指标代码。
- SQL 元数据和安全执行追踪。
- 用户反馈。

### 15.2 默认不保存

- 作业附件正文。
- 私密答疑全文。
- 辅导员内部跟进正文。
- 数据库完整结果集。
- 模型密钥、数据库密码和内部连接地址。
- 未经脱敏的敏感字段。

### 15.3 角色切换

- 会话绑定创建时的角色绑定 ID。
- 切换角色后旧会话不出现在列表中。
- 旧角色绑定失效后不能继续读取或提交。
- 旧角色动作草稿立即失效。

## 16. 测试契约

后续实现至少需要以下测试文件或等价覆盖：

```text
tests/test_v3_assistant_context.py
tests/test_v3_assistant_sessions.py
tests/test_v3_assistant_orchestrator.py
tests/test_v3_semantic_metrics.py
tests/test_v3_answer_evidence.py
tests/test_v3_action_drafts.py
tests/test_v3_assistant_role_integration.py
tests/test_v3_assistant_quality.py
```

必测矩阵：

- 未登录。
- token 伪造或会话版本失效。
- 当前角色允许页面。
- 当前角色禁止页面。
- 本人课程与其他教师课程。
- 本人学生数据与其他学生数据。
- 本人带班与非带班学生。
- 本学院与其他学院。
- 空权限角色。
- 切换角色后的旧会话。
- 过期、重复和篡改动作草稿。
- 模型、检索、SQL 和知识源失败。
- local/server 检索降级。
- 旧 `/api/ask` 回归。

## 17. 契约验收结果

V3-0.2 完成定义：

- 统一助手入口与配套端点已经确定。
- 请求、响应和稳定字段已经确定。
- 页面上下文和服务端复核语义已经确定。
- 会话与工作身份隔离规则已经确定。
- 回答状态、类型和错误语义已经确定。
- 动作草稿白名单和确认流程已经确定。
- `/api/ask` 兼容策略已经确定。
- 测试矩阵已经确定。

本契约冻结后，下一步应执行 **V3-0.3：建立 V3 增量迁移基础**，然后进入 **V3-1.1：页面上下文与权限复核**。
