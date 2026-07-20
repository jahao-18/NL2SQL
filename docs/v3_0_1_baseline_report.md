# V3-0.1 当前基线复核报告

> 任务编号：V3-0.1
> 执行日期：2026-07-18
> 任务状态：已完成
> 基线性质：对当前工作树的只读验证与文档审计，不代表 V3 新功能已经实现。

## 1. 复核结论

当前项目满足进入 V3-0.2 接口契约设计的质量条件：

- Python 编译检查通过。
- 完整自动化测试为 **168 passed**。
- 阶段 F 六角色独立回归为 **22 passed**。
- local 检索完整模式成功使用 `vector / keyword / graph`。
- local 检索在外部模型不可用时能够降级为 `keyword / graph`。
- server 检索模式成功使用 `vector / keyword / glossary / graph` 四路真实组件。
- Docker 中 Elasticsearch、Milvus、etcd、MinIO、PostgreSQL/pgvector 均为 healthy。
- 运行时 **129 个 API** 与功能目录 API 清单完全一致。
- 运行时 **10 个角色** 与功能目录角色表完全一致。
- 发现并修正文档页面表中漏记 `notifications-view` 的维护问题。

本任务未修改 V3 产品代码、API 或数据模型。

## 2. 执行环境

仓库自带 `.venv` 当前不可用，其解释器仍指向不存在的 `D:\miniconda\python.exe`。系统默认 `python` 来自另一目录的虚拟环境，并缺少 pytest。

为避免覆盖用户现有环境，本次在仓库忽略目录中建立隔离测试环境：

```text
.tmp/v3-baseline-venv
```

关键版本：

| 组件 | 版本 |
|---|---:|
| Python | 3.12.3 |
| FastAPI | 0.139.2 |
| pytest | 9.1.1 |
| Uvicorn | 0.51.0 |

临时环境安装的是仓库当前 `requirements.txt` 声明的完整依赖，包括 local/server 检索客户端。该环境不进入版本控制。

## 3. 编译与自动化测试

### 3.1 Python 编译检查

执行：

```powershell
.\.tmp\v3-baseline-venv\Scripts\python.exe -m compileall -q app tests scripts
```

结果：通过，无语法错误。

### 3.2 完整测试

执行：

```powershell
.\.tmp\v3-baseline-venv\Scripts\python.exe -m pytest -q
```

结果：

```text
168 passed, 2 warnings in 182.86s
```

警告：

1. Starlette 提示当前 `TestClient` 使用的 httpx 集成即将弃用，后续依赖升级需要迁移到新版测试客户端方案。
2. `langchain-community` 提示进入 sunset 阶段，通义模型集成后续应迁移到独立维护包。

两条均为依赖演进警告，不影响当前测试结果，但应进入技术债务待办。

### 3.3 阶段 F 六角色回归

执行：

```powershell
.\.tmp\v3-baseline-venv\Scripts\python.exe scripts\run_stage_f_regression.py --verbose
```

结果：

```text
22 passed, 2 warnings in 28.76s
```

覆盖内容：

- 学生、教师、辅导员、学院、教务、管理员菜单与会话字段。
- 六角色关键 API 允许/拒绝矩阵。
- 未登录 API 拒绝。
- 通知安全跳转。
- 课程空间、作业、考勤、答疑、学生支持和成绩审批链路。
- 临时数据库隔离。

回归脚本确认未写入共享 `data/teaching.db`。

## 4. 检索模式复核

### 4.1 local 模式完整链路

执行方式：

```powershell
$env:RETRIEVAL_BACKEND='local'
.\.tmp\v3-baseline-venv\Scripts\python.exe -m scripts.verify_server_backend teaching '统计各学院当前开设的教学班数量'
```

结果：

```text
retrievers_used = ['vector', 'keyword', 'graph']
```

同时确认：

- 639 个 Schema 原子完成向量索引。
- BM25 索引完成。
- 62 张表、83 条外键边完成关系图构建。
- 查询扩展调用成功。
- 问题成功召回 `teaching_class`、学院运行汇总等相关表。

### 4.2 local 模式外部服务故障降级

在沙箱代理阻断 DashScope 时，同一验证仍成功返回：

```text
retrievers_used = ['keyword', 'graph']
```

向量检索和查询扩展失败会写入日志，但检索管线回退到可用路径，没有终止进程。该行为与项目当前降级设计一致。

### 4.3 server 模式四路检索

Docker 状态：

| 服务 | 状态 |
|---|---|
| Elasticsearch + IK | healthy |
| Milvus | healthy |
| etcd | healthy |
| MinIO | healthy |
| PostgreSQL/pgvector | healthy |

执行方式：

```powershell
$env:RETRIEVAL_BACKEND='server'
.\.tmp\v3-baseline-venv\Scripts\python.exe -m scripts.verify_server_backend teaching '统计各学院当前开设的教学班数量'
```

结果：

```text
retrievers_used = ['vector', 'keyword', 'glossary', 'graph']
```

确认：

- Milvus 成功重建 639 个原子索引。
- Elasticsearch 成功重建教学索引。
- pgvector 术语索引缓存命中 44 条术语。
- 关系图成功参与融合。
- 查询返回 5 条术语召回结果。

## 5. API、页面与角色目录审计

审计来源：

- FastAPI `app.openapi()` 运行时路由。
- `docs/project_feature_catalog.md` API 表。
- `app/static/index.html` 中的 `work-view`。
- `app.core.business_domains.ROLES`。

### 5.1 API

| 项目 | 数量 |
|---|---:|
| 运行时 API | 129 |
| 功能目录 API | 129 |
| 运行时存在但目录缺失 | 0 |
| 目录存在但运行时缺失 | 0 |

结论：API 清单一致。

### 5.2 角色

运行时与目录均包含以下 10 个角色/状态身份：

```text
academic_office
admin
college_manager
counselor
identity_reviewer
pending
self_service
staff
student
teacher
```

结论：角色清单一致。

### 5.3 页面

| 项目 | 数量 |
|---|---:|
| 运行时 `work-view` | 19 |
| 审计前功能目录页面项 | 18 |
| 漏记页面 | `notifications-view` |

`notifications-view` 已有完整后端与前端实现，只是功能目录页面表漏记。本任务已在 `docs/project_feature_catalog.md` 补充该页面，并更新核对日期与变更记录。修正后页面清单一致。

## 6. 当前智能问数响应基线

当前主接口：

```text
POST /api/ask
```

请求特征：

- 使用 `X-Demo-Token` 认证。
- 历史由前端持有并随请求发送。
- 非管理员固定查询 `teaching` 数据源。
- 后端注入角色行级范围和“本学期”口径。
- 问数失败通常使用 HTTP 200 返回结构化 `error`；认证、授权、参数和数据源错误使用相应 HTTP 状态码。

### 6.1 成功

关键字段：

```json
{
  "sql": "SELECT ...",
  "columns": ["n"],
  "rows": [[2]],
  "row_count": 1,
  "elapsed_ms": 3,
  "truncated": false,
  "error": null,
  "clarify": null,
  "source": "teaching",
  "explanation": {},
  "trace": {}
}
```

### 6.2 澄清

```json
{
  "sql": null,
  "rows": [],
  "error": null,
  "clarify": "请说明要查询的学期。"
}
```

### 6.3 权限前置拒绝

```json
{
  "sql": null,
  "rows": [],
  "error": "当前身份无权查询相关数据。",
  "clarify": null
}
```

### 6.4 模型或执行失败

```json
{
  "sql": null,
  "rows": [],
  "error": "LLM 调用失败: ...",
  "clarify": null
}
```

### 6.5 回修

`tests/test_ask_regression.py` 已确认：初次 SQL 缺少必要行范围时，不会执行不安全 SQL；系统回修后只执行带正确范围条件的 SQL。

## 7. 已知问题与技术债务

### 7.1 阻断性问题

当前没有阻断 V3-0.2 契约设计的问题。

### 7.2 需要后续处理

1. **仓库 `.venv` 失效。** README 推荐命令无法直接在当前本机环境执行，应在后续环境维护任务中重建，但不在 V3-0.1 中修改。
2. **检索验证脚本直接运行失败。** `python scripts/verify_server_backend.py` 会出现 `ModuleNotFoundError: app`；使用 `python -m scripts.verify_server_backend` 可以运行。后续应修正脚本入口或 README 命令。
3. **pytest 默认收集范围过宽。** 仓库没有明确 pytest 收集目录时，根目录下无权限临时目录可能阻断收集。后续建议增加 pytest 配置，将 `testpaths` 固定为 `tests`。
4. **依赖弃用警告。** Starlette TestClient/httpx 和 langchain-community 需要单独升级评估。
5. **健康接口信息有限。** `/api/health` 当前只检查教学数据库、DashScope Key 是否配置和预热开关，不检查 ES、Milvus、pgvector、最近索引状态或模型可达性。
6. **local 完整检索依赖外部网络。** 外部 embedding/查询扩展不可用时可以降级，但质量和延迟会变化。
7. **当前 `/api/ask` 无服务端会话。** 历史、用户术语和部分偏好由前端持有，这是 V3-1.2 的建设对象。

## 8. 工作树说明

执行 V3-0.1 前仓库已经存在多项未提交修改，包括检索、数据源、README、测试和教学数据库变更。本次基线针对**当前工作树整体状态**，未将这些修改归因于 V3。

V3-0.1 新增或修改的受控文档：

- 新增本基线报告。
- 修正 `docs/project_feature_catalog.md` 中遗漏的通知中心页面。
- 在 `docs/next_iteration_v3_plan.md` 标记 V3-0.1 已完成。

## 9. 阶段结论

V3-0.1 完成定义已满足：

- 当前测试基线已经得到真实复核。
- 六角色产品链路可重复运行。
- local/server 检索及降级行为已经验证。
- 智能问数成功、澄清、回修、拒绝和失败响应已经核对。
- API、页面和角色目录已经完成反查。
- 已知问题已经形成清单。

可以进入 V3-0.2 接口契约冻结。
