# V3-1.3 统一问题编排器完成报告

> 完成日期：2026-07-18
> 阶段状态：已完成
> V3-1 阶段门禁：已通过
> 下一任务：V3-2.1 认证指标语义层

## 1. 统一入口

新增 `POST /api/assistant/query`，请求使用 V3-0.2 冻结的页面上下文和查询选项，响应统一包含：

- 会话 ID、轮次 ID、状态和回答类型。
- 回答、结构化数据和可选 SQL。
- 当前角色与验证后的对象范围。
- 时间范围、证据、warning、置信度和安全 trace。
- 建议问题、建议动作、结构化错误或澄清信息。

未提供 `session_id` 时自动创建当前工作身份会话；提供时只允许续用当前 `user_id + role_binding_id` 且页面一致的未删除会话。每次回答都会保存安全轮次摘要。

## 2. 首版路由

编排器按以下顺序工作：

| 路由 | 处理方式 |
|---|---|
| `metric` | 从当前角色范围化工作台读取固定计数，不调用模型 |
| `business_state` | 返回当前身份工作台待办和状态摘要，不展示其他身份内容 |
| `navigation` | 只从服务端授权导航中选择目标页面 |
| `nl2sql` | 调用现有 `app.service.ask()`，保留表、字段、行级权限及只读 SQL 链路 |
| `unsupported` | 明确说明当前助手范围并给出可用问法，不伪造答案 |

具体课程、学生或学院上下文存在时，计数问题不会使用全范围工作台捷径，而是进入可落实对象范围的 NL2SQL 路径。

## 3. 权限与兼容

- 请求首先经过 V3-1.1 页面、账号、角色绑定和资源关系复核；无权上下文返回 HTTP 403，不调用模型。
- 验证后的 `teaching_class_id`、`student_id`、`college_id` 与原 `AuthContext.row_scope` 合并后传入 SQL validator。
- 扩展了 SQL validator 对课程上下文的强制条件，覆盖课程、选课、作业、考勤、学习活动和分析汇总表。
- 修复未带别名的 `assignment` 表被 sqlparse 识别为关键字后跳过直接表引用识别的问题。
- 普通角色只能获得安全 trace 摘要；管理员显式设置 `include_trace=true` 后可读取治理 trace。
- `include_sql=false` 只隐藏 SQL，`max_rows` 只能进一步收紧结果。
- 原 `POST /api/ask` 请求和响应保持兼容。

## 4. 会话 API

V3-1.2 内部服务现已开放为受认证 API：

```text
GET    /api/assistant/sessions
POST   /api/assistant/sessions
GET    /api/assistant/sessions/{session_id}
PATCH  /api/assistant/sessions/{session_id}
DELETE /api/assistant/sessions/{session_id}
```

跨用户或跨工作身份读取统一返回 404。当前运行时 API 总数从 129 增加到 135。

## 5. 错误隔离

模型、检索、SQL 或编排器异常统一转换为：

```json
{
  "status": "failed",
  "error": {
    "code": "ASSISTANT_INTERNAL_ERROR",
    "message": "智能助手暂时不可用，请稍后重试。",
    "retryable": true
  }
}
```

失败仍会以安全摘要保存轮次，但不会抛出未处理异常。助手分支失败不会影响工作台等基础业务接口。

## 6. 测试结果

新增 10 项测试，覆盖：

1. 固定指标路由。
2. 业务状态路由。
3. 授权页面导航。
4. 不支持问题。
5. NL2SQL 旧响应转换、结果收紧和 SQL 隐藏。
6. 页面课程上下文传递到 SQL 行范围。
7. 伪造课程在调用模型前返回 403。
8. 编排异常结构化失败且工作台继续可用。
9. 旧 `/api/ask` 兼容。
10. 会话 HTTP API 身份隔离及查询轮次写入。

助手、旧问数与安全联合回归：

```text
53 passed, 2 warnings in 12.67s
```

完整回归：

```text
197 passed, 2 warnings in 153.02s
```

两个 warning 仍为既有 Starlette TestClient/httpx 和 `langchain-community` 弃用提醒，本阶段没有新增 warning。

## 7. 明确边界

- 前端尚未调用统一助手和服务端会话 API，当前网页继续使用 `/api/ask` 和浏览器本地历史。
- 保存的轮次尚未恢复为 NL2SQL 多轮 SQL 历史；当前续用会话主要提供身份隔离持久化和审计基础。
- 当前 `metric` 是已有工作台固定计数，不是 V3-2.1 的版本化认证指标。
- `knowledge`、`hybrid`、证据卡片、动作草稿和质量运营能力尚未实现。
- 当前为非流式响应，不包含运行中任务恢复。

V3-1.1 上下文越权、V3-1.2 身份隔离会话和 V3-1.3 统一助手 API 测试均已通过，阶段 V3-1 门禁已满足。
