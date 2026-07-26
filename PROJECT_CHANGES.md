# 项目修改记录

## 强制工作准则

1. 先审查并记录问题；修改任何项目文件前必须向用户申请并获得批准。
2. 尽量不改变原项目结构；环境配置优先遵循原项目文件，缺少配置时先申请补充。
3. 是否修改以能否运行和完成查询测试为主要依据；阻塞项优先最小修正，并同步更新问题记录。
4. 不影响运行和查询测试的问题延后酌情处理。
5. 每次修改记录批准情况、涉及文件、修改原因和验证结果；问题状态变化时同步更新 `PROJECT_ISSUES.md`。
6. 修改后执行与风险相称的测试，不以修改测试掩盖实现问题。
7. 不记录、输出或提交真实密钥及其他敏感配置。
8. 回退仅限本次已确认的修改，不覆盖他人或用户的现有变更。
9. 后续每次项目修改必须按代码级粒度记录，不能只写功能摘要。每条详细记录至少包含：批准与对应问题、修改前证据、逐文件的函数/类/常量/参数或代码分支变化、调用链与行为变化、新增测试函数的输入构造和关键断言、明确未修改范围、验证结果、潜在影响、故障归因索引以及可独立执行的精确回退范围。
10. 如果同一修改后续补充代码、测试或修正实现，必须更新原变更条目和测试数量，不另留相互矛盾的旧描述；新发现但未获批修正的问题只登记问题，不混入已批准修改范围。
11. 所有工作必须遵守实事求是原则。结论必须明确区分“实际运行测试结果”“源码直接证据”和“尚待验证的推测”；发现问题必须提供可复现的实际测试，解决问题必须执行修改后的实际测试并记录结果。未经测试验证的内容不得写成已发现事实、已修复或已通过。
12. 以完成既定项目任务、能够正常运行并通过必要查询测试为完成边界；禁止为了追求无限完善而持续优化代码或扩大项目范围。非阻塞、非必要改进只记录或延后处理，达到“能用、可验证、满足任务要求”后及时收束。

## 修改记录

| 日期 | 批准情况 | 涉及文件 | 修改内容 | 验证结果 |
|---|---|---|---|---|
| 2026-07-13 | 用户已批准 | `PROJECT_ISSUES.md`、`PROJECT_CHANGES.md` | 创建精简的问题记录和修改记录；登记当前已发现问题与强制工作准则 | 已核对；Git 仅新增这两个文件 |
| 2026-07-13 | 用户已批准 | `PROJECT_PROGRESS.md`、`PROJECT_CHANGES.md` | 创建工程进程表，登记工作阶段、真实状态、依赖条件和下一步 | 已核对；Git 仅新增三个获批记录文件 |
| 2026-07-13 | 用户已批准 | `PROJECT_ISSUES.md`、`PROJECT_PROGRESS.md`、`PROJECT_CHANGES.md` | 记录只读功能与 SQL 安全审查结果，新增 ISSUE-006 至 010，更新 P-05、P-07、P-08 | SQL 写操作、多语句、越权表、敏感字段、200行上限和数据库只读已验证；未修改业务文件 |
| 2026-07-13 | 用户已批准 | `PROJECT_ISSUES.md`、`PROJECT_PROGRESS.md`、`PROJECT_CHANGES.md` | 更新 ISSUE-010，新增 ISSUE-011；完成前端语法、HTML、资源和查询超时审查；完成 P-05、P-07 | 5 个 JS 语法通过；176 个 HTML ID 无重复；本地资源齐全；递归查询约 1.04 秒被超时中断 |
| 2026-07-14 | 用户明确要求并批准 | `PROJECT_CHANGES.md` | 新增强制工作准则第 12 条，明确以能运行、能完成必要查询和满足既定任务为收束边界，禁止无限优化或扩大项目 | 已核对准则文本；未修改业务代码、测试代码或项目结构 |
| 2026-07-13 | 用户已批准 | `.venv`、`PROJECT_ISSUES.md`、`PROJECT_PROGRESS.md`、`PROJECT_CHANGES.md` | 按原 `requirements.txt` 安装项目虚拟环境依赖并更新环境进度 | 关键依赖和应用导入通过；`pip check` 无损坏依赖；pytest 7 通过、1 个既有失败；未修改业务文件 |
| 2026-07-14 | 用户已批准 | `PROJECT_ISSUES.md`、`PROJECT_PROGRESS.md`、`PROJECT_CHANGES.md` | 记录 `.env`、Uvicorn、DashScope 和 8 条教学真实问数基线；确认 ISSUE-009，新增 ISSUE-012 | 服务健康检查通过；教学 SQL 片段 8/8，但 1 条返回 0 行语义错误；学生全局查询风险已复现 |
| 2026-07-14 | 用户已批准 | `PROJECT_ISSUES.md`、`PROJECT_PROGRESS.md`、`PROJECT_CHANGES.md` | 记录角色范围、四轮追问、歧义澄清、受控 SQL 修复及可信度评估；完成 P-06 | 显式角色范围、敏感字段、多轮、澄清和修复通过；学生模糊查询仍越权且获 92 分；专业枚举问题重跑成功，确认具有不稳定性 |
| 2026-07-14 | 用户已批准修改和测试 | `app/core/retrieval/atoms.py`、`tests/test_retrieval_context.py` | 对齐完整 Schema 与检索原子的枚举采样上限；新增专业枚举进入检索上下文的回归测试 | 定向测试 1 通过；真实问题使用 `major.name = '软件工程'` 并返回 5 行 |
| 2026-07-14 | 用户已批准修改和测试 | `app/core/business_domains.py`、`app/api/routes.py`、`app/service.py`、`app/core/validator.py`、`tests/test_role_permissions.py` | 将行级范围从条件式 Prompt 提示升级为生成后、执行前的强制校验；缺少范围进入原修复链；新增学生、教师、学院及 OR 绕过测试 | 完整 pytest 14 通过、1 个 ISSUE-002 既有失败；学生、教师、学院真实问题均先拦截全局 SQL 并修复为账号范围 |
| 2026-07-14 | 用户已批准修改和测试 | `app/core/business_domains.py`、`app/main.py`、`tests/test_authentication.py`、三份项目记录 | 删除缺失/未知令牌回退管理员逻辑，增加统一认证异常和 HTTP 401 映射；新增认证核心、公开接口、受保护接口和合法角色测试 | 定向 22 通过；完整 pytest 25 通过、ISSUE-002 既有失败 1 个；临时 Uvicorn 真实 HTTP 与合法学生查询通过 |
| 2026-07-14 | 用户明确要求生成 | `INITIAL_PROJECT_EVALUATION.md`、`PROJECT_CHANGES.md`、`PROJECT_PROGRESS.md` | 创建原始项目评价与责任边界文档，按实际运行、源码证据和未验证内容区分原始交付、环境准备及本轮优化 | 已与 README、原始 Git 基线、评测集、数据源配置及既有实际测试记录核对；未修改业务代码 |
| 2026-07-14 | 用户已批准 007A 修改和测试 | `app/core/business_domains.py`、`app/main.py`、`app/api/routes.py`、`app/api/governance.py`、`tests/test_authentication.py`、三份项目记录 | 复用现有角色 `features`，为 Profile/版本/质量和治理接口增加后端功能授权；低可信入队保留普通问数角色权限 | 授权定向 26 通过；完整 pytest 40 通过、ISSUE-002 既有失败 1 个；临时 Uvicorn 权限矩阵和合法学生真实问数通过 |
| 2026-07-14 | 用户已批准 007B 修改、测试和详细记录 | `app/api/routes.py`、`tests/test_authentication.py`、三份项目记录 | 为反馈与标准示例六类端点增加最小后端功能授权；保留普通问数反馈和示例读取，不扩展持久化所有权模型 | 定向 34 通过；完整 pytest 48 通过、ISSUE-002 既有失败 1 个；临时 Uvicorn 权限矩阵、内存写保护和合法学生真实问数通过 |
| 2026-07-14 | 用户已批准 ISSUE-008 修改和测试 | `app/api/data_access.py`、`app/core/data_access.py`、`tests/test_data_access_permissions.py`、三份项目记录 | 将现有允许表、禁用字段和账号范围应用到数据源列表、扫描、行读取、增删改及审计；非管理员隐藏 URL，无直接范围字段的原始表保守拒绝 | 专项 9 通过；完整 pytest 57 通过、ISSUE-002 既有失败 1 个；多角色 Uvicorn 矩阵和学生真实问数通过 |

## 详细变更条目

### CHG-20260714-01：检索枚举阈值对齐

- 批准：用户于 2026-07-14 明确批准修改和测试。
- 对应问题：ISSUE-012。
- 修改前证据：完整 Schema 含 `major.name` 的 18 个枚举值及“软件工程”；检索原子 `major.name.value_hints` 为空，检索上下文不含“软件工程”。完整 Schema 上限为 20，检索上限为 12。
- 修改文件：`app/core/retrieval/atoms.py` 将 `_ENUM_MAX` 从 12 调整为 20，并注明需与完整 Schema 保持一致；新增 `tests/test_retrieval_context.py`，同时验证检索原子和最终检索上下文。
- 代码级实现：
  - `app/core/retrieval/atoms.py::_sample_enum` 原有逻辑不变，仍执行 `SELECT DISTINCT` 并在取值数超过 `_ENUM_MAX` 时返回空字符串；本次只把它使用的模块常量 `_ENUM_MAX` 从 `12` 改为 `20`。
  - 由于 `major.name` 有 18 个不同值，修改前 `_sample_enum` 读取第 13 条后判定超限并返回空字符串；修改后 18 小于等于 20，函数返回由 `/` 分隔的完整专业名称，随后写入 `SchemaAtom.value_hints`。
  - `app/core/retrieval/pipeline.py::_render` 未修改；它会按原逻辑读取 `SchemaAtom.value_hints`，将其渲染为 `name TEXT -- 取值: ... / 软件工程 / ...`。因此修复点位于数据准备阶段，不是 Prompt 后处理。
  - `tests/test_retrieval_context.py::test_retrieval_keeps_major_name_enum_values` 第一段调用 `extract_atoms("teaching")`，从返回原子中定位 `table == "major" and column == "name"`，断言 `value_hints` 含“软件工程”；这可直接定位枚举采样是否再次失效。
  - 同一测试第二段调用 `load_schema("teaching")` 和 `retrieve_context(...)`，断言返回值非空且最终 `context_text` 含“软件工程”；这覆盖从原子抽取到检索渲染的完整链路，而不只验证常量值。
- 未修改：数据库、数据源配置、Prompt、教学画像、教学词表和既有评测 YAML 均未改动。
- 行为影响：13 至 20 个短文本枚举值的字段现在也会进入检索上下文；可能略微增加检索上下文长度，但不会改变 SQL 执行或 API 结构。
- 验证：新增测试 `1 passed`；与权限测试合跑 `10 passed`；真实问题生成 `major.name = '软件工程'`，返回 5 行。
- 归因参考：若后续出现检索上下文略增或枚举字段召回变化，优先核对本变更；若出现治理测试 `demo` 数据源失败，与本变更无关，见 ISSUE-002。
- 回退范围：仅恢复 `app/core/retrieval/atoms.py` 的 `_ENUM_MAX = 12` 并移除 `tests/test_retrieval_context.py`；不得回退其他用户文件。

### CHG-20260714-02：行级账号范围执行前校验

- 批准：用户于 2026-07-14 明确批准修改和测试，并要求逐次详细记录以便故障归因。
- 对应问题：ISSUE-009。
- 修改前证据：学生显式问“我的平均成绩”能生成 `student_id = 1`，但模糊问“平均成绩是多少”执行全局平均；范围仅存在于 Prompt，校验器不接收账号范围。
- 修改文件与职责：
  - `app/core/business_domains.py::row_scope_context`：只替换三个角色分支返回的提示文本，函数分支结构和 `AuthContext` 未改。学生分支由“出现我/我的时限定”改成“所有查询均限定”，并指定成绩/课程通过 `enrollment.student_id` 关联；教师分支固定要求 `teaching_class.teacher_id`；学院分支固定要求相应业务表的 `college_id`。
  - `app/api/routes.py::ask`：在原 `ask_service(...)` 调用末尾新增关键字参数 `row_scope=auth.row_scope`。取值仍来自 `user_from_token(ctx)` 产生的认证上下文，没有从请求正文接受范围值，避免用户自行提交其他账号 ID。
  - `app/service.py::ask`：函数签名新增可选参数 `row_scope: dict[str, Any] | None = None`，保持原有直接调用兼容；调用 `validate_and_fix(...)` 时新增 `required_scope=row_scope`。范围错误属于普通 `SQLValidationError`，会写入 `last_err` 并执行既有下一轮 `repair_sql(...)`；未改变未授权表/字段立即返回的原分支。
  - `app/core/validator.py::validate_and_fix`：签名新增末尾可选参数 `required_scope`，在表白名单和输出字段黑名单通过后、自动补 `LIMIT` 前调用 `_check_required_row_scope(...)`。因此不满足范围的 SQL 不会进入执行器，也不会因补 `LIMIT` 改变错误定位。
  - `app/core/validator.py::ROW_SCOPE_COLUMNS`：新增范围键到可接受真实字段的静态映射。`student_id` 接受选课、评教、作业提交、考勤、学习行为、奖助和学业预警表的对应字段；`teacher_id` 只接受 `teaching_class.teacher_id`；`college_id` 接受学院主键以及专业、学生、教师、课程的学院外键。
  - `app/core/validator.py::_check_required_row_scope`：从顶层语句提取 `WHERE` 文本，复用原 `_table_aliases` 建立 `e -> enrollment`、`tc -> teaching_class` 等映射，再把认证范围转换为 SQL 中实际可接受的“别名.字段”。找不到对应表/别名、范围键未知或条件不能证明时抛出带范围键和值的 `SQLValidationError`。
  - `app/core/validator.py::_scope_is_mandatory`：递归判断布尔表达式。顶层 `OR` 使用 `all(...)`，要求每个分支都有范围；顶层 `AND` 使用 `any(...)`，任一必选合取项含范围即可；拒绝 `NOT` 开头的范围表达式；末端仅接受带表名/别名的等值比较，同时支持 `e.student_id = 1` 和 `1 = e.student_id`。
  - `app/core/validator.py::_strip_outer_parentheses`：只在一对括号确实包住整个表达式时剥离括号，并跳过单、双引号内字符，为递归布尔判断保留真实分组。
  - `app/core/validator.py::_split_top_level_boolean`：逐字符记录括号深度和引号状态，只切分深度为 0 且具有单词边界的 `AND`/`OR`，避免切开括号内部条件或字符串内容。

#### `tests/test_role_permissions.py` 新增代码明细

- `test_student_global_aggregate_is_rejected_without_row_scope`：构造只从 `score s` 计算全局 `AVG(s.final_score)`、没有 `WHERE` 的 SQL；调用 `validate_and_fix(..., required_scope={"student_id": 1})`；要求抛出 `SQLValidationError` 且错误包含 `student_id = 1`。它直接防止 ISSUE-009 原始故障复发。
- `test_student_aggregate_with_required_row_scope_is_allowed`：构造 `score s JOIN enrollment e`，并在顶层 `WHERE` 写入 `e.student_id = 1`；要求校验通过且返回 SQL 保留该条件。它同时验证表别名 `e` 能被 `_table_aliases` 解析为 `enrollment`。
- `test_row_scope_cannot_be_bypassed_by_unscoped_or_branch`：构造 `WHERE e.student_id = 1 OR 1 = 1`；要求抛出“行级范围校验失败”。它对应 `_scope_is_mandatory` 中顶层 `OR -> all(...)` 的拒绝分支。
- `test_every_or_branch_may_repeat_the_required_row_scope`：构造两个括号分支，每个分支都包含 `e.student_id = 1`，但分别过滤 `enrolled` 和 `completed`；要求校验通过。它保证防绕过逻辑不会把所有合法 OR 查询一并禁止。
- `test_teacher_aggregate_with_required_row_scope_is_allowed`：构造 `score -> enrollment -> teaching_class tc` 连接并限定 `tc.teacher_id = 37`；传入 `required_scope={"teacher_id": 37}`，要求校验通过。它覆盖 `ROW_SCOPE_COLUMNS["teacher_id"]` 和三表别名链。
- `test_college_aggregate_with_required_row_scope_is_allowed`：构造 `score -> enrollment -> teaching_class -> course c` 连接并限定 `c.college_id = 1`；传入 `required_scope={"college_id": 1}`，要求校验通过。它覆盖学院范围落到课程外键的路径。
- 上述六项均直接调用校验器，不调用 Qwen、网络或数据库执行器；因此如果它们失败，可先判断为本次范围校验代码回归，而不是模型输出波动或数据库数据变化。
- 未修改：数据库、执行器、认证令牌逻辑、裁判 Prompt、前端和依赖均未改动。
- 行为影响：带 `student_id`、`teacher_id` 或 `college_id` 账号范围的角色，即使问题未写“我的/本学院”，生成 SQL 也必须包含其账号范围；不满足时最多使用项目原有修复轮次重新生成，仍不满足则返回错误而不执行。
- 安全边界：本变更校验顶层 WHERE 中明确、带限定名的等值范围；不自动重写复杂 SQL，避免错误注入条件。复杂 CTE 或无法证明范围的写法会保守拒绝并交由修复链简化。
- 验证：新增学生四项、教师一项、学院一项范围测试；编译和 `git diff --check` 通过；最终完整 pytest 为 `14 passed, 1 failed`，失败项与修改前相同，仍是 ISSUE-002。
- 真实回归：学生问题首轮全局平均被拒并修复为 `enrollment.student_id = 1`；教师问题修复为 `teaching_class.teacher_id = 37`；学院平均分和挂科率修复为 `course.college_id = 1`；三项均返回 1 行。
- 新发现：裁判未正确理解学生和教师账号范围，对安全且正确的本人结果给出错误低分或相反说明，已独立登记 ISSUE-013；这是本变更暴露出的下游语义不一致，不影响执行结果。
- 归因参考：若后续低权限角色出现“行级范围校验失败”、多一次模型修复调用或复杂 CTE 被拒，优先核对本变更；管理员无 `row_scope`，不受此校验影响。
- 回退范围：仅恢复上述五个文件中 CHG-20260714-02 的对应代码和六项新增测试；保留 CHG-20260714-01 及所有用户原有改动。

#### CHG-20260714-02 故障定位索引

| 后续现象 | 优先检查位置 | 判断依据 |
|---|---|---|
| 所有学生/教师/学院请求都未触发行级校验 | `app/api/routes.py::ask` 到 `app/service.py::ask` 的 `row_scope` 参数 | 范围可能没有从认证上下文传入服务 |
| 只有某一种角色始终报“行级范围校验失败” | `app/core/validator.py::ROW_SCOPE_COLUMNS` 与该角色 Prompt | 该角色生成的过滤字段可能不在允许映射中 |
| SQL 明明有正确别名条件却被拒绝 | `_table_aliases`、`_check_required_row_scope` | 先确认别名是否解析为预期真实表，再确认条件位于顶层 WHERE |
| 合法 AND/OR 组合被误拒或绕过条件被放行 | `_scope_is_mandatory`、`_strip_outer_parentheses`、`_split_top_level_boolean` | 这三个函数决定括号和布尔分支是否必须包含范围 |
| 低权限查询比以前多一次模型调用 | `app/service.py` 的 `SQLValidationError` 修复分支 | 首轮缺少范围会进入原 `repair_sql`，属于本变更预期行为 |
| 管理员查询也被要求提供范围 | `app/api/routes.py` 传入的 `auth.row_scope` | 管理员应为空字典并由 `_check_required_row_scope` 立即返回；若非空则属于异常 |
| 查询结果正确但可信度低或解释相反 | ISSUE-013，`app/core/judge.py` 与 `prompts/judge_prompt.txt` | 这是裁判缺少角色语义，不是范围校验或数据库结果错误 |

### CHG-20260714-03：缺失或未知令牌不再回退管理员

- 批准：用户于 2026-07-14 明确批准 ISSUE-006 修改和测试，并要求发现问题与解决问题均通过实际测试验证。
- 对应问题：ISSUE-006。
- 修改前实际证据：真实 API 探测中，无 `X-Demo-Token` 和未知令牌请求 `/api/auth/session` 均返回成功且用户角色为 `admin`；无令牌数据维护请求曾返回 200。源码随后定位到 `user_from_token` 的两次管理员回退，但问题结论以实际响应为依据。

#### 逐文件代码变更

- `app/core/business_domains.py::AuthenticationError`
  - 在 `AuthContext` 后新增 `AuthenticationError(ValueError)`，仅表示请求没有有效的演示认证令牌。
  - 继承 `ValueError` 保持其作为输入错误的语义，但 HTTP 状态不由核心层决定。
- `app/core/business_domains.py::user_from_token`
  - 修改前使用 `(token or "admin").strip() or "admin"`，因此 `None`、空字符串和纯空格都会变成 `admin`。
  - 修改后使用 `(token or "").strip()`；结果为空时立即抛出 `AuthenticationError("未登录或令牌无效")`。
  - 修改前 `DEMO_USERS.get(username)` 查不到用户时再次赋值 `DEMO_USERS["admin"]`；修改后未知用户名同样抛出认证异常。
  - 合法用户名仍调用原有 `auth_context(user)`，角色、业务域、表权限、字段限制和 `row_scope` 生成逻辑未改。
- `app/main.py::_authentication_error_handler`
  - 新增 `Request`、`JSONResponse` 和 `AuthenticationError` 导入。
  - 在注册三个 API router 前调用 `@app.exception_handler(AuthenticationError)` 注册全局处理器。
  - 处理器固定返回 HTTP 401，JSON 为 `{"detail": str(exc)}`；因此 `routes.py` 和 `data_access.py` 中现有的所有 `user_from_token` 调用都得到统一响应，无需逐个复制 `try/except`。
- `tests/test_authentication.py`
  - 新增独立认证回归文件，使用 FastAPI `TestClient(app)` 走真实路由、异常处理器和响应序列化，不替换 `user_from_token`。
- `PROJECT_CHANGES.md`
  - 新增强制准则第 11 条，要求区分实际测试、源码证据和待验证推测；未验证内容不得记录为已发现、已修复或已通过。

#### `tests/test_authentication.py` 测试代码明细

- `test_user_from_token_rejects_missing_blank_and_unknown_tokens`
  - 参数化输入 `None`、空字符串、纯空格和 `not-a-real-user`，形成四个独立用例。
  - 每个用例直接调用 `user_from_token(token)`，要求抛出 `AuthenticationError`，且消息匹配“未登录或令牌无效”。
- `test_user_from_token_keeps_known_role_identity`
  - 输入合法令牌 `student`，断言用户名仍为 `student`、角色仍为 `student`、范围仍为 `{"student_id": 1}`。
  - 用于证明本次删除的是回退逻辑，而不是破坏合法角色上下文。
- `test_auth_session_returns_401_without_valid_token`
  - 参数化真实 HTTP 请求头为空和 `X-Demo-Token: not-a-real-user` 两种情况。
  - 请求 `/api/auth/session`，断言状态码严格为 401，JSON 严格等于 `{"detail": "未登录或令牌无效"}`。
- `test_auth_session_restores_known_user`
  - 使用教师令牌请求 session，断言 200 且返回角色为 `teacher`。
- `test_public_auth_bootstrap_endpoints_remain_accessible`
  - 无令牌请求 `/api/health` 和 `/api/auth/options`，断言均为 200 且登录选项非空。
  - 无令牌向 `/api/auth/login` 提交不存在账号，断言得到登录逻辑自身的 401“用户名或密码错误”，证明请求确实进入公开登录接口而非被令牌校验提前阻断。
- `test_ask_rejects_missing_token_before_model_call`
  - 无令牌提交包含合法问题和 `teaching` 数据源的 `/api/ask` 请求，断言 401 和统一 JSON。
  - 因响应在 `user_from_token` 处产生，测试不会调用 Qwen，可定位认证必须先于问数链。
- `test_data_access_rejects_missing_token_instead_of_using_admin`
  - 无令牌请求 `/api/data-access/sources`，断言 401 和统一 JSON，直接覆盖修改前无令牌获得管理员路径。

#### 实际验证结果

- 定向测试：`tests/test_authentication.py` 与 `tests/test_role_permissions.py` 合计 `22 passed`。
- 完整测试：`25 passed, 1 failed`；唯一失败仍是 ISSUE-002 中治理测试使用未注册 `demo` 数据源，与修改前调用栈一致。
- 编译及格式：`python -m compileall -q app tests` 和 `git diff --check` 通过。
- 临时 Uvicorn 真实 HTTP：`/api/health` 200；缺失 session 401；未知令牌 session 401；合法学生 session 200 且角色为 student；无令牌数据维护 401；无令牌问数 401。
- 合法真实查询：学生令牌请求“平均成绩是多少？”返回 200、1 行，SQL 连接 `score` 与 `enrollment` 并含 `WHERE e.student_id = 1 LIMIT 200`，证明认证修复后正常问数和此前行级范围修复仍可工作。
- 临时服务：测试脚本在 `finally` 中停止 Uvicorn；未把测试服务作为常驻进程保留。

#### 未修改范围与安全边界

- 未修改 `app/api/routes.py`、`app/api/data_access.py` 的各接口权限规则，未顺带处理 ISSUE-007、008。
- 未修改前端。源码显示启动恢复 session 失败时会清除本地令牌，但本轮没有把浏览器页面表现记录为已实测结论。
- 当前仍是项目原有的演示令牌模型：已知用户名字符串仍可作为 `X-Demo-Token`。本次实际解决的是缺失、空白和未知令牌自动成为管理员，不宣称其为生产级会话认证。

#### 故障归因与精确回退

| 后续现象 | 优先检查位置 | 判断依据 |
|---|---|---|
| 缺失或未知令牌重新返回 200/admin | `business_domains.py::user_from_token` | 两个抛出 `AuthenticationError` 的分支可能被恢复或绕过 |
| 核心函数抛出认证异常但 HTTP 返回 500 | `main.py::_authentication_error_handler` | 全局异常处理器可能未注册或响应构造失败 |
| 合法学生、教师令牌也返回 401 | `DEMO_USERS.get(username)` 前的规范化以及合法角色单元测试 | 可能错误拒绝了非空已知用户名 |
| health、登录选项或登录接口要求令牌 | 路由是否错误调用 `user_from_token` | 本变更没有给公开接口增加依赖 |
| 认证通过但管理接口仍可越权 | ISSUE-007、008 | 这是接口授权与数据范围问题，不属于 ISSUE-006 回归 |
- 回退时仅恢复 `business_domains.py::AuthenticationError/user_from_token`、`main.py::_authentication_error_handler` 和 `tests/test_authentication.py`；项目记录只更新对应条目。不得回退 CHG-20260714-01、02 或用户其他修改。

### CHG-20260714-04：原始项目评价与责任边界文档

- 批准：用户于 2026-07-14 明确要求在下一步工作前生成详细原始项目评价，用于区分本轮与上一阶段工作。
- 新增文件：`INITIAL_PROJECT_EVALUATION.md`。
- 评价基线：当前 Git `HEAD` 中的原始跟踪文件和本轮修改前已保存的实际运行记录；没有用当前未提交修复后的代码冒充原始状态。
- 证据来源：完整 README、`tests/teaching_eval_cases.yaml`、`data_sources.yaml`、原始 `user_from_token`、原始 `service.validate_and_fix` 调用，以及已经执行的依赖、pytest、Uvicorn、API、SQLite、Qwen 和安全测试结果。
- 文档实现：分为项目内容、面向问题、首次环境、首次启动、八条教学问数、角色查询、多轮/澄清/修复、确认问题、通过的安全检查、仅源码发现事项、综合评价、责任范围和认定误区十二部分。
- 事实边界：把 `.env`/依赖归入环境准备；把 BIRD 缺失与不可用源展示分开；把实际错误、源码证据和未做浏览器验证的判断分开；不对具体个人作无证据的主观评价。
- 未修改范围：没有修改 `app/`、`tests/`、配置、数据库、Prompt 或当前问题状态，只新增评价文档并登记进程。
- 验证方式：核对文档中的原始认证代码与 `git show HEAD:...` 一致；核对评测问题与 YAML 一致；核对项目能力与 README 一致；核对问题及测试数与项目记录一致；执行 Markdown 差异检查。
- 归因参考：后续报告若需要判断问题属于原始交付还是本轮修改，应先查本文件第十部分，再查 `PROJECT_CHANGES.md` 对应 CHG 条目和 Git 差异。
- 回退范围：仅移除 `INITIAL_PROJECT_EVALUATION.md` 及本条文档记录，不得回退任何业务修复或测试。

### CHG-20260714-05：ISSUE-007A 管理接口功能授权

- 批准：用户于 2026-07-14 在逐项核对 11 条工作准则后明确批准 ISSUE-007A 修改和测试。
- 对应问题：ISSUE-007 的第一阶段。
- 修改前实际证据：临时 Uvicorn 中 Profile、版本、质量、治理设置和待审队列对无令牌、学生令牌均返回 200；`/api/schema` 对照无令牌返回 401。内存替身受控写测试中，无令牌和学生令牌的 Profile 保存、治理设置保存实际进入了替身函数并返回 200。
- 失败的测试脚本说明：第一次只读 Uvicorn 探测因 PowerShell 管道语法错误在启动服务前退出，没有产生项目测试结果；修正脚本后的状态矩阵才作为问题证据，脚本错误不计为项目故障。

#### 逐文件代码变更

- `app/core/business_domains.py::AuthorizationError`
  - 在现有 `AuthenticationError` 后新增 `AuthorizationError(PermissionError)`，仅表示令牌有效但当前角色缺少功能权限。
  - 没有修改 `ROLES` 中任何角色的 `features`，授权判断完全复用原项目角色配置。
- `app/core/business_domains.py::require_feature`
  - 新增签名 `require_feature(ctx: AuthContext, feature: str) -> AuthContext`。
  - 使用 `feature not in ctx.features` 判断；失败时抛出包含当前角色标签的授权异常，成功时返回原 `AuthContext`。
- `app/main.py::_authorization_error_handler`
  - 在现有 401 认证异常处理器之后新增 `AuthorizationError` 全局处理器。
  - 固定返回 HTTP 403 和 `{"detail": str(exc)}`；认证失败仍由原处理器返回 401，二者没有合并。
- `app/api/routes.py::_require_feature`
  - 将未使用的 `_auth(...)` 辅助函数替换为 `_require_feature(token, feature)`。
  - 调用链为：读取 `X-Demo-Token` → `user_from_token` 验证身份 → `require_feature` 验证功能；因此缺失/未知令牌为 401，合法但无功能角色为 403。
- `app/api/routes.py` 的 `knowledge` 端点
  - 为 `get_profile`、`update_profile`、`get_profile_versions`、`publish_profile_endpoint`、`rollback_profile_endpoint`、`update_profile_version_endpoint`、`delete_profile_version_endpoint`、`get_quality` 增加 `X-Demo-Token` Header 参数。
  - 每个函数在数据源读取、文件保存、版本操作或质量计算之前首先调用 `_require_feature(ctx, "knowledge")`，保证越权请求不会触达存储函数。
- `app/api/governance.py::_require_feature`
  - 增加 `Header`、`require_feature` 和 `user_from_token` 导入，并新增与核心路由相同的认证→授权辅助调用链。
- `app/api/governance.py` 的 `governance` 端点
  - `get_review_items`、`update_review_item`、`accept_review_item_endpoint`、`reject_review_item_endpoint`、`get_governance_settings`、`update_governance_settings` 均新增 Header 并在业务函数前要求 `governance`。
  - 按原角色配置，管理员具有 `governance`；学生、教师、学院和教务均不具有，本次没有擅自扩大角色权限。
- `app/api/governance.py::create_low_confidence_review_endpoint`
  - 新增 Header，但要求 `ask` 而不是 `governance`。
  - 这样普通学生、教师等问数角色仍能把低可信结果提交待审队列，无令牌请求则为 401。

#### `tests/test_authentication.py` 新增测试明细

- `test_all_knowledge_management_endpoints_reject_student`
  - 通过 8 组参数覆盖 Profile GET/PUT、版本 GET、发布、回滚、版本元数据 PUT、版本 DELETE 和质量 GET。
  - 每组使用学生令牌，断言严格为 403 且消息含“无权使用该功能”；写端点使用合法最小请求体，使测试确实进入端点授权而不是在请求模型校验阶段失败。
- `test_knowledge_reader_allows_college_manager`
  - 通过 3 组参数实际读取 Profile、版本和质量，使用学院令牌断言 200，证明没有把原有 `knowledge` 角色一并阻断。
- `test_profile_write_does_not_call_storage_for_student`
  - 用 `monkeypatch` 将 `save_profile_dict` 替换为只记录调用的内存函数。
  - 学生 PUT 断言 403 且调用列表为空；学院 PUT 断言 200 且调用列表只出现一次 `("teaching", profile)`，没有写磁盘。
- `test_governance_read_requires_governance_feature`
  - 无令牌读取设置断言 401；学生和教务断言 403；管理员断言 200。
- `test_governance_write_does_not_call_storage_without_feature`
  - 将 `save_settings` 替换为内存调用记录；学生 PUT 断言 403 且无调用，管理员 PUT 断言 200 且调用一次。
- `test_low_confidence_queue_requires_ask_but_not_governance`
  - 将 `create_low_confidence_review` 替换为内存函数；无令牌 POST 断言 401 且无调用，学生 POST 断言 200、`queued=true` 且载荷被调用一次。
- 上述 6 个测试函数经参数化形成 15 个新增测试实例；加上原认证测试后，该文件定向执行共 `26 passed`。

#### 实际验证结果

- 定向测试：`tests/test_authentication.py` 为 `26 passed`。
- 编译与格式：`python -m compileall -q app tests`、`git diff --check` 通过。
- 完整 pytest：`40 passed, 1 failed`；唯一失败仍为 ISSUE-002 的未注册 `demo` 数据源，调用栈与修改前一致。
- 临时 Uvicorn 知识接口：无令牌 401、学生 403、学院 200、管理员 200。
- 临时 Uvicorn 治理接口：无令牌 401、学生 403、学院 403、管理员 200。
- `/api/schema` 对照：无令牌 401，学生、学院、管理员均为 200，证明普通查询/Schema 权限未被误改。
- 合法真实问数：学生问题“我的平均成绩是多少？”返回 200、1 行，SQL 为 `score JOIN enrollment` 并包含 `e.student_id = 1 LIMIT 200`。
- 所有临时 Uvicorn 服务均在脚本 `finally` 中停止；本轮真实写接口只使用内存替身，没有修改 Profile、治理设置或反馈文件。

#### 未修改范围与行为边界

- 未修改反馈和示例接口，它们仍属于 ISSUE-007B。
- 未修改数据维护接口及其表、字段、行级范围，仍属于 ISSUE-008。
- 未修改前端、角色 `features`、数据库、Prompt、依赖和环境配置。
- 源码显示学生请求治理设置 403 后前端会使用默认设置，知识加载失败也有空值回退；本轮没有进行真实浏览器页面交互，因此不把页面表现写成已通过。

#### 故障归因与精确回退

| 后续现象 | 优先检查位置 | 判断依据 |
|---|---|---|
| 无令牌管理接口返回 403 而不是 401 | 各 `_require_feature` 是否先调用 `user_from_token` | 正确顺序应先认证、后授权 |
| 学生能再次修改 Profile 或治理设置 | 端点函数开头的 `_require_feature` 及受控写测试 | 授权必须发生在存储函数之前 |
| 学院无法读取 Profile/质量 | `ROLES["college_manager"].features` 与 `require_feature("knowledge")` | 本次预期学院保留 knowledge 访问 |
| 教务能够进入治理队列或设置 | 原角色配置不含 governance；检查端点是否错误要求 knowledge | 007A 没有为教务新增治理权限 |
| 学生低可信结果无法入队 | `create_low_confidence_review_endpoint` 是否误用 governance | 本端点应要求 ask |
| 普通问数、Schema 或行级范围异常 | ISSUE-006/009 相关调用链和真实问数回归 | 007A 不应修改 ask/schema 权限与 SQL 范围 |
- 回退仅恢复本条列出的 `AuthorizationError/require_feature`、403 处理器、routes/governance 端点 Header 与权限调用，以及 6 个新增测试函数；保留 ISSUE-006、009、012 和评价文档等其他修改。

### CHG-20260714-06：ISSUE-007B 反馈与标准示例接口授权

- 批准：用户于 2026-07-14 明确批准执行下一步，并要求详细记录修改内容和解决的问题。
- 对应问题：ISSUE-007 的第二阶段；007A 已完成，本条不改动 007A 的治理、Profile、版本和质量授权。

#### 修改前实际证据

- 使用 FastAPI `TestClient`，将 `add_feedback`、`create_feedback_review`、`list_feedback`、`delete_feedback`、`delete_review_items_for_feedback`、`list_examples`、`upsert_example`、`delete_example` 全部替换为只记录调用的内存函数。
- 无令牌和学生令牌分别请求反馈 GET/POST/DELETE、示例 GET/POST/DELETE，12 次请求全部返回 200；每次均实际进入相应内存函数，因此确认路由没有认证或授权。测试未调用文件存储，没有改写 `data/feedback` 或 `data/examples`。
- 源码直接证据：`app/static/app.js::savedFewShotsForRequest` 从 `standardExamplesCache` 选择示例，问数时通过 `few_shots` 发送；`app/service.py::ask` 将这些示例加入模型上下文。因此标准示例被改写会影响 SQL 生成链路。

#### `app/api/routes.py` 逐函数代码变化

- `create_feedback(req, token)`：新增 `X-Demo-Token` Header 参数，在 `add_feedback` 和 `create_feedback_review` 之前调用 `_require_feature(token, "ask")`。缺失/未知令牌先返回 401；所有原有合法问数角色仍能提交反馈。
- `get_feedback(source, limit, token)`：新增 Header 参数并在 `list_feedback` 前要求 `knowledge`。学生和教师不能列出全局反馈，学院、教务和管理员按原角色配置保留知识管理读取。
- `remove_feedback(item_id, token)`：新增 Header 参数并在 `delete_feedback`、`delete_review_items_for_feedback` 前要求 `ask`，保留前端对当前反馈撤销或切换的既有流程。
- `get_examples(source, limit, token)`：新增 Header 参数并在数据源检查、`list_examples` 前要求 `ask`。普通学生和教师仍可取得会参与问数的标准示例。
- `save_example(req, source, token)`：新增 Header 参数并在数据源检查、`upsert_example` 前要求 `knowledge`，学生和教师不能新增或用相同 ID 改写标准示例。
- `remove_example(item_id, source, token)`：新增 Header 参数并在数据源检查、`delete_example` 前要求 `knowledge`，学生和教师不能删除标准示例。
- 调用链统一为 Header → `user_from_token` → `require_feature` → 数据源/存储操作；没有新增授权模块、角色 feature 或数据格式。

#### `tests/test_authentication.py` 新增测试明细

- `test_feedback_and_example_endpoints_reject_missing_token_before_storage`：6 组参数覆盖两类资源的 GET/POST/DELETE；为八个可能读写的函数统一安装 `fail_if_called`，使用合法最小请求体，断言无令牌严格返回 401 和既有错误 JSON，且任何存储函数一旦被调用就立即使测试失败。
- `test_feedback_permissions_keep_ask_workflow_and_protect_management_list`：用内存列表记录反馈新增、建审、列表、删除和删除关联审查调用；断言学生列表为 403 且零调用，学生创建和删除均为 200 并按顺序调用对应函数，学院列表为 200 并返回受控反馈。
- `test_example_permissions_allow_ask_read_and_require_knowledge_for_writes`：用内存函数构造单条标准示例；断言学生读取 200，学生新增/删除均为 403 且没有写调用，学院新增/删除均为 200 且调用参数为 `teaching` 与 `memory-example`。
- 本次新增 3 个测试函数，其中首项参数化为 6 个测试实例，共增加 8 个实际测试实例。

#### 实际验证结果

- 定向测试：`pytest tests/test_authentication.py -q` 为 `34 passed`；4 项原有弃用警告和 1 项已知 `.pytest_cache` 写入警告不影响结果。
- 编译与格式：`python -m compileall -q app tests/test_authentication.py`、`git diff --check` 通过。
- 临时 Uvicorn GET 权限矩阵：反馈列表为无令牌 401、学生 403、学院 200、管理员 200；示例列表为无令牌 401、学生 200、学院 200、管理员 200。
- 第一次沙箱内真实问数到达 API 并返回 HTTP 200，但 DashScope 连接以 WinError 10013 失败，SQL 为空；该次只记录为网络权限阻断，不记为查询通过或项目故障。
- 在获准的沙箱外网络环境重试同一学生问题“我的平均成绩是多少？”：HTTP 200、1 行、无错误，SQL 为 `SELECT AVG(s.final_score) ... WHERE e.student_id = 1 LIMIT 200`。
- 第一次完整 pytest 因系统旧临时目录 `pytest-of-...` 拒绝访问而出现 `46 passed, 3 setup errors`，未作为有效代码回归。未删除旧目录；改用新的 `--basetemp` 后得到 `48 passed, 1 failed`，唯一失败仍为 ISSUE-002 的未注册 `demo` 数据源。
- 所有临时 Uvicorn 服务均在 `finally` 中停止；写接口测试均使用内存替身，没有改写反馈、示例或治理文件。

#### 未修改范围、残余边界与潜在影响

- 未修改 `app/core/feedback.py`、`app/core/examples.py`、请求模型、现有数据文件、前端、角色配置、数据库、Prompt、依赖和环境配置。
- 为避免扩大本地演示项目，没有新增 `created_by` 或旧反馈迁移。反馈 ID 为随机值，学生不能再通过列表获得全局 ID，但持有某个 ID 的合法 `ask` 用户仍可请求删除；这是明确保留的本地演示边界，不宣称为生产级所有权隔离。
- 示例读取必须保留给 `ask`，否则学生和教师会失去前端标准 few-shot；示例写入使用 `knowledge`，与现有知识库管理入口一致。
- `.pytest_cache` 和旧系统 pytest 临时目录权限未被清理或修改；通过独立临时基目录完成有效回归。

#### 故障归因索引与精确回退

| 后续现象 | 优先检查位置 | 判断依据 |
|---|---|---|
| 学生无法提交或撤销反馈 | `create_feedback/remove_feedback` 的 feature | 两者应为 `ask`，不能误改成 `knowledge` |
| 学生无法取得标准示例或问数 few-shot 变少 | `get_examples` | 读取应为 `ask`，写入才是 `knowledge` |
| 学生能够新增、改写或删除标准示例 | `save_example/remove_example` | 两个写端点必须在存储前要求 `knowledge` |
| 匿名请求返回 403 而不是 401 | `_require_feature` 调用顺序 | 必须先由 `user_from_token` 认证，再检查 feature |
| 完整 pytest 出现临时目录 setup error | pytest `--basetemp` 与系统旧临时目录 | 属于运行环境权限；与 ISSUE-002 断言失败分开归因 |
- 精确回退范围：只移除上述六个路由新增的 Header 参数和 `_require_feature` 调用，并移除本条新增的 3 个测试函数；不得回退 CHG-20260714-01 至 05、用户文件或其他现有修改。

### CHG-20260714-07：ISSUE-008 数据维护表、字段和账号范围

- 批准：用户于 2026-07-14 在查看修改范围、正反面和边界测试计划后明确批准。
- 对应问题：ISSUE-008；不混入 ISSUE-003、004、010、011 或 013。

#### 修改前实际证据

- 教师 TestClient 请求 `/api/data-access/sources` 返回 200、12 个数据源，教学源含非空 `url` 和全部 17 张表。
- 教师扫描教学源返回 `student` 表及 `id/student_no/name` 等字段；读取学生表首行返回相同字段，`total=8926`。
- 内存替身受控测试中，教师对 `controlled/student` 的 POST、PATCH、DELETE 均返回 200，并分别调用 `insert_row/update_row/delete_row`；审计接口返回了受控 `student_no/name`。替身测试未写数据库或审计文件。
- 源码直接证据：原 `_require_maintainer` 只按四个角色名放行；读取执行 `SELECT *`，增删改只检查数据源 `writable`，没有传入 `allowed_tables`、`denied_columns` 或 `row_scope`。

#### `app/core/data_access.py` 逐函数代码变化

- `_resolved_scope_columns(table, columns, required_scope)`：新增范围解析。优先使用表内同名 `teacher_id/college_id`；本人实体表允许将 `teacher.id/college.id` 映射到账号值；其他无法直接证明范围的表抛出 `PermissionError`，不增加 JOIN 权限引擎。
- `_visible_columns`：在真实表列顺序中保留允许字段；结果为空时拒绝。
- `_scope_sql`：把解析后的范围生成为参数化等值 `WHERE`，范围值不拼接进 SQL。
- `_row_matches_scope`：在更新和删除事务中检查读取到的原记录是否属于账号范围。
- `_filtered_row`：写操作响应仅返回允许字段，审计仍保留核心原记录供后续受控过滤。
- `table_rows`：新增可选 `allowed_columns`、`required_scope` 参数；先读取真实表结构，再生成明确列清单和参数化范围条件；`COUNT(*)` 与分页 SELECT 使用同一范围，所以 `total` 是账号范围内总数，而不是全表总数。
- `insert_row`：新增同样两个策略参数；拒绝提交禁用字段和冲突范围值，缺失直接范围时自动写入当前账号值；本人实体表主键范围不允许新增；返回值移除不可见字段。原 `writable` 与 SQLite 检查保持不变。
- `update_row`：在原事务中读取旧记录后先校验范围，再拒绝禁用字段和把范围字段改成其他账号；只有通过后才执行 UPDATE、提交和审计。
- `delete_row`：在原事务中校验旧记录范围，通过后才 DELETE、提交和审计；返回删除记录时只暴露允许字段。

#### `app/api/data_access.py` 逐函数与调用链变化

- `_require_maintainer`：由硬编码角色集合改为复用 `require_feature(user_from_token(token), "data_access")`；没有改变任何角色的 feature。
- `_table_policy`：管理员绕过表限制；其他角色必须命中 `allowed_tables`，再按 `table.column` 移除 `denied_columns`，并确认 `row_scope` 可在单表直接落实。
- `_filtered_scan`：过滤扫描结果并重新计算 `table_count/column_count`；范围无法直接落实的表不展示。
- `_filtered_sources`：对每个数据源复用扫描过滤；非管理员把 `url` 置空，表列表和数量改为当前角色可安全维护的范围。
- `_table_access`：在行读写前取得真实表列并返回允许列与账号范围。
- `_filtered_audit`：只保留允许表、允许字段且记录前/后值能证明属于账号范围的审计项；管理员保留完整结果。
- `sources/scan/rows/create_row/patch_row/remove_row/audit` 均接收 `_require_maintainer` 返回的 `AuthContext` 并使用上述策略；数据源注册、连接测试、CSV/DB 导入仍维持管理员专属。
- 行读写调用链为：认证 → `data_access` feature → 表/字段/范围策略 → 核心 SQL/事务内二次范围执行。
- 首次专项测试发现 `_table_access` 抛出的 403 被通用 `except Exception` 改写为 400；在四个行读写端点增加 `except HTTPException: raise`，保留 403，`PermissionError` 也明确映射为 403。测试预期未放宽。

#### `tests/test_data_access_permissions.py` 新增测试明细

- `test_source_list_redacts_non_admin_url_and_filters_tables_by_scope`：教师断言 URL 为空、学生表不出现、数量一致；管理员断言教学 URL 与学生表仍存在。
- `test_teacher_scan_and_rows_only_expose_direct_personal_scope`：扫描结果逐表必须含 `teacher_id` 或为本人 `teacher` 表；学生表读取 403；授课班读取 200、总数等于返回数且全部 `teacher_id=37`。
- `test_college_rows_are_limited_to_bound_college`：学院读取学生分页，断言所有行 `college_id=1`，范围总数大于单页数量。
- `test_academic_office_keeps_allowed_table_but_not_denied_teacher_number`：教务读取教师表仍为 200，但 columns 和 row 均无 `teacher_no`。
- `test_audit_is_filtered_by_table_columns_and_row_scope`：内存构造本人授课班、其他教师授课班和学生身份三条审计；教师只得到本人一条。
- `test_api_rejects_disallowed_write_before_storage`：把 `insert_row` 替换为记录函数；教师向学生表 POST 返回 403 且调用列表为空。
- `scoped_sqlite` fixture：在 pytest 临时目录创建只有 `id/teacher_id/title/secret` 的 SQLite 表，写入教师 37 和 38 两行；替换数据源与审计函数，不接触教学库。
- `test_core_read_filters_columns_rows_and_total`：断言隐藏 `secret`、只返回教师 37 一行且范围 total 为 1。
- `test_core_insert_enforces_scope_and_denied_columns`：省略范围时自动写入 37；范围 38 和写 `secret` 均拒绝；只有成功操作产生一次内存审计。
- `test_core_update_and_delete_reject_cross_scope`：本人更新/删除成功；其他教师更新/删除及把范围改成 38 均拒绝；只记录成功审计。
- 共新增 9 个测试函数和 1 个临时库 fixture。

#### 实际验证结果

- 现有认证回归：`tests/test_authentication.py` 为 `34 passed`。
- 专项首次：`7 passed, 2 failed`；两项均因正确越权被错误映射成 400。补充 HTTPException 原样抛出后重跑为 `9 passed`。
- 完整 pytest：使用独立 `--basetemp` 得到 `57 passed, 1 failed`；唯一失败仍是 ISSUE-002 的未注册 `demo` 数据源。
- 编译与格式：`python -m compileall -q app tests`、`git diff --check` 通过。
- 临时 Uvicorn：教师 URL 已隐藏、来源表不含 student、直接读 student 为 403；教师授课班 `total=12` 且全部 `teacher_id=37`；学院学生 `total=1491` 且分页全部 `college_id=1`；教务无 `teacher_no`；管理员仍有学生 `name`；学生数据维护为 403。
- 合法学生真实问数“我的平均成绩是多少？”：HTTP 200、1 行、无错误，SQL 包含 `WHERE e.student_id = 1 LIMIT 200`。
- 所有临时 Uvicorn 服务均在 `finally` 中停止；实际教学库只读。写回归只使用 pytest 临时 SQLite 和内存审计，没有修改教学数据、数据源配置或真实审计文件。

#### 未修改范围、边界与潜在影响

- 未修改角色配置、教学数据库、`data_sources.yaml`、前端、Prompt、模型、依赖和环境配置；未清理 `.pytest_cache`。
- 数据维护采用比智能问数更保守的单表直接范围：教师不能在原始维护页打开需通过 JOIN 才能证明本人范围的课程、成绩等表；这些聚合仍可走已保护的智能问数链。该限制是安全收束，不建设通用跨表维护权限引擎。
- 非管理员不再从数据维护列表取得完整 URL；管理员行为不变。
- 对自定义/BIRD 等非教学表，现有非管理员 `allowed_tables` 通常不包含其表名，因此数据维护页会隐藏；跨库通用角色模型属于后续独立需求，不在本变更扩展。

#### 故障归因索引与精确回退

| 后续现象 | 优先检查位置 | 判断依据 |
|---|---|---|
| 越权返回 400 而非 403 | 四个行读写端点的 `except HTTPException` 顺序 | HTTPException 必须先原样抛出 |
| 教师看到其他教师授课班 | `table_rows` 的 `_resolved_scope_columns/_scope_sql` | COUNT 与 SELECT 都应含 `teacher_id=37` |
| 学院 total 为全校总数 | `table_rows` 的 COUNT 查询 | total 必须复用范围 WHERE |
| 禁用字段出现在读写响应 | `_visible_columns/_filtered_row` 与 `_table_policy` | API 与核心均传递同一允许列集合 |
| 合法管理员被限制 | `_table_policy` 的 `auth.is_admin` 分支 | 管理员应保留全表全列且无 row_scope |
| 教师看不到需跨表关联的数据维护表 | 单表直接范围策略 | 这是明确边界，不是问数链回归 |
- 精确回退范围：仅恢复本条对 `app/api/data_access.py`、`app/core/data_access.py` 的策略参数、辅助函数和端点传参，并移除 `tests/test_data_access_permissions.py`；不得回退 CHG-20260714-01 至 06 或用户其他修改。

### CHG-20260714-08：BIRD 后续范围标记（仅管理记录）

- 批准：用户于 2026-07-14 明确要求“BIRD 应该需要涉及，先做一个标记，先进行当下的主线内容”。
- 对应问题：ISSUE-010；本条不是 BIRD 接入、修复或测试通过记录。
- 修改前实际证据：`data/` 实际只有教学库及其辅助目录，`Test-Path data/bird` 返回 `False`；README 明示 BIRD 原始数据库未随仓库提供；`scripts/eval_bird.py` 源码要求外部目录含 `dev.json` 和 `dev_databases/`。
- `PROJECT_ISSUES.md`：更新 ISSUE-010 的时间、证据文件和状态；明确 BIRD 后续必须涉及，但在教学库主线完成前暂缓，恢复时从单库 5～10 题开始。
- `PROJECT_PROGRESS.md`：把当前主线收敛为 ISSUE-003 教学评测；将 BIRD 放到教学库验收后，不安排全量或检索 A/B 优化。
- 调用链与行为变化：无。没有改动 Python、前端、Prompt、数据源配置、环境、依赖或数据库；应用启动、查询和权限行为不受影响。
- 验证边界：本轮只核对本地目录、README 和评测脚本参数，没有下载或实际运行 BIRD，因此不得把“脚本存在”记录成“BIRD 已接入/已通过”。
- 潜在影响与归因：后续若 BIRD 无法加载或评测失败，优先归为尚未执行的外部数据接入工作，不能归因于本条管理文档修改。
- 精确回退范围：仅恢复 ISSUE-010 本次新增的 BIRD 暂缓说明、进程表当前下一步的对应文字，并删除本条；不得回退任何程序修改。

### CHG-20260714-09：ISSUE-003 教学执行结果自动评测

- 批准：用户于 2026-07-14 明确批准“ISSUE-003 的上述修改和测试”。
- 对应问题：ISSUE-003；真实评测新发现的生成问题独立登记为 ISSUE-014，没有混入未获批业务修正。

#### 修改前实际证据

- 实际运行 `scripts/eval.py --cases tests/teaching_eval_cases.yaml --source teaching`，脚本退出码为1并提示“没有匹配的 case”；源码中 `main` 只读取每条 case 的 `source`，未继承 YAML 顶层 `source: teaching`。
- 固定模型输出为可执行的 `SELECT COUNT(*) FROM student` 后实际调用 `run_case`，返回 `标准 SQL 无法执行: 'expected_sql'`；教学 YAML 只有 `checks/contains_sql`。
- `_cmp_rowset/_cmp_ordered/_cmp_cell` 对 `[[1]]` 和 `[[1.0]]` 的实际结果均为 `False`，与原“避免 1 vs 1.0”注释不一致。
- SQLite `PRAGMA table_info(student)` 实测不存在 `grade_year`，真实年级字段为 `enrollment_year`；原第3题关键词检查不能证明列存在。
- 第4题标准查询实际有240位教师，经过生产校验与执行链返回200行且 `capped=True`；原评测器丢弃执行器的截断标记。

#### `scripts/eval.py` 逐函数代码变化

- 新增 `_normalize_cell(value)`：仅对实际数值类型使用 `Decimal(str(value)).normalize()` 生成稳定文本，使 `1` 与 `1.0` 精确等价；`None`、布尔值和普通字符串保持明确表示，不加入会掩盖真实分数差异的模糊容差。
- `_normalize_rows` 改为逐单元调用 `_normalize_cell`；`_cmp_cell` 同样复用该函数，三个比较器的数值规则一致。
- 新增 `load_cases(cases_path)`：读取 YAML 后复制各 case；当 case 没有自己的 `source` 时继承顶层 `source`，显式 case 数据源仍优先。
- `main` 改为调用 `load_cases`，原 `--filter/--source` 筛选、输出和退出码保持不变。
- `run_case` 保留预测 SQL 和标准 SQL 的 `capped` 返回值；有 `expected_capped` 时分别校验标准和预测状态，没有声明时要求二者一致。结果原因会明确显示 `capped`，不再把前200行相等描述成完整结果。
- 仍先比较列数、再按 `rowset/ordered/cell` 比较结果；没有增加只看 SQL 关键词的宽松通过分支。

#### `tests/teaching_eval_cases.yaml` 逐用例变化

- 所有8题增加 `category`、`expected_sql`、`match` 和 `expected_capped`，删除仅凭 `contains_sql` 判定通过的配置。
- `teaching_001`：学院左连接在读学生，按学院输出学生数。
- `teaching_002`：限定2025年春季，以总评低于60的条件聚合挂科率并取前5。
- `teaching_003`：使用真实 `student.enrollment_year` 和数据库真实枚举“软件工程”，同时保留在读过滤。
- `teaching_004`：教师左连接授课班和选课，输出教师 ID、姓名、班级数和选课人次；声明 `expected_capped: true`。首次模型评测暴露额外 ID 与标准列定义不一致后，数据库实测发现22组重名教师，因此将 ID 纳入标准答案，而不是放宽列数检查。
- `teaching_005`：按课程聚合总评并用 `HAVING AVG(...) < 70`。
- `teaching_006`：按教师聚合教学评价平均分，稳定排序取前10。
- `teaching_007`：明确以2025年春季开课班中的不同课程计数，使用 `cell` 比较。
- `teaching_008`：首次真实评测证明“学生所属学院”和“课程所属学院”会产生两组不同且各自可解释的真实结果；问题改为“按学生所属学院”，标准 SQL 沿学生—选课—成绩链统计，不修改模型来迎合歧义题。

#### `tests/test_eval_runner.py` 新增测试明细

- `_stub_runtime`：用受控数据源、Schema、模型输出、校验器和两次执行结果替身隔离网络与真实数据库；不改变生产模块。
- `_case`：集中构造含标准 SQL、比较类型和截断预期的最小 case。
- `test_load_cases_inherits_top_level_source`：临时 YAML 同时构造继承源和显式覆盖源，断言分别为 `teaching/other`。
- `test_numeric_comparators_treat_integer_and_float_as_equivalent`：断言三个比较器均接受 `1` 与 `1.0`。
- `test_run_case_accepts_equivalent_result`：预测浮点1.0、标准整数1，断言完整 `run_case` 正面通过。
- `test_run_case_rejects_wrong_or_empty_result`：预测空集、标准一行，断言反面失败且原因是结果集不一致。
- `test_run_case_rejects_capped_state_mismatch`：预测未截断、标准与用例要求截断，断言边界失败。
- `test_run_case_reports_missing_expected_sql`：删除标准 SQL，断言明确报告标准 SQL 无法执行。

#### 实际验证结果

- 编译与差异：`python -m compileall -q app scripts tests` 和 `git diff --check` 通过。
- 专项 pytest 两轮均为 `6 passed`；只有既有 LangChain 弃用和 `.pytest_cache` 权限警告。
- 8条标准 SQL 在教学库实际执行两轮均为8/8成功；最终行数为6、5、5、200、7、10、1、6，第4题 `capped=True`，其余为 `False`。
- 沙箱内首次真实模型运行因 Windows 套接字权限对8题全部报 DashScope 连接失败；获准联网后立即重跑成功连接，因此该轮归因于沙箱网络，不计作项目0/8。
- 第一轮联网真实模型为6/8：第4题列数不一致，第8题使用课程所属学院口径。澄清第8题和修正第4题唯一身份列后，最终真实模型为 `7/8 (87.5%)`。
- 最终唯一失败 `teaching_004`：模型再次使用 `JOIN teaching_class`；数据库实测240名教师中239名有授课班，ID 94 无授课班，自动结果比较正确发现遗漏，已登记 ISSUE-014，未修改 Prompt。
- 完整 pytest 为 `63 passed, 1 failed`；唯一失败仍是 ISSUE-002 的治理测试未注册 `demo` 数据源。相比修改前新增6个通过测试，没有增加失败项。
- 三个本轮生成的独立 pytest 临时目录已在确认绝对路径位于项目根后清理；既有 `.pytest_cache` 未处理。

#### 未修改范围、边界与潜在影响

- 未修改 `app/` 业务代码、Prompt、教学数据库、数据源配置、角色权限、`.env`、依赖、前端或 BIRD 文件。
- 数值比较只消除表示等价，不接受近似但不同的聚合值；模型自行 ROUND 后仍可能失败，这是有意保留的严格边界。
- 评测仍要求列数一致；第4题因重名教师需要 ID 作为稳定身份，不接受只按姓名合并。
- 第4题在生产200行上限下只能评估被截断窗口及 `capped` 状态；报告不宣称返回全部240人。
- 评测器直接测试生成、校验、执行与结果比较，不覆盖 HTTP 认证、行级角色范围或异步裁判；这些由现有专项/API测试覆盖。

#### 故障归因索引与精确回退

| 后续现象 | 优先检查位置 | 判断依据 |
|---|---|---|
| `--source teaching` 找不到用例 | `load_cases` 与 `main` | 顶层 source 必须写入缺省 case 后再筛选 |
| 正确整数/浮点结果被判不同 | `_normalize_cell` 和三个比较器 | `1` 与 `1.0` 应规整成同一文本 |
| 第4题看似前几行相同仍失败 | `teaching_004`、ISSUE-014 | ID 94 的无授课教师在内连接中被遗漏 |
| 第8题再次出现两组学院数值 | 用例问题文字与连接路径 | 标准口径是学生所属学院，不是课程所属学院 |
| 8题全部连接失败 | 沙箱网络与 DashScope 访问 | Windows 10013 发生在模型调用前，不是 SQL 失败 |
- 精确回退范围：仅恢复 `scripts/eval.py` 本条新增的加载、数值与截断逻辑，恢复 `tests/teaching_eval_cases.yaml` 的8条原关键词配置，并删除 `tests/test_eval_runner.py`；同时恢复 ISSUE-003/014 与进程表的本条状态文字、删除 CHG-09。不得回退 CHG-01 至 08 或任何业务代码。

### CHG-20260714-10：ISSUE-014 “每位教师”零记录保留规则

- 批准：用户于 2026-07-14 明确批准“ISSUE-014 的上述 Prompt 最小修改和测试”。
- 对应问题：ISSUE-014；没有混入 ISSUE-002、004、010 或 013。

#### 修改前实际证据

- ISSUE-003 最终真实评测前的两次模型输出均以 `teacher JOIN teaching_class` 统计“每位教师”，没有使用左连接。
- 教学库只读查询确认教师总数为240、`teaching_class` 中不同教师为239；唯一没有授课班的是教师 ID 94。第二轮结果比较虽然前两行相同，但完整前200行集合不一致，证明内连接实际改变结果。
- `prompts/sql_prompt.txt` 教学口径第6条原本只规定班级数和选课人次的聚合公式，没有规定“每位/所有教师”是否应包含零记录教师；这是源码直接证据，不把模型行为归因于未出现的规则。

#### `prompts/sql_prompt.txt` 代码级变化

- 仅扩展“教学数据专用口径”第6条，没有新增章节或改动通用生成链。
- 当问题明确要求“每位教师/所有教师”时，要求以 `teacher` 为主表，依次 `LEFT JOIN teaching_class` 和 `enrollment`，使无授课班教师返回0。
- 明确计数使用 `COUNT(DISTINCT teaching_class.id)` 和 `COUNT(enrollment.id)` 所代表的明细主键，不允许 `COUNT(*)` 把左连接占位行误计为1。
- 保留语义例外：只有用户明确限定“有授课的教师”时，才允许用内连接排除零记录教师。
- 调用链变化：`app/core/chain.py::_chat_prompt` 在新进程中通过 `_read("sql_prompt.txt")` 加载该文本；Python 函数、参数、模型配置和 SQL 校验/执行链均未改变。

#### 实际验证结果

- 修改后独立运行 `teaching_004` 两次，均为 `rowset 通过 (200 行, capped)`；模型调用耗时分别约4424ms和5066ms。
- 随后完整运行8条教学评测，8/8通过：行数分别为6、5、5、200、7、10、1、6；第4题继续明确 `capped`，没有宣称返回全部240人。
- 完整 pytest 为 `63 passed, 1 failed`；唯一失败仍是 ISSUE-002 的治理测试使用未注册 `demo` 数据源，与修改前相同。
- `python -m compileall -q app scripts tests` 与 `git diff --check` 通过；警告仍为既有依赖弃用和 `.pytest_cache` 权限提示。
- 本轮 pytest 临时目录在核对绝对路径位于项目根后已清理；未触碰既有 `.pytest_cache`。

#### 未修改范围、潜在影响与故障归因

- 未修改 `app/`、评测器、教学标准 SQL、测试函数、数据库、数据源配置、角色权限、前端、环境或依赖。
- 规则被限制在教学教师工作量口径，不建设跨数据库的通用“零事实记录维度补全”引擎。
- 模型输出具有概率性；两次独立专项加一次完整回归均通过，证明当前配置下重复可用，但不宣称未来每次调用绝对一致。
- 若后续再次遗漏零授课教师，优先检查 Prompt 是否被实际加载、模型是否遵守第6条以及是否出现新的问题限定；不要放宽标准结果或删除教师 ID 来掩盖。
- 若只查询“有授课的教师”却出现零授课者，检查第6条的明确例外是否被模型忽略。
- 精确回退范围：仅将 `prompts/sql_prompt.txt` 教学口径第6条恢复为修改前单句，并恢复 ISSUE-014、进程表的本次状态、删除 CHG-10；不得回退评测器、用例或任何 CHG-01 至 09 修改。

### CHG-20260714-11：ISSUE-002 治理发布测试隔离

- 批准：用户于 2026-07-14 明确批准“ISSUE-002 的上述测试隔离修改和测试”。
- 对应问题：ISSUE-002；没有修改治理实现，也没有混入 ISSUE-004、010 或 013。

#### 修改前实际证据与归因

- 完整 pytest 多轮稳定失败于 `test_publish_review_is_approved_before_publish`：`accept_review_item` 调用真实 `save_profile_dict("demo", snapshot)`，后者经 `profile_path/get_source` 抛出未知数据源 `demo`。
- 源码直接证据：测试已替换 `governance.load_profile_dict` 和 `publish_profile`，但没有替换同一发布分支必经的 `save_profile_dict`；`demo` 仅为测试虚构名称，不在真实 `data_sources.yaml` 中。
- 修改前用临时目录和内存保存替身实际执行同一调用链，得到 `status=accepted`、保存源为 `demo`、保存快照与审查快照一致、发布参数正确，证明实现路径可用且失败来自测试隔离缺口。

#### `tests/test_governance.py` 代码级变化

- 仅修改 `test_publish_review_is_approved_before_publish`，新增 `saved` 字典和 `events` 列表；没有新增或删除测试函数。
- 新增局部 `fake_save(source, profile)`：把实际收到的数据源和画像快照写入内存字典，追加 `save` 事件并返回画像；不调用真实数据源或写画像文件。
- `fake_publish` 在原有发布参数记录基础上追加 `publish` 事件。
- 通过 `monkeypatch.setattr(governance, "save_profile_dict", fake_save)` 补齐与既有读取/发布替身相同的测试隔离边界。
- 创建审查后新增断言 `saved == {}`，与原 `published == {}` 一起证明审批前既未保存也未发布。
- 接受审查后新增断言：保存源严格为 `demo`；保存画像严格等于创建审查时的 `orders` 快照；`events == ["save", "publish"]`。原状态和发布参数断言均保留，没有放宽实现要求。
- 调用链验证变为：创建发布审查并捕获快照 → 接受审查 → 内存保存完整快照 → 调用发布替身 → 审查状态更新为 accepted。

#### 实际验证结果

- 治理专项 `tests/test_governance.py` 为 `3 passed`；保存与发布的新增断言已实际执行。
- 完整 pytest 为 `64 passed`、无失败；这是当前工作树首次完整全绿。
- `python -m compileall -q app scripts tests` 和 `git diff --check` 通过。
- 剩余5条警告为既有 FastAPI/TestClient、LangChain、`on_event` 弃用及 `.pytest_cache` 权限提示，不属于本次失败。
- 两个本轮 pytest 临时目录在验证绝对路径位于项目根后已清理；既有 `.pytest_cache` 未修改。

#### 未修改范围、潜在影响与故障归因

- 未修改 `app/core/governance.py`、`schema_profile.py`、数据源配置、画像文件、数据库、Prompt、前端、环境或依赖。
- 测试不再验证真实画像文件落盘；它验证的是审查编排是否把正确快照先交给保存层再交给发布层。真实画像持久化由其自身模块边界负责。
- 若后续再次出现未知测试数据源，优先检查新增的发布分支是否有未隔离的外部依赖；不能通过注册虚假生产数据源规避。
- 若事件顺序变为 `publish → save`，本测试应失败，因为发布成功但快照尚未保存会破坏审查发布语义。
- 精确回退范围：仅移除该测试中的 `saved/events/fake_save`、保存替身和新增断言，并恢复 ISSUE-002、进程表状态、删除 CHG-11；不得回退治理实现或 CHG-01 至 10。

### CHG-20260714-12：ISSUE-013 强制角色范围裁判上下文

- 批准：用户于 2026-07-14 明确批准“ISSUE-013 的上述最小修改和测试”。
- 对应问题：ISSUE-013；没有混入 BIRD、ISSUE-004、缓存或依赖警告处理。

#### 修改前实际证据与用户可见影响

- 行级范围修正后的真实学生查询执行正确，但异步裁判给出总分56、正确性40，并把 `student_id=1` 解释为多余过滤；教师查询出现同类理由。
- `app/service.py::ask` 已持有 `role_label` 和 `row_scope` 并用后者做执行前校验，但原 `stash_judge(...)` 调用只传问题、Schema、SQL、结果、方言和检索状态。
- `app/core/judge.py::judge/stash` 原签名没有角色或范围参数；裁判消息只包含问题、Schema、方言、SQL和结果预览，因此它无法区分系统强制范围与模型自行增加的过滤。
- 前端源码直接证据：`confidenceBadge` 在查询结果元信息区域显示彩色“结果可信度”；`fetchConfidence` 轮询裁判；`queueLowConfidenceIfNeeded` 会把低于阈值的结果送入治理队列。因此问题既影响演示，也会产生虚假治理任务。

#### `app/core/judge.py` 逐函数代码变化

- 引入 `Any` 类型以表示已有的范围值字典。
- 新增 `_scope_context(role_label, row_scope)`：有范围时用排序后的 JSON 明确列出角色和真实强制条件，并声明这些条件是可信系统授权约束；无范围时明确说明没有账号级强制行过滤，不为管理员伪造范围。
- `judge` 在原参数末尾增加可选 `role_label=None`、`row_scope=None`，保持旧调用兼容；在人类消息的方言与 SQL 之间插入独立权限范围段，不把权限文字混进用户原问题。
- `stash` 同样增加两个可选参数，并把它们写入后台 worker 的 `args`；`_judge_worker` 仍通过 `judge(**args)` 调用，没有改变线程、容量、过期或 fallback 行为。
- `_fallback_judge` 未修改；它只根据执行和结果状态给临时估算，不对 SQL 中的具体范围条件作语义判断。

#### `app/service.py::ask` 调用链变化

- 将原位置参数式 `stash_judge(...)` 改为明确关键字参数，保留全部原值。
- 追加传入 `role_label=role_label`、`row_scope=row_scope`；这两个值来自认证上下文，且同一 `row_scope` 已用于 `validate_and_fix(required_scope=...)`。
- 调用链现为：认证角色范围 → SQL生成 → 执行前强制范围校验 → SQL执行 → 把同一可信范围交给异步裁判。
- SQL生成、修复、校验、执行、返回格式和前端接口字段均未改变。

#### `prompts/judge_prompt.txt` 变化

- 在评分原则中增加：若输入存在 Mandatory access scope，必须在授权范围内理解问题，不得因为用户未重复“我的/本学院”而扣除强制条件的正确性分。
- 明确只豁免范围上下文实际列出的条件；其它过滤仍须正常审查，避免把任意 ID 条件都视为合法。
- 增加一条面向业务用户的权限范围正例，理由不泄露技术字段或 SQL术语。

#### `tests/test_judge_scope.py` 新增测试明细

- `_FakeJudgeLlm`：捕获裁判消息并返回固定合法 JSON，不联网。
- `_run_controlled_judge`：构造同一查询的角色/范围变体并取得实际发送给裁判的人类消息。
- `test_judge_message_includes_trusted_mandatory_scope`：学生范围断言角色、`student_id=1` 和可信授权说明均进入消息。
- `test_judge_message_does_not_invent_scope_for_admin`：管理员断言明确无强制范围，且消息中不出现 Required row filters。
- `test_stash_preserves_scope_for_background_worker`：用不启动 worker 的线程替身检查 `_pending` 参数包含教师和 `teacher_id=37`，并在 `finally` 清理暂存项。
- `test_service_forwards_scope_to_validator_and_judge`：受控替换数据源、Schema、生成、校验、执行和解释，断言同一个 `student_id=1` 同时进入验证器和裁判，且成功响应返回受控 judge ID。

#### 实际验证结果

- 裁判范围专项为 `4 passed`；编译和 `git diff --check` 通过。
- 临时 Uvicorn 真实学生查询“我的平均成绩是多少？”：HTTP成功、1行、SQL含 `e.student_id = 1`；裁判状态 done、可信度95、正确性95、召回95，理由明确“学生本人可查看的成绩数据范围”。
- 真实教师查询“统计我的授课班级数和选课学生人次”：HTTP成功、1行、SQL含 `tc.teacher_id = 37`；裁判可信度93、正确性92、召回95，理由明确“当前账号可查看的数据范围”。
- 教师37的数据库直接对照：内连接与左连接结果都为12个授课班、976选课人次，零选课授课班为0，因此该次教师 SQL 对真实账号数据无遗漏。
- 临时服务在 `finally` 中停止并确认 `SERVER_STOPPED=True`；查询只读，未修改教学数据库。
- 完整 pytest 为 `68 passed`、无失败；编译和差异检查通过。5条警告仍为既有依赖弃用和 `.pytest_cache` 权限提示。
- 两个本轮 pytest 临时目录在核对绝对路径后清理；既有 `.pytest_cache` 未处理。

#### 未修改范围、潜在影响与故障归因

- 未修改前端、认证配置、角色范围定义、SQL生成 Prompt、数据库、数据源、依赖、环境或裁判分数公式。
- 范围值是系统认证上下文，不采信用户自然语言中的自报身份；管理员无范围分支不会自动合理化 SQL 中的任意 ID 过滤。
- 裁判仍是概率性信息模型；本次两类真实范围查询均明显越过低可信阈值，但不宣称所有未来措辞都固定同一分数。
- 若查询结果正确但再次被说成多余范围，依次检查 `service.ask` 的关键字传参、`stash` 暂存 args、`_scope_context` 输出和 judge Prompt 加载。
- 若任意非授权过滤被错误放过，核对它是否出现在真实 `row_scope`；Prompt 明确只豁免列出的系统条件。
- 精确回退范围：只恢复 `app/core/judge.py` 本条新增的范围辅助、参数和消息段，恢复 `app/service.py` 的裁判调用，移除 judge Prompt 新规则和 `tests/test_judge_scope.py`，并恢复 ISSUE-013/进程表状态、删除 CHG-12；不得回退行级 SQL校验或 CHG-01 至 11。

### CHG-20260715-01：BIRD 后续必测阶段标记（仅管理记录）

- 批准：用户于 2026-07-15 明确要求“现在先标记 BIRD 测试，随后再完成”。
- 对应问题：ISSUE-010；对应进程：P-12。本条不是 BIRD 接入或测试通过记录。
- 修改前证据：`data/bird/` 实际不存在；README 与 `scripts/eval_bird.py` 要求外部 `dev.json` 和 `dev_databases/`；当前没有可执行 BIRD 真实测试的数据条件。
- `PROJECT_ISSUES.md`：将 ISSUE-010 更新为已建立 P-12 必做标记，强调取得数据后只做单库5～10题，未运行前不得写成通过。
- `PROJECT_PROGRESS.md`：新增 P-12，范围限定为数据加载、Schema、生成 SQL、标准 SQL 执行结果比较和失败归因；状态为“待数据”。当前下一步先完成功能与测试覆盖审查。
- 调用链与行为变化：无。没有修改 Python、JavaScript、Prompt、配置、依赖、数据库或 BIRD 脚本；项目启动、查询和测试行为不受影响。
- 验证边界：只核对本地目录及既有 README/脚本要求，没有下载、生成或执行 BIRD，不能据此评价 BIRD 准确率。
- 精确回退范围：仅恢复 ISSUE-010 本次状态文字、删除 P-12 和本条记录；不得回退任何程序或此前记录。

### CHG-20260715-02：教学驾驶舱多角色 API 实测记录（仅管理记录）

- 批准：用户于 2026-07-15 明确批准更新 `PROJECT_ISSUES.md`、`PROJECT_PROGRESS.md`、`PROJECT_CHANGES.md` 三份记录文件。
- 对应问题与进程：新增 ISSUE-015、P-13。本条只记录已经执行的测试，不代表 ISSUE-015 已修复，也不包含 BIRD、ISSUE-004 或低优先级依赖升级。

#### 测试前源码直接证据

- `app/api/routes.py::get_teaching_dashboard` 接收 `term`、`college`、`major`、`course_type`，认证后把四项筛选、当前角色的 `allowed_tables` 和 `row_scope` 交给 `teaching_dashboard`。
- `app/core/teaching_dashboard.py::_normalize_filters` 会规范学期和课程类型，`_apply_filters` 能为学期、学院、专业和课程类型生成查询条件。
- 同文件 `teaching_dashboard` 的学生、教师、学院分支分别按 `student_id`、`teacher_id`、`college_id` 执行固定 SQL 后提前返回；实际读取确认这些查询没有调用 `_apply_filters`。无范围分支才全面调用该辅助函数。
- `app/static/app.js::renderDashboard` 固定把 `current_classes` 和 `current_enrollments` 标为“本学期开课”和“本学期选课”，其中开课副标题明确为“2025 春季学期”；`loadDashboard` 会把当前四项筛选传给 API。

#### 实际 API、数据库与边界测试

- 使用 FastAPI `TestClient` 直接调用真实 `/api/teaching/dashboard`，未替换认证、角色配置、驾驶舱函数或教学数据库；缺失令牌和无效令牌均实际返回401。
- `admin`、`jwc`、`college`、`teacher`、`student` 五个令牌均返回200，`permission.role` 分别为 `admin`、`academic_office`、`college_manager`、`teacher`、`student`。
- 用独立 `sqlite3` 查询 `data/teaching.db` 交叉核对：学院卡片和列表均限制在 `college_id=1`；教师工作量与课程列表限制在 `teacher_id=37`；学生课程列表限制在 `student_id=1`，学生成绩分布API合计11条，与数据库成绩数11条一致。
- 权限、角色和范围共22项检查通过；未发现跨学院、跨教师或跨学生的数据泄露。
- 对学院、教师、学生分别传入 `term=1900-spring`、不存在学院、不存在专业及不存在课程类型，三种角色的完整业务载荷均与无筛选请求完全相同；三项边界断言实际失败，不是源码推测。
- 管理员/教务处无筛选时返回 `current_classes=1037`、`current_enrollments=81835`；显式传 `term=2025-spring` 时返回105和14192。该差异与前端固定“本学期”标签共同构成 ISSUE-015 的默认口径证据。
- 边界补充：管理员传不存在学院或课程类型时返回空统计；传格式错误且无法解析的 `term=bad-format` 时保持无筛选结果。该行为已观察，但本条不把未定义的非法参数状态码要求扩展为新问题。

#### 完整回归、环境归因与未修改范围

- 首次 `python -m pytest -q` 得到 `61 passed, 7 errors`；7个错误均发生在 `tmp_path` 夹具创建阶段，统一为旧 Windows 临时目录 `C:\Users\大象~大象~\AppData\Local\Temp\pytest-of-大象~大象~` 的 `PermissionError [WinError 5]`，没有进入项目断言，不能记为7项功能失败。
- 随后未清理旧目录，改用 `python -m pytest -q -p no:cacheprovider --basetemp D:\NL2SQL\.codex-pytest-dashboard-20260715-1629`，完整结果为 `68 passed, 4 warnings in 6.92s`。四条均为既有 TestClient/httpx、LangChain、FastAPI `on_event` 弃用警告。
- 没有修改 Python、JavaScript、测试、Prompt、数据库、数据源、环境、依赖或旧 `.pytest_cache`；本条行为变化仅为三份管理记录增加真实测试结论。
- 本轮没有新增自动化测试文件，因此现有68项测试数量不变；22/25是本轮一次性多角色验证脚本的断言数量，不得与 pytest 数量相加。

#### 故障归因索引与精确回退

| 后续现象 | 优先检查位置 | 判断依据 |
|---|---|---|
| 学院、教师或学生切换筛选后数据不变 | `teaching_dashboard` 三个范围分支 | 当前分支在 `_apply_filters` 前返回，已由三种角色的实际请求复现 |
| 默认页面显示1037个“本学期开课” | 无范围分支默认过滤与 `renderDashboard` 标签 | 空学期请求统计累计值；2025春季实际为105 |
| 完整 pytest 再次出现若干 `tmp_path` setup error | Windows pytest 临时目录权限 | 使用独立 `--basetemp` 后同一工作树68项全部通过 |
| 后续出现跨角色驾驶舱数据 | 角色固定范围 SQL 和新增专项测试 | 本轮只证明当前样本未泄露；后续修改必须重新执行范围集合对照 |

- 精确回退范围：仅删除 ISSUE-015 行、删除 P-13 并恢复 P-08/P-10/“当前下一步”的本条文字、删除 CHG-20260715-02；不得回退任何程序文件、测试文件、此前问题状态或 CHG-20260715-01 及更早记录。

### CHG-20260715-03：ISSUE-015 教学驾驶舱范围筛选与统计标签修正

- 批准：用户于 2026-07-15 明确批准“ISSUE-015 修改和测试”。
- 对应问题：ISSUE-015；修改范围限定为教学驾驶舱后端、驾驶舱前端行为、新增专项测试及三份管理记录，没有混入 BIRD、NL2SQL 主链、数据库结构、认证、依赖或其它低优先级优化。

#### 修改前实际证据

- TestClient 实测学院、教师、学生分别携带不存在的 `term/college/major/course_type` 后，完整业务载荷与无筛选请求完全相同，三项边界断言失败；认证与行级范围22项通过。
- 源码直接证据：`get_teaching_dashboard` 已传入四项筛选，但 `teaching_dashboard` 的学生、教师和学院分支使用固定范围 SQL 后提前返回，没有调用 `_apply_filters`。
- 管理员/教务处空学期请求返回1037个班和81835条选课，显式 `2025-spring` 返回105和14192；前端却把两种结果都固定标为“本学期开课/本学期选课”。
- 原有68项 pytest 全部通过，因此本次只修正驾驶舱未覆盖行为，不归因于问数、权限校验器或数据库故障。

#### `app/core/teaching_dashboard.py` 代码级变化

- `_validate_scoped_filters(filters, row_scope)`：校验非空学期必须能解析为 `YYYY-semester`；学生和教师拒绝学院/专业参数；学院账号拒绝学院参数，防止客户端用筛选表达替代固定学院范围。既有路由继续通过 `ValueError → HTTP 400` 映射返回错误，未修改路由代码。
- `_public_filters(filters)`：只返回 `term/college/major/course_type` 四个公开值，不把内部解析出的 `year/semester` 暴露给页面；四个角色分支均返回实际生效筛选。
- `_student_warning_filters(filters, params)`：学生预警表直接保留 `w.student_id=:student_id`；学期使用预警自身年月，课程类型通过同一学生的选课、班级和课程 `EXISTS` 判断，不为使用筛选而读取学生身份表。
- `_filter_options(conn, college_id=None)`：可按固定学院缩小学院和专业选项；学院账号只得到计算机学院及其专业，教师和学生返回前再将学院/专业选项清空。学期和课程类型选项沿用原查询。
- 学生分支：所有课程、班级、成绩、作业、考勤、预警、学习行为及三类图表仍首先限定 `student_id`，再按查询已有或补充的 `teaching_class/course` 连接追加学期和课程类型；空学期不再硬编码2025春，而是返回该学生累计11个班/选课，显式2025春返回2个。
- 教师分支：课程、班级、选课、成绩、作业、考勤、学习行为、课程排行和工作量均保留 `teacher_id` 后追加学期/课程类型；空学期累计12个班、976选课，2025春为4个班、462选课。
- 学院分支：所有查询保留 `college_id`；对需要专业的统计补充选课和学生连接，对事实表补充已有主外键连接；班级、选课和学生数量使用 `COUNT(DISTINCT 主键)` 避免新增连接重复计数。支持学期、专业、课程类型，学院筛选固定为账号范围。
- 无范围管理员/教务处分支继续使用原 `_apply_filters`，仅把返回的内部筛选字典改为 `_public_filters`；原四类筛选 SQL 和权限表判断未重写。
- 调用链变为：路由认证并取得固定 `row_scope` → 规范化并校验角色可用筛选 → 原固定范围 SQL 追加筛选 → 返回业务结果、公开筛选和范围化选项。筛选条件只能缩小结果，不能移除原账号条件。

#### `app/static/app.js` 代码级变化

- `dashboardFilters` 根据 `currentUser.role` 在请求前清空不适用参数：学院/教师/学生不发送学院参数，教师/学生不发送专业参数；避免从上一个登录角色遗留的下拉值触发错误请求。
- `populateDashboardFilters` 根据 API 的 `permission.role` 隐藏对应下拉框并清空隐藏值；管理员、教务处保持四项可见，学院保留学期/专业/课程类型，教师和学生保留学期/课程类型。
- `renderDashboard` 使用响应中的 `filters.term` 动态生成卡片文字。空学期显示“开课班级/选课记录，全部学期”；指定学期显示“学期开课/学期选课”及当前下拉项文字，不再把累计值固定写成2025春季。
- 未修改 HTML 结构、CSS、其它页面、问数按钮、API 客户端或登录逻辑。

#### `tests/test_teaching_dashboard.py` 新增26项测试

- `test_dashboard_requires_valid_token` 两组：无令牌和未知令牌均断言401及统一中文错误。
- `test_dashboard_returns_the_authenticated_role` 五组：五个演示令牌断言200和各自 `permission.role`。
- `test_scoped_baseline_cards_match_independent_database_queries`：分别用独立 SQLite 查询核对学院在读学生、教师累计班级、学生累计班级。
- `test_term_filter_changes_scoped_results_and_matches_database` 三组：构造2025春季筛选，断言学生2、教师4、学院21个班，且均小于各自累计值。
- `test_course_type_filter_matches_each_scoped_role` 三组：构造 `required`，分别以独立 SQL 核对学生5门、教师6门、学院7门必修课程。
- `test_course_type_filter_does_not_expand_student_or_teacher_scope` 两组：从数据库构造学生本人/教师本人必修课程名称集合，断言低分、挂科和考勤列表返回名称均为其子集。
- `test_college_major_filter_stays_inside_bound_college`：构造软件工程专业，核对在读学生446人，并断言预警专业只含软件工程、学院列表只含计算机学院。
- `test_scoped_roles_reject_unsupported_or_malformed_filters` 四组：学生学院、教师专业、学院学院参数及错误学期格式均断言400和精确错误信息。
- `test_impossible_term_returns_empty_scoped_class_statistics` 三组：1900春季对学院、教师、学生均断言班级和选课为0，不再静默返回累计数据。
- `test_unrestricted_term_filter_keeps_existing_behavior`：管理员2025春季班级105、选课14192与独立 SQL 一致，证明原无范围筛选未回退。
- `test_filter_options_follow_role_scope`：学院选项只含本学院，教师和学生学院/专业选项为空。

#### 实际验证结果

- 首轮真实API冒烟：五角色无筛选均200；学生、教师的2025春季和必修筛选，学院的2025春季、软件工程和必修筛选均返回变化后的数据；学生学院、教师专业、学院学院参数均实际返回400。
- 驾驶舱专项在新增最后两项范围集合断言前为24/24通过；最终26项均包含在完整回归中并通过。
- 完整 pytest 使用独立 `--basetemp` 实际结果为 `94 passed, 4 warnings in 18.44s`；新增26项，原68项没有失败。
- `python -m compileall -q app tests`、`node --check app/static/app.js` 和 `git diff --check` 均通过。警告仅为既有 TestClient/httpx、LangChain、FastAPI `on_event` 弃用提示及 Git 行尾提示，不影响本次执行结果。

#### 未修改范围、潜在影响与故障归因

- 未修改 `app/api/routes.py`、认证角色定义、SQL生成/校验/执行链、Prompt、数据库、数据源、依赖、环境或 BIRD 文件。
- 驾驶舱空学期现在统一表示累计范围，因此学生、教师、学院的 `current_classes/current_enrollments` 数值较修改前的硬编码2025春季变大；字段名保持兼容，页面标签已同步纠正。这是口径修正，不是数据增加。
- 学院专业筛选需要连接学生记录，但返回仍是聚合值和既有课程/教师名称，不新增学生身份字段；固定 `college_id` 始终存在。
- 未执行真实浏览器点击验收；已完成 API、前端语法和响应字段测试。若浏览器显示/隐藏异常，应先检查角色切换后的 DOM 状态，不应回退后端范围筛选。
- 若筛选后数字异常增大，优先检查新增连接是否遗漏 `DISTINCT`；若出现越权名称，优先检查原固定 `student_id/teacher_id/college_id` 是否仍位于每条 SQL 的 `WHERE`。
- 若旧角色下拉值造成400，检查 `dashboardFilters` 是否在请求前按 `currentUser.role` 清空，而不只依赖响应后的隐藏处理。

#### 精确回退范围

- 只恢复 `app/core/teaching_dashboard.py` 本条新增的四个辅助函数签名/实现、三个范围分支的筛选连接与公开返回字段，以及无范围分支的公开筛选返回；不得回退该文件本条前已有驾驶舱统计。
- 恢复 `app/static/app.js` 的 `dashboardFilters/populateDashboardFilters/renderDashboard` 本条变化，删除 `tests/test_teaching_dashboard.py`。
- 将 ISSUE-015、P-08/P-09/P-10/P-13 和“当前下一步”恢复至 CHG-20260715-02 后状态并删除本条；不得回退 ISSUE-013/014、BIRD 标记或任何其它程序修改。

### CHG-20260715-04：浏览器验收补充问题最小修正

- 批准：用户在提交管理员/学生浏览器响应、Local Storage、403状态和发起程序栈截图后，于2026-07-15明确批准本批修改与测试。
- 对应问题：ISSUE-015补充口径、ISSUE-016角色切换页面残留、ISSUE-017学生问数多余知识管理请求。
- 未混入范围：ISSUE-018裁判假阴性、ISSUE-010/BIRD、治理设置403、未登录sources 401、依赖警告、数据库和新功能扩展均未修改。

#### 修改前实际证据与故障归因

- ISSUE-015浏览器证据：管理员请求响应中的 `filters` 明确为 `term=2025-spring/college=计算机学院`，但选择任意学院“学期开课”均为105；选择专业后数值会变化，排除了下拉未触发、整个响应缓存及专业完全失效。
- ISSUE-015独立数据库证据：2025春季全部班级105，按课程所属学院计算机学院应为21；其余学院为19/18/16/16/15。源码中无范围 `current_classes` 同时传 `student_alias/course_alias`，默认学院条件优先落在学生学院，语义变成“有该学院学生参与的班级”。
- 新增修改前测试后，管理员和教务处两组均实际失败为 `assert 105 == 21`；响应状态200且四个公开筛选值正确，进一步把故障限定在卡片SQL口径。
- ISSUE-016浏览器证据：管理员全校查询后切换学生，学生按权限正常直接进入智能问数，但输入、SQL和结果仍在；学生新请求实际 `history=[]`，故归因是前端DOM/运行时残留，不是后端模型历史、认证或行级范围串号。
- Local Storage证据：公共 `nl2sql.queryLog.v1` 保留不同角色问题，但学生页面没有查询日志入口；本批按本地演示边界选择退出时清空，不引入按账号持久化结构。
- ISSUE-017浏览器证据：学生正常 `/api/ask`、教学Schema、示例和裁判均200；质量和版本各403。DevTools发起栈分别为 `executeQuery → loadSchema → loadQuality` 与 `executeQuery → loadSchema → loadProfileVersions`；后端正确拒绝，无越权泄露。

#### `tests/test_teaching_dashboard.py` 代码级变化

- 新增参数化函数 `test_unrestricted_college_filter_counts_classes_owned_by_course_college`，输入令牌为 `admin`、`jwc` 两组，请求参数固定为 `term=2025-spring`、`college=计算机学院`。
- 第一组关键断言核对HTTP 200以及响应 `filters` 精确等于四字段字典，证明请求参数已被服务接受，且专业/课程类型保持空值。
- 第二组关键断言用独立SQLite SQL连接 `teaching_class → course → college`，按课程所属学院和学期计算21，并要求 `cards.current_classes` 与之相等。
- 测试数量由驾驶舱26项增至28项、完整pytest由94项增至96项；没有修改或放宽原26项测试，没有为通过而把期望值改成105。

#### `app/core/teaching_dashboard.py` 代码级变化

- 只修改无 `student_id/teacher_id/college_id` 账号范围分支的 `cards["current_classes"]` SQL拼接调用。
- 在原 `_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc")` 末尾传入已有参数 `college_scope="course"`；该参数使学院子句选用 `course.college_id`，不再因同时存在学生别名而优先选学生学院。
- 学期仍落在班级年月，专业仍通过学生专业限定，课程类型仍通过课程类型限定；SQL表连接、`COUNT(DISTINCT tc.id)`、返回字段和其它卡片完全保留。
- 调用链变化仅为：管理员/教务处驾驶舱筛选 → 无范围班级卡片 → 学院按课程归属；固定范围学院、教师、学生分支不受影响。

#### `app/static/app.js` ISSUE-016代码级变化

- 新增 `resetAssistantSession(clearQueryLog)`，集中清除 `HISTORY_KEY`、进度计时器、`conversationSource`、`currentResult`、`lastTrace`。
- 当参数为true时删除公共 `QUERY_LOG_KEY` 并调用 `renderQueryLog()`；没有删除收藏样例、术语、指标、Schema Profile或认证密码配置。
- 清空输入框、过程日志、SQL文本和元信息、表头/表体、结果摘要，复位结果标题和图表按钮；隐藏路由、进度、错误、澄清、SQL和结果区域，并以空 `currentResult` 刷新反馈按钮。
- 退出按钮仍先删除认证token和用户，再以 `resetAssistantSession(true)` 代替原只调用 `clearHistory()`；随后清空用户与驾驶舱/业务域缓存并显示登录页。
- 未修改学生默认进入智能问数的逻辑；该行为由学生没有dashboard feature决定，保持原权限设计。

#### `app/static/app.js` ISSUE-017代码级变化

- `loadSchema(src)` 仍首先请求当前角色可用的过滤Schema；有数据源时始终调用 `loadStandardExamples(src)`，保留学生生成SQL需要的few-shot示例。
- 新增 `hasFeature("knowledge")` 分支：只有知识管理角色才继续 `loadProfile`，并并行加载 `loadQuality/loadProfileVersions`。
- 未修改 `/api/quality`、`/api/profile/versions` 后端权限，不通过放宽403解决红色请求；未调整API客户端路径、Schema接口、示例读取权限或问数流程。

#### 实际验证结果

- 修改前专项：新增两组均失败，管理员/教务处实际值105、独立SQL期望21；共 `2 failed, 26 deselected`。
- 修改后相同筛选专项：两组均通过；随后驾驶舱完整专项为 `28 passed, 4 warnings`。
- 完整pytest使用独立 `--basetemp D:\NL2SQL\.codex-pytest-browser-fixes-full`，实际为 `96 passed, 4 warnings in 18.02s`。
- `python -m py_compile app/core/teaching_dashboard.py`、`node --check app/static/app.js`、`git diff --check`均通过。
- 四条警告仍为既有TestClient/httpx、LangChain和FastAPI `on_event`弃用提示；旧 `.pytest_cache` 未读取、清理或修改。
- 浏览器自动化不存在，因此不能把DOM清理和Network无403写成已人工通过；必须在当前服务重启/刷新后分别复验。

#### 潜在影响、故障归因与精确回退

- 学院筛选的“学期开课”会从跨学院学生参与口径改为课程归属口径；这是标签语义纠正，不修改教学数据。
- 退出会清空本浏览器公共查询日志，代价是切换回来也不能恢复旧日志；对课程演示的角色隔离优先，未扩展账号级存储。
- 异步裁判若在退出后返回，其可信度占位节点已随 `sqlMeta` 清空，既有 `isConnected` 检查会停止后续页面写入；未取消后端裁判任务。
- 若学院仍显示105，优先确认服务是否加载新代码以及请求响应中的 `cards.current_classes`；不得再次修改专业筛选。
- 若学生仍见旧结果，检查退出按钮是否进入 `resetAssistantSession(true)`；若 `history` 仍为空，不应归因后端权限。
- 若学生仍出现质量/版本403，检查浏览器缓存的 `app.js?v=p0-product-3` 是否刷新以及 `currentUser.features` 是否含knowledge；不得放宽后端接口。
- 精确回退：移除 `current_classes` 调用新增的 `college_scope="course"`；删除新增参数化测试；删除 `resetAssistantSession` 并恢复退出按钮原 `clearHistory()`；恢复 `loadSchema` 原Profile/质量/示例/版本加载顺序；同步恢复ISSUE-015～017、P-08～P-14并删除本条。不得回退CHG-20260715-03及更早变更。

### CHG-20260715-05：二次浏览器验收后的专业口径与静态缓存修正

- 批准：用户提交二次浏览器结果，并补充该专业开课现象覆盖春/秋学期和任一学院后，明确批准本次记录、口径提示、缓存版本与测试修改。
- 对应问题：ISSUE-015专业开课统计口径限制、ISSUE-016角色切换页面残留、ISSUE-017学生问数多余403。
- 修改顺序：遵循准则先更新`PROJECT_ISSUES.md/PROJECT_PROGRESS.md`登记二次失败和待修范围，再修改项目文件；本条在实际测试后补齐最终结果。
- 未混入范围：没有修改数据库、数据生成、后端驾驶舱SQL、认证、知识接口权限、Prompt、裁判、BIRD、依赖或其它低优先级问题。

#### 修改前实际证据与归因

- 用户二次浏览器实测：固定学期与学院后切换专业，学期开课数仍等于全部专业；切换角色后上一角色最后一条输入和结果仍显示；学生问数仍出现质量和版本两个403。三项因此均未按首次自动化结果直接关闭。
- 真实运行API矩阵：使用管理员令牌逐一请求有效`2025-spring`、`2025-autumn`，覆盖6学院、每学院3专业。春季18/18、秋季18/18，共36/36组`major_classes == all_classes`；请求响应`filters.major`均为所选专业，而`current_enrollments`随专业变化。例如春季计算机学院三个专业开课均21，选课分别716/717/663；秋季开课均21，选课分别453/450/442。
- 数据库与源码直接证据：`teaching_class`只有`course_id`，`course`只有`college_id`，不存在专业—课程或专业—教学班外键；`_apply_filters`的专业条件只能经选课学生`student.major_id`限定“该专业学生参与过的班”。因此当前数据无法提供真实的课程所属专业开课数，不能通过改期望值或编造SQL制造差异。
- 静态入口直接证据：本地运行服务的`/app.js?v=p0-product-3`内容已包含`resetAssistantSession`和knowledge权限分支；学生真实登录features不含knowledge，但`index.html`仍沿用修改前相同p3版本。二次浏览器表现与旧脚本一致，因此本次用缓存版本更新让浏览器可明确加载新脚本，不放宽后端403。

#### `app/static/app.js::renderDashboard`代码级变化

- 从公开响应`data.filters`新增读取`appliedCollege`和`appliedMajor`，不读取本地未提交的下拉值，确保标签对应后端实际接受的筛选。
- 有专业且有学院时将`current_classes`卡片标签改为“学院开课”；只有专业时标为“专业参与开课”；没有专业时保持原“学期开课/开课班级”。
- 新增`classSub`：专业筛选时显示“当前库无专业—课程归属，按该专业学生选课覆盖统计”，并保留所选学期文本；未改变`current_classes`数值、其它卡片、请求参数或后端SQL。
- 行为影响：用户能看到专业选课等指标确实被过滤，同时明确开课卡片不是培养方案意义的专业所属课程数；这以透明说明收束当前数据限制，不扩展项目结构。

#### `app/static/index.html`代码级变化

- 只将主脚本引用从`/app.js?v=p0-product-3`更新为`/app.js?v=p0-product-4`；API、弹窗、治理和数据维护脚本版本未改，因为本轮没有修改这些脚本。
- 调用链变化：首页重新加载→取得p4主脚本→角色切换执行`resetAssistantSession(true)`；学生执行`loadSchema`时使用`hasFeature("knowledge")`分支，不再沿用浏览器旧p3脚本。

#### `tests/test_authentication.py`代码级变化

- 新增`test_frontend_entrypoint_serves_current_role_isolation_script`，先GET`/`并断言HTTP 200和首页精确引用`/app.js?v=p0-product-4`。
- 再GET带p4参数的脚本，断言HTTP 200，并检查三个关键实现标记：`resetAssistantSession(clearQueryLog)`、`hasFeature("knowledge")`分支和专业口径提示文本。
- 该测试验证应用实际挂载的静态入口，而不是只读取磁盘文件；没有修改或放宽任何既有测试。完整pytest数量由96增至97。

#### 实际验证结果

- 新增定向测试实际为`1 passed, 4 warnings in 2.81s`；`node --check app/static/app.js`通过。
- 完整pytest使用独立`--basetemp D:\NL2SQL\.codex-pytest-static-cache-full`，实际为`97 passed, 4 warnings in 25.38s`。
- 对正在运行的本地服务真实HTTP请求：`GET /`为200且响应包含p4；`GET /app.js?v=p0-product-4`为200，响应同时包含清理函数、knowledge权限分支和专业提示。
- `git diff --check`退出码0；仅显示既有Windows LF/CRLF提示。四条pytest警告仍为TestClient/httpx、LangChain和FastAPI`on_event`弃用警告。
- 无浏览器自动化，故不能把角色DOM清空和学生Network无403写成已人工通过；ISSUE-015～017保持待第三次浏览器复验。
- 第三次浏览器人工复验：用户于2026-07-15实际确认三个问题均已解决，即专业开课口径提示正常、切换角色后上一角色查询内容和结果不再显示、学生问数Network不再出现原quality/profile versions两个403。该结果补充本条原“待人工复验”状态，ISSUE-015～017据此关闭；没有追加代码或测试修改。

#### 潜在影响、故障归因索引与精确回退

- 潜在影响仅为专业筛选时开课卡片标签/副标题变化，以及浏览器获取新的主脚本URL；没有业务数据或权限变化。
- 若数字仍相同且提示存在，属于已验证的数据模型限制；不得为了视觉差异伪造专业开课数。若选课数也完全不变，才应重新检查专业参数和数据。
- 若角色仍残留或学生仍有两个403，先在Network确认实际脚本URL是否为p4；若为p4，再记录Console异常和403发起程序栈后定位，不继续猜测缓存。
- 精确回退：恢复`renderDashboard`原`classLabel/termSub`及卡片第四参数，删除`appliedCollege/appliedMajor/classSub`；把`index.html`主脚本p4恢复p3；删除新增静态入口测试；同步恢复ISSUE-015～017与P-08～P-14本条文字并删除CHG-20260715-05。不得回退CHG-20260715-04及更早代码、测试或记录。

### CHG-20260715-06：ISSUE-018裁判波动与冷门问题只读复核

- 批准：用户先批准ISSUE-018只读重复取证，随后要求增加一次不常见问题测试，并批准将实际结果更新到三份记录。
- 修改范围：本条只修改`PROJECT_ISSUES.md`、`PROJECT_PROGRESS.md`和`PROJECT_CHANGES.md`；没有修改Python、JavaScript、Prompt、测试、数据库、数据源、依赖或环境。
- 对应问题：ISSUE-018。目标是判断首次正确结果被评33分是否为稳定实现缺陷，而不是为了提高分数直接调整Prompt。

#### 同题三轮真实API与裁判结果

- 身份与输入：管理员令牌、`source=teaching`、每轮`history=[]`，问题固定为“软件工程课程有多少名同学满分”。三轮分别独立调用`POST /api/ask`并轮询`POST /api/judge`至完成。
- 三轮生成SQL完全一致：连接`score → enrollment → teaching_class → course`，条件为`course.name='软件工程'`和`score.final_score=100`，使用`COUNT(*)`并由校验器保留`LIMIT 200`。
- 三轮实际执行均返回单元格0、`row_count=1`、无错误；裁判最终分依次93、92、92，召回分均95，正确性依次92、90、90。三轮理由均明确认可课程、选课、成绩数据和满分统计逻辑。
- 独立SQLite只读SQL确认“软件工程”课程存在1条，满分人数为0；`PRAGMA table_info(score)`确认字段包含`final_score`。
- `POST /api/debug/retrieval`实际返回`retrieval_used=true`，命中`course/student/evaluation/college/major/score/enrollment/academic_warning/teaching_class`，使用vector/keyword/graph三种检索器；2000字符预览已包含完整`score`表及`final_score`字段，故首次“没有成绩字段”的裁判理由不能归因字段缺失或4000字符截断。

#### 冷门问题真实测试与边界观察

- 问题为“2025年春季学期尚未解除、风险分不低于80分的考勤风险预警有多少条？”，管理员、教学源、空历史，仅真实问数一次。
- 生成SQL正确使用`academic_warning.year=2025`、`semester='spring'`、`warning_type='attendance_risk'`、`resolved=0`和`risk_score>=80`，返回104、无错误。
- 裁判实际为`final=96/retrieval=100/correctness=95`，理由明确识别学业预警、考勤风险、未解除和风险阈值。
- 独立SQLite按问题原始口径返回104；按生成SQL额外加入的`student.status='active'`同样返回104；满足其余条件但非active的记录为0。因此额外条件是源码/SQL直接可见的潜在跨数据集口径风险，但本次没有改变结果，不能写成已发生功能错误。
- Debug检索命中`academic_warning/student/attendance/score/teaching_class/enrollment`等表，预览实际包含`warning_type/risk_score/resolved`。

#### 结论、状态与后续边界

- ISSUE-018首次33分是真实发生的裁判假阴性，不能删除旧证据；但相同环境同题连续三轮均92～93，另一冷门题96，未形成稳定复现。
- 当前证据支持“外部裁判模型偶发波动”，不支持检索字段缺失、上下文截断或稳定Prompt缺陷。查询SQL与结果始终正确，故归类为非阻塞项并暂不修改代码。
- 按准则第12条，不扩大Schema、不重写裁判Prompt、不增加问题硬编码、不为了单次分数继续无限优化。若以后上下文完整时连续稳定低分，或额外在读条件在其它数据源实际改变答案，再登记新证据并重新申请。
- 本轮没有新增或修改pytest；上一次完整回归仍为97/97。本条验证数量是4次真实模型问数和对应只读数据库/检索核验，不与pytest数量相加。
- 精确回退范围：仅恢复ISSUE-018、P-08/P-10和“当前下一步”至本条前文字并删除CHG-20260715-06；不得回退任何业务代码、测试、CHG-20260715-05或更早记录。

### CHG-20260715-07：教学库测试与B同学成果总结

- 批准：用户要求进行P-11下一步内容，并明确批准创建教学测试/工作总结及更新进度、修改记录。
- 新增文件：`TEACHING_TEST_AND_WORK_SUMMARY.md`；更新文件：`PROJECT_PROGRESS.md`、`PROJECT_CHANGES.md`。
- 未修改范围：`INITIAL_PROJECT_EVALUATION.md`、`README.md`、业务代码、前端代码、Prompt、测试、数据库、配置、依赖和环境均未修改。

#### 总结文件内容与证据来源

- 第一至二节根据README和已实际检查的教学库整理项目定位、17表教学数据及当前功能模块；没有把README声明的可选能力写成已实际通过。
- 第三节按“测试优化+功能辅助”分工映射B同学的功能测试、智能问数、SQL安全、用例整理、提示词/页面优化和协助修复成果；同时明确原始主体功能仍属于原项目，不改变`INITIAL_PROJECT_EVALUATION.md`责任边界。
- 第四节记录Windows、`.venv`、Uvicorn、SQLite、DashScope/Qwen、local检索和浏览器验收环境，并保留实事求是的三类证据区分。
- 第五节通过实际执行`pytest --collect-only -q -p no:cacheprovider`重新核对97项：认证35、数据维护9、评测器6、治理3、裁判4、检索1、角色权限11、驾驶舱28；完整运行结果沿用已记录的`97 passed, 4 warnings in 25.38s`，本条没有伪造或重复执行完整pytest。
- 第六至八节从实际模型、API、SQLite、浏览器和测试记录整理正面、反面、边界用例，包括8/8教学评测、五角色范围、危险SQL拒绝、200行、超时、0值、专业开课口径和裁判波动。
- 第九节按问题范围列出最小修正及主要文件，详细代码级变化继续引用`PROJECT_CHANGES.md`，没有在总结中用功能摘要替代原详细记录。
- 第十节保留ISSUE-004/005/010/011、专业映射、裁判波动和BIRD等待项，区分“后续必须”“当前不阻塞”“未经验证”。
- 第十一至十二节给出课程演示顺序和小学期大作业交付评价，明确不宣称生产部署、server检索或BIRD全量已通过。

#### 进度变化、验证与回退

- `PROJECT_PROGRESS.md`将P-09教学库优化和P-11成果整理标为已完成；P-12仍保持待数据，没有因为生成总结而标记BIRD完成。
- 本条是文档变更，没有运行完整pytest、模型查询或浏览器测试；只读执行的测试收集结果为97，与上一次完整97/97一致。
- 文档检查应确认总结文件存在、章节完整、P-09/P-11状态一致，并执行`git diff --check`；不把文档检查写成业务回归。
- 潜在影响仅为新增课程交付总结和进度状态；不改变运行行为。
- 精确回退范围：删除`TEACHING_TEST_AND_WORK_SUMMARY.md`，恢复P-09/P-11和“当前下一步”至本条前文字，并删除CHG-20260715-07；不得回退`INITIAL_PROJECT_EVALUATION.md`、CHG-20260715-06及更早代码、测试或记录。

### CHG-20260715-08：项目修改记录简化版

- 批准：用户明确要求新增项目修改记录简化版，包含历次问题修改目录、编号/时间/问题/内容正文，以及最终修改原文件和新增文件清单。
- 新增文件：`PROJECT_CHANGES_SUMMARY.md`；同步更新`PROJECT_PROGRESS.md`的P-11成果和审阅入口；本条写入`PROJECT_CHANGES.md`保持修改可追踪。
- 未修改范围：业务代码、前端代码、Prompt、测试、数据库、配置、依赖、`README.md`、`INITIAL_PROJECT_EVALUATION.md`和`TEACHING_TEST_AND_WORK_SUMMARY.md`均未修改。

#### 简化版结构和筛选规则

- 第一节列出13个实际问题修改目录，只收录修改了代码、Prompt或测试来解决问题的CHG条目。
- 第二节每条固定使用“编号、修改时间、解决的问题、修改内容”四项，内容压缩为功能级摘要；详细实现统一指向`PROJECT_CHANGES.md`，不复制函数级长记录。
- 第三节明确排除纯文档、BIRD标记、只读API测试、ISSUE-018不修改结论和成果整理，避免把“发现或记录问题”误写成“已修改问题”。
- 第四节依据当前`git status --short`列出19个被修改的原文件，为每个文件标注问题修改编号和最终作用。
- 第五节列出12个新增文件，包括6个新增测试、原始评价、三份管理记录、教学成果总结和本简化版；管理记录使用“基础记录/随CHG同步”说明，避免伪造不存在的单一创建编号。
- 第六节说明简化版、完整修改记录、问题记录、进度表和成果总结的用途分工。

#### 验证、影响与回退

- 本条是文档整理，不修改或运行项目行为；验证范围为文件存在、目录锚点、13个问题条目、原文件/新增文件清单、敏感信息扫描和`git diff --check`。
- 潜在影响仅为新增快速查阅入口和P-11描述变化；完整修改记录仍是故障归因和精确回退的唯一详细依据。
- 精确回退范围：删除`PROJECT_CHANGES_SUMMARY.md`，恢复P-11和“当前下一步”对应文字，并删除CHG-20260715-08；不得回退任何业务代码、测试、问题记录、CHG-20260715-07或更早内容。

## 已回退事项

- 2026-07-13：此前未经确认产生的评测、数据源及测试修改已全部回退；回退后 Git 工作区恢复干净。
