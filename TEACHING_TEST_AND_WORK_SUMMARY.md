
> 整理日期：2026-07-15  
> 整理范围：默认教学数据源 `teaching` 的环境、功能、权限、安全、智能问数、教学驾驶舱、治理和浏览器验收。  

## 一、当前结论

当前项目已经达到默认教学库课程演示和测试交付要求：

- FastAPI 服务、静态前端、SQLite 教学库和 DashScope/Qwen 模型能够实际运行。
- 管理员、教务处、学院负责人、教师、学生五种角色可以登录并按权限使用系统。
- 中文问题可以经过数据源路由、Schema 检索、SQL 生成、安全校验、只读执行和异步可信度评估返回结果。
- 学生、教师、学院的账号级数据范围已从提示词约束升级为执行前强制校验。
- 教学驾驶舱支持五角色数据范围和学期、学院、专业、课程类型筛选；学院开课数已按课程所属学院统计。
- 认证、管理接口和数据维护接口的主要越权风险已完成最小修正。
- 当前自动化测试为 `97 passed`；教学真实评测8/8、驾驶舱矩阵、真实HTTP和浏览器人工主验收均已完成。

项目仍不是生产级系统：演示账号、外部模型随机性、BIRD数据缺失、并发压力、生产部署和长期稳定性不在当前已验收范围内。

## 二、项目解决的问题与当前功能

### 2.1 面向的问题

项目主要解决教学管理人员或师生不会编写SQL，但需要从多张教学业务表中获取数据的问题。系统通过自然语言问数减少人工编写连接、筛选和聚合SQL的成本，同时用权限和只读执行降低误操作风险。

### 2.2 教学业务数据

默认 `data/teaching.db` 覆盖17张业务表，主要包括：

- 学院、专业、行政班、学生和教师。
- 课程、开课班、选课和成绩。
- 作业、提交、考勤、学习活动和教学评价。
- 奖学金和学业预警。

### 2.3 当前功能模块

| 模块 | 当前能力 | 主要文件 |
|---|---|---|
| 服务与前端 | FastAPI API、Swagger、原生HTML/CSS/JavaScript工作台 | `app/main.py`、`app/static/` |
| 智能问数 | 数据源选择、检索、SQL生成、失败修复、执行、结果解释 | `app/service.py`、`app/core/chain.py` |
| Schema增强 | DDL、业务词表、画像、枚举、关系和多路检索 | `app/core/schema.py`、`app/core/retrieval/`、`data/glossaries/`、`data/schema_profiles/` |
| SQL安全 | 只读校验、授权表/字段、账号范围、行数限制和超时 | `app/core/validator.py`、`app/core/executor.py` |
| 五角色权限 | 认证、业务域、允许表、禁用字段和行级范围 | `app/core/business_domains.py`、`app/api/routes.py` |
| 教学驾驶舱 | 五角色统计卡片、图表和四类筛选 | `app/core/teaching_dashboard.py`、`app/static/app.js` |
| 可信度评估 | 后台异步裁判、分项得分和低可信治理入口 | `app/core/judge.py`、`prompts/judge_prompt.txt` |
| 知识治理 | Schema画像、质量、版本发布/回滚、反馈、示例和复核队列 | `app/core/schema_profile.py`、`app/api/governance.py` |
| 数据维护 | 数据源查看、扫描、分页、受控增删改和审计 | `app/api/data_access.py`、`app/core/data_access.py` |
| 自动评测 | YAML用例、标准SQL结果比较、真实模型评测 | `scripts/eval.py`、`tests/teaching_eval_cases.yaml` |

## 三、B 同学职责与本轮实际成果

按照任务分工，B同学负责测试优化和功能辅助。本轮成果与职责对应如下：

| B同学职责 | 本轮完成内容 | 可核验证据 |
|---|---|---|
| 功能测试 | 环境、服务、认证、API、五角色、驾驶舱、治理、数据维护和浏览器验收 | `PROJECT_CHANGES.md`、`PROJECT_PROGRESS.md` |
| 智能问数测试 | 8条教学评测、多轮追问、澄清、SQL修复、角色问题、常见和冷门问题 | `tests/teaching_eval_cases.yaml`、CHG-20260714/15记录 |
| SQL安全测试 | 只读、多语句、危险语句、未授权表、敏感字段、账号范围、200行和超时 | `tests/test_role_permissions.py`及实际运行记录 |
| 整理测试用例 | 自动化测试从原始8项扩展到当前97项；教学评测脚本支持真实结果比较 | `tests/`、`scripts/eval.py` |
| 优化问数样例/提示词 | 修正专业枚举检索和教师零授课保留口径；裁判理解强制角色范围 | `app/core/retrieval/atoms.py`、`prompts/sql_prompt.txt`、`prompts/judge_prompt.txt` |
| 页面细节 | 驾驶舱筛选、专业开课口径提示、角色切换清理、静态缓存版本 | `app/static/app.js`、`app/static/index.html` |
| 协助修复Bug | 按实际失败证据完成认证、授权、数据维护、行级范围、评测、驾驶舱等最小修正 | `PROJECT_ISSUES.md`、`PROJECT_CHANGES.md` |

本轮没有把原始项目主体功能记为B同学新增。原始后端、前端、教学库、检索、治理和数据维护框架均属于原项目范围；本轮责任是发现、复现、最小修正和验证。

## 四、测试原则与环境

### 4.1 证据原则

- 实际运行结果：pytest、Uvicorn、HTTP、浏览器、SQLite或真实Qwen调用得到的结果。
- 源码直接证据：可说明实现和调用链，但不单独写成已发生运行故障。
- 未验证内容：明确标记，不以推测写成已通过或已修复。

### 4.2 测试环境

| 项目 | 当前状态 |
|---|---|
| 操作系统 | Windows，本地开发环境 |
| Python环境 | 项目 `.venv`，按 `requirements.txt` 安装 |
| Web服务 | Uvicorn + FastAPI，`127.0.0.1:8000` |
| 默认数据库 | SQLite `data/teaching.db` |
| 模型 | `.env`配置的DashScope/Qwen生成模型和裁判模型 |
| 检索 | local模式：向量、BM25、关系图 |
| 自动化 | pytest，使用独立`--basetemp`规避旧Windows临时缓存权限问题 |
| 浏览器 | 本地浏览器开发者工具、Network和Local Storage人工验收 |

真实密钥没有写入测试、记录或提交文件。

## 五、自动化测试现状

最后一次完整pytest实际结果为：

```text
97 passed, 4 warnings in 25.38s
```

四条警告为既有TestClient/httpx、LangChain Community和FastAPI `on_event`弃用提示，不影响当前运行。

### 5.1 测试数量分布

| 测试文件 | 收集数量 | 覆盖重点 |
|---|---:|---|
| `tests/test_authentication.py` | 35 | 认证、管理功能授权、反馈/示例、治理权限和静态入口 |
| `tests/test_data_access_permissions.py` | 9 | 数据源脱敏、表/字段/行范围、受控增删改和审计 |
| `tests/test_eval_runner.py` | 6 | YAML继承、数值规整、正确/错误结果和截断判断 |
| `tests/test_governance.py` | 3 | 自动入队、发布审批顺序、低可信阈值 |
| `tests/test_judge_scope.py` | 4 | 裁判强制账号范围和后台传递 |
| `tests/test_retrieval_context.py` | 1 | 专业枚举进入检索上下文 |
| `tests/test_role_permissions.py` | 11 | 未授权表/字段、星号、学生/教师/学院范围和OR绕过 |
| `tests/test_teaching_dashboard.py` | 28 | 认证、五角色、数据库真值、筛选正反面和边界 |
| 合计 | 97 | 当前教学库主要确定性行为 |

原始基线为7项通过、1项失败。当前97/97不代表原项目原本已有97项测试，而是本轮增加隔离、权限、评测和驾驶舱覆盖并修正原失败后的结果。

## 六、正面测试

| 类别 | 实际用例 | 结果 |
|---|---|---|
| 服务启动 | 应用导入、健康接口、Uvicorn、本地前端 | 通过 |
| 教学问数 | 8条教学问题真实模型评测 | 最终8/8通过 |
| 多轮对话 | 学院平均分→计算机学院→挂科率→按课程拆分 | 历史条件保持并执行成功 |
| 歧义澄清 | “哪个学院最好？”后补充“按平均成绩” | 能先澄清再查询 |
| 角色合法查询 | 学生本人、教师本人授课、学院本院统计 | 修改后均带正确账号范围并返回结果 |
| 教师完整统计 | 每位教师授课班和选课人次 | 使用左连接保留零授课教师 |
| 驾驶舱 | 五角色基础卡片与独立SQLite真值 | 专项28/28通过 |
| 学院筛选 | 2025春季计算机学院开课 | 修正后为21，与独立SQL一致 |
| 浏览器 | 五角色登录、驾驶舱、问数、切换和Network | 人工主验收完成 |
| 冷门问题 | 高风险未解除考勤预警数 | 返回104，独立SQL一致，可信度96 |

## 七、反面测试

| 类别 | 输入或行为 | 实际结果 |
|---|---|---|
| 无效认证 | 缺失、空白、未知令牌 | HTTP 401，不再回退管理员 |
| 功能越权 | 学生读取Profile、质量、版本或治理设置 | HTTP 403，存储函数不被调用 |
| 匿名写入 | 无令牌新增/删除反馈和示例 | 请求在存储前被拒绝 |
| 未授权表 | 角色SQL连接无权表 | 校验拒绝 |
| 敏感字段 | 输出学生/教师身份字段或`SELECT *`包含禁用列 | 校验拒绝 |
| 范围缺失 | 学生生成全局聚合 | 执行前拒绝并进入修复链 |
| OR绕过 | 一支带范围、另一支无范围 | 校验拒绝 |
| 数据维护越权 | 教师读取/修改学生全表、学院跨院修改 | API和SQL事务内拒绝 |
| 危险SQL | `DELETE`、`PRAGMA`、多语句 | 只读校验拒绝 |
| 不存在筛选 | 驾驶舱不存在学院/课程类型/学期 | 返回空统计或明确400，不扩大角色范围 |

## 八、边界测试

| 边界 | 实际结果与说明 |
|---|---|
| 200行上限 | 超过上限时结果被限制并标记`truncated`，不把截断结果误判为完整结果 |
| 查询超时 | 递归查询约1秒被中断，执行器超时生效 |
| 0值结果 | 软件工程满分人数真实为0；同题三轮裁判92～93，首次曾偶发33 |
| 空结果 | 评测器能区分正确空集和错误空集，不再只检查SQL关键词 |
| 数值类型 | 标准答案`1`与预测`1.0`按数值等价比较 |
| 多轮上限 | 前端仅发送最近配置轮数，避免历史无限增长 |
| 固定角色范围 | 学生、教师、学院筛选不能越过账号绑定范围 |
| 专业开课口径 | 当前库没有专业—课程关系；卡片明确说明按专业学生选课覆盖统计，不伪造专业归属值 |
| 裁判波动 | 首次33分未稳定复现；同题三轮92～93、冷门题96，记录为非阻塞模型波动 |
| 静态缓存 | 主脚本更新为`p0-product-4`，入口测试和真实HTTP确认浏览器可取得新逻辑 |

## 九、主要问题与最小修正

| 问题范围 | 已完成修正 | 主要文件 |
|---|---|---|
| 评测不可用/比较不准确 | 顶层数据源继承、标准SQL结果比较、数值规整、截断检查 | `scripts/eval.py`、`tests/test_eval_runner.py` |
| 无效令牌成为管理员 | 删除管理员回退，统一401 | `app/core/business_domains.py`、`app/main.py` |
| 管理接口缺少后端授权 | Profile、版本、质量、治理、反馈和示例按feature授权 | `app/api/routes.py`、`app/api/governance.py` |
| 数据维护越权 | 数据源脱敏、允许表/字段和直接账号范围双层强制 | `app/api/data_access.py`、`app/core/data_access.py` |
| 行级范围仅靠Prompt | SQL生成后、执行前强制验证，OR分支不能绕过 | `app/core/validator.py`、`app/service.py` |
| 专业枚举丢失 | 检索枚举上限与完整Schema对齐 | `app/core/retrieval/atoms.py` |
| 裁判误解合法账号范围 | 单独传递可信角色和强制范围上下文 | `app/core/judge.py`、`prompts/judge_prompt.txt` |
| 教师零授课遗漏 | 教师统计使用主表左连接 | `prompts/sql_prompt.txt` |
| 驾驶舱筛选/学院口径 | 固定角色筛选、独立真值测试、学院按课程归属 | `app/core/teaching_dashboard.py` |
| 角色切换页面残留 | 统一清理输入、SQL、结果、进度和本地会话 | `app/static/app.js` |
| 学生多余403 | 无knowledge feature时不请求质量和版本 | `app/static/app.js` |
| 浏览器旧脚本 | 更新静态版本并增加入口测试 | `app/static/index.html`、`tests/test_authentication.py` |

每次修正的修改前证据、函数级变化、测试断言、验证结果和回退范围详见 `PROJECT_CHANGES.md`。

## 十、当前遗留与不扩展范围

### 10.1 后续必须处理

- BIRD小规模测试：本地尚无 `data/bird/`、dev JSON和数据库。取得数据后只选一个库、5～10题测试加载、检索、SQL、执行和结果比较。

### 10.2 已知但当前不阻塞

- ISSUE-004：通用电商评测依赖的 `data/app.db` / `demo_sqlite` 未确认。
- ISSUE-005：FastAPI、LangChain和TestClient弃用警告。
- ISSUE-010：未下载的BIRD源仍会被配置暴露并产生Schema 500；教学库主流程不受影响。
- ISSUE-011：数据维护前端部分异步失败缺少统一提示。
- 专业—课程归属关系不存在，无法统计培养方案意义的专业开课数。
- 可信度裁判依赖外部模型，存在偶发假阴性，不能作为权限或正确性的唯一保证。

### 10.3 未验证、不得写成已通过

- 生产部署、HTTPS、真实账号体系和密钥管理。
- 高并发、压力、长时间稳定性和故障恢复。
- PostgreSQL以及Milvus、Elasticsearch、pgvector的真实server模式。
- BIRD全量准确率和跨库泛化能力。



