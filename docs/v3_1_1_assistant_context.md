# V3-1.1 页面上下文与权限复核完成报告

> 完成日期：2026-07-18
> 阶段状态：已完成
> 下一任务：V3-1.2 服务端会话与消息

## 1. 交付范围

新增 `app/core/assistant_context.py`，实现冻结契约中的页面上下文模型与服务端权限求交：

- `AssistantPageContext`：页面、课程、学生、学院、学年、学期、时间范围和筛选条件。
- `AssistantTimeRange`：要求开始和结束时间包含时区，并校验先后顺序。
- `resolve_assistant_context(auth, request_context)`：输出最终生效上下文、忽略字段和拒绝字段。
- `AssistantContextAuthorizationError`：在无权上下文中携带被拒绝的客户端字段，供后续 API 转换为 HTTP 403。

本任务没有提前实现 `/api/assistant/query`，也没有修改当前 `/api/ask` 行为。

## 2. 页面和权限规则

首版页面标识与 V3-0.2 契约一致，共 12 个：

```text
dashboard, assistant, course_space, assignment_workflow,
attendance, course_analytics, support_workbench, teaching_operations,
notifications, governance, data_access, profile
```

每个页面先映射到现有 `AuthContext.features`。当前身份没有对应功能时直接拒绝，不继续查询资源或进入后续助手链路。

对象范围按以下规则重新核验：

| 上下文 | 服务端核验 |
|---|---|
| 课程 | 学生必须已选课；教师必须是实际任课人；学院负责人只能使用本学院课程；教务和管理员只能使用真实存在的课程 |
| 学生 | 学生只能使用本人 ID；辅导员只能使用被分配行政班中的学生；管理员可以使用真实存在的学生；其他角色不获得学生上下文权限 |
| 学院 | 学院负责人只能使用本学院；教师、学生和辅导员只能使用本人所属学院；教务和管理员可以选择真实学院 |
| 组合 | 学院必须与课程或学生一致；同时提供课程和学生时，学生必须实际选修该课程 |

账号状态、`session_version`、当前 `role_binding_id`、角色、绑定有效期和岗位有效期也会在解析时重新确认。角色切换使旧会话版本失效，因此旧页面上下文不能借旧 `AuthContext` 继续使用。

## 3. 输入安全和数据最小化

- `filters` 序列化后最大 4 KB、最多 50 个顶层字段，字段名使用受限格式。
- 筛选条件任意层级出现 `allowed_tables`、`role`、`student_id`、`college_id`、`teaching_class_id` 等身份或权限字段都会被拒绝。
- 页面不使用的字段进入 `ignored_fields`，不会因为提交一个无关 ID 而改变权限。
- 数据库核验读取的 `teacher_id`、`class_id` 等内部关系不放入 `effective_context`。
- 解析结果持有原始 `AuthContext`，不复制或扩展 `allowed_tables`、`denied_columns`、`features` 或 `row_scope`。

## 4. 测试结果

新增 8 项测试，覆盖方案要求的六类必测场景和输入边界：

1. 教师使用本人课程。
2. 教师伪造其他教师课程。
3. 学生伪造其他学生 ID。
4. 辅导员伪造非带班学生。
5. 学院负责人伪造其他学院。
6. 切换角色后复用旧页面上下文和旧身份。
7. 页面无关字段忽略及筛选条件权限字段拦截。
8. 时间范围和 4 KB 筛选上限。

专项与既有角色权限联合回归：

```text
19 passed, 2 warnings in 6.61s
```

完整回归：

```text
181 passed, 2 warnings in 121.78s
```

两个 warning 仍是既有 Starlette TestClient/httpx 和 `langchain-community` 弃用提醒，本任务没有新增 warning。

## 5. 完成结论与边界

V3-1.1 的模型、权限求交、角色切换失效和必测越权场景均已完成，可以进入 V3-1.2。

当前能力属于后端基础组件，尚无独立 API 或前端调用入口。下一阶段应使用 V3-0.3 迁移机制建立服务端会话和消息表，并将会话严格绑定到 `user_id + role_binding_id`。
