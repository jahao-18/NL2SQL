# NL2SQL 教学数据智能问数平台

这是一个基于 **FastAPI + LangChain + 通义千问 Qwen + SQLite/PostgreSQL** 的自然语言问数系统。用户用中文提问，系统自动选择数据源、检索相关 Schema、生成只读 SQL、执行查询，并把结果、SQL、可信度评估和治理建议展示在前端工作台。

当前仓库默认包含一套模拟教学数据 `data/teaching.db`，clone 后安装依赖、配置 DashScope API Key 即可启动默认演示。

## 主要能力

- **自然语言转 SQL**：中文问题自动生成 `SELECT` SQL，支持多表 JOIN、追问、结果表格展示。
- **教学数据演示库**：内置学生、教师、课程、成绩、考勤、作业、评价、学业预警、奖学金等模拟数据。
- **角色权限演示**：内置管理员、教务、学院、教师、学生等角色，不同角色看到不同业务域、表和字段。
- **Schema 知识增强**：结合数据库结构、业务词表 `data/glossaries/`、结构化 Schema 画像 `data/schema_profiles/`。
- **多路检索**：本地模式使用向量、BM25、关系图谱；server 模式可接 Milvus、Elasticsearch、PostgreSQL/pgvector。
- **可信度评估**：查询成功后后台异步评估结果完整度和 SQL/结果匹配度。
- **数据治理工作台**：支持 Schema 画像编辑、版本发布/回滚、低可信结果复核队列、反馈沉淀和示例维护。
- **数据接入与维护**：支持在页面中测试连接、注册 SQLite、导入 CSV/DB 文件，并对开启 `writable` 的 SQLite 源做受控增删改和审计。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI, Uvicorn |
| LLM | LangChain, DashScope/Qwen |
| 数据库 | SQLite, PostgreSQL |
| SQL 解析与保护 | SQLAlchemy, sqlparse |
| 检索 | numpy, rank-bm25, networkx；可选 Milvus, Elasticsearch, pgvector |
| 配置 | pydantic-settings, `.env`, `data_sources.yaml` |
| 前端 | 原生 HTML/CSS/JavaScript |

## 目录结构

```text
NL2SQL/
├─ app/
│  ├─ main.py                  # FastAPI 入口，挂载 API 和静态前端
│  ├─ service.py               # 问数主流程：路由、Schema、检索、生成、校验、执行、评估
│  ├─ api/
│  │  ├─ routes.py             # 核心问数、认证、Schema、画像、反馈、示例 API
│  │  ├─ governance.py         # 治理复核队列 API
│  │  └─ data_access.py        # 数据接入与受控维护 API
│  ├─ core/
│  │  ├─ config.py             # 环境变量配置
│  │  ├─ data_sources.py       # data_sources.yaml 加载和只读连接管理
│  │  ├─ business_domains.py   # 角色、权限、字段限制和行级提示
│  │  ├─ schema.py             # Schema 读取、业务词表、画像、枚举发现
│  │  ├─ schema_profile.py     # Schema 画像、质量报告、版本发布/回滚
│  │  ├─ chain.py              # Qwen 调用、SQL 生成和修复
│  │  ├─ validator.py          # SQL 安全校验
│  │  ├─ executor.py           # 只读执行器和超时控制
│  │  ├─ judge.py              # 可信度评估
│  │  ├─ data_access.py        # 数据源导入、表维护、审计日志
│  │  └─ retrieval/            # 多路 Schema linking 检索
│  ├─ models/schemas.py        # Pydantic 模型
│  └─ static/                  # 前端页面、样式和交互脚本
├─ data/
│  ├─ teaching.db              # 默认模拟教学库
│  ├─ glossaries/teaching.md   # 教学库业务词表
│  ├─ schema_profiles/         # 结构化 Schema 画像
│  └─ examples/                # Few-shot 示例
├─ prompts/                    # SQL、修复、路由、评估、查询扩展 prompt
├─ scripts/                    # 数据生成、评测、服务验证、局域网启动脚本
├─ tests/                      # 权限和治理测试
├─ data_sources.yaml           # 数据源注册表
├─ docker-compose.yml          # 可选 server 检索组件
└─ requirements.txt
```

## 快速启动

### 1. 克隆并安装依赖

```powershell
git clone https://github.com/jahao-18/NL2SQL.git
cd NL2SQL

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 配置 `.env`

复制示例配置：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，至少填入：

```env
DASHSCOPE_API_KEY=sk-你的密钥
```

可选模型配置：

```env
QWEN_MODEL=qwen3.7-plus
JUDGE_MODEL=qwen3.6-plus
ROUTER_MODEL=qwen-turbo
```

> 默认 `RETRIEVAL_BACKEND=local`，不需要 Docker。DashScope API Key 是问数、路由、查询扩展和评估功能的核心依赖。

### 3. 启动服务

```powershell
uvicorn app.main:app --reload
```

访问：

- 前端：<http://127.0.0.1:8000/>
- Swagger：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

Windows 下也可以使用局域网启动脚本：

```powershell
.\scripts\start_lan_server.ps1
```

脚本会监听 `0.0.0.0:8000`，并把日志写到 `uvicorn-lan.combined.log`。该日志已被 `.gitignore` 忽略。

## 默认登录账号

这是演示系统，内置账号密码用于角色权限体验。默认密码均为 `123456`。

| 用户名 | 角色 |
|---|---|
| `admin` | 校级管理员 |
| `jwc` | 教务处老师 |
| `college` | 学院负责人 |
| `teacher` | 任课教师 |
| `student` | 学生用户 |

登录后可以在前端切换业务域、问数、查看教学仪表盘、维护知识库和使用数据接入功能。用户修改后的密码会保存到本地 `data/auth_passwords.json`，该文件不建议提交。

## 数据源说明

数据源在项目根目录的 `data_sources.yaml` 中注册。默认第一个源是内置教学库：

```yaml
sources:
  - name: teaching
    label: 教学数据管理平台 (SQLite)
    url: sqlite:///data/teaching.db
    glossary: data/glossaries/teaching.md
    schema_profile: data/schema_profiles/teaching.yaml
```

`data/teaching.db` 是模拟数据，已经纳入仓库。clone 后无需额外生成即可使用默认演示。

### BIRD 数据集

`data_sources.yaml` 中还保留了若干 BIRD benchmark 示例源，路径形如：

```text
data/bird/dev_databases/<db>/<db>.sqlite
```

这些原始数据库体积较大，未放入 Git 仓库，`data/bird/` 也被 `.gitignore` 忽略。缺少 BIRD 数据不会影响默认教学库启动；只有当你手动选择或评测 BIRD 数据源时才需要下载并放到对应目录。

如果要重新生成 BIRD 数据源配置，可参考：

```powershell
python scripts/eval_bird.py --bird-dir <你的BIRD数据目录> --gen-sources
```

## 连接自己的数据库

编辑 `data_sources.yaml`，新增 SQLite 或 PostgreSQL 数据源：

```yaml
sources:
  - name: my_sqlite
    label: 我的 SQLite
    url: sqlite:///data/my.db
    glossary: data/glossaries/my_sqlite.md
    schema_profile: data/schema_profiles/my_sqlite.yaml

  - name: prod_pg
    label: 业务 PostgreSQL
    url: postgresql+psycopg://readonly_user:password@127.0.0.1:5432/mydb
    glossary: data/glossaries/prod_pg.md
    schema_profile: data/schema_profiles/prod_pg.yaml
```

建议：

- 真实业务库使用只读账号。
- 为每个源补充 `glossary`，写业务术语、枚举含义、口径和派生指标。
- 为复杂库补充 `schema_profile`，写表粒度、默认过滤、人工 JOIN、字段语义、敏感字段和指标。
- 改完数据源、prompt、词表或画像后重启 Uvicorn，避免缓存仍使用旧内容。

## 数据接入与维护

前端“数据维护”页面对应 `/api/data-access/*`。

能力包括：

- 查看已注册数据源状态。
- 测试 SQLAlchemy URL 连接。
- 注册本地 SQLite 文件。
- 上传 CSV 并转成托管 SQLite 数据源。
- 上传 `.db/.sqlite/.sqlite3` 文件并注册。
- 扫描表结构、分页查看表数据。
- 对 `writable: true` 的 SQLite 源执行受控新增、更新、删除。
- 将变更审计写入 `data/audit/data_change_logs.jsonl`。

相关运行时目录均已忽略：

```text
data/uploads/
data/managed/*.db
data/audit/
```

## Schema 画像与治理

`data/schema_profiles/<source>.yaml` 用来沉淀结构化知识。系统会把这些信息用于前端展示、检索、prompt 注入和 SQL 校验。

常见内容：

- 表的业务名和一行数据代表什么。
- 默认时间字段和默认过滤条件。
- 字段中文名、语义类型、枚举、单位、默认聚合方式。
- 敏感字段、废弃字段、禁用字段。
- 手工 JOIN 关系。
- 业务指标定义。

前端支持画像编辑、质量检查、版本发布、版本回滚。治理队列支持把用户反馈、低可信查询和发布审核沉淀成待处理事项。

治理数据默认写入：

```text
data/governance/
data/feedback/
data/schema_profiles/.versions/
```

其中运行时反馈和治理目录被 ignore，画像版本目录是否提交取决于你的发布策略。

## 检索模式

### local 模式

默认模式，无需 Docker：

```env
RETRIEVAL_BACKEND=local
```

使用：

- `numpy` 向量相似度
- `rank-bm25` 关键词召回
- `networkx` 关系图谱

适合本地开发、默认教学库和轻量演示。

### server 模式

适合更大规模的库，使用 Milvus、Elasticsearch 和 PostgreSQL/pgvector：

```powershell
docker compose up -d --build
```

然后在 `.env` 中开启：

```env
RETRIEVAL_BACKEND=server
ES_URL=http://localhost:9200
MILVUS_URI=http://localhost:19530
PG_DSN=postgresql://nl2sql:nl2sql@localhost:5433/nl2sql_retrieval
```

验证：

```powershell
python scripts/verify_server_backend.py
```

说明：

- `docker-compose.yml` 中的 MinIO/PostgreSQL 密码是本地演示默认值，不要直接用于公网生产。
- Elasticsearch 镜像会构建 IK 中文分词插件，因此首次启动建议带 `--build`。
- server 组件不可用时，系统会尽量跳过对应检索路，回退到可用路径或完整 DDL。

## REST API 概览

| API | 说明 |
|---|---|
| `GET /api/health` | 健康检查 |
| `GET /api/auth/options` | 演示账号和角色选项 |
| `POST /api/auth/login` | 登录 |
| `GET /api/sources` | 数据源列表 |
| `GET /api/schema?source=teaching` | Schema 和字段元数据 |
| `POST /api/ask` | 自然语言问数 |
| `POST /api/judge` | 获取异步可信度评估 |
| `POST /api/debug/retrieval` | 查看检索上下文 |
| `GET/PUT /api/profile` | Schema 画像读取和保存 |
| `GET /api/profile/versions` | 画像版本列表 |
| `POST /api/profile/publish` | 发布画像版本 |
| `POST /api/profile/rollback` | 回滚画像版本 |
| `GET/POST/DELETE /api/feedback` | 用户反馈 |
| `GET/POST/DELETE /api/examples` | Few-shot 示例 |
| `/api/governance/*` | 治理复核队列 |
| `/api/data-access/*` | 数据接入与受控维护 |

`POST /api/ask` 示例：

```json
{
  "question": "各学院平均分和挂科率分别是多少？",
  "history": [],
  "source": "teaching",
  "current_source": "teaching",
  "user_glossary": [],
  "few_shots": []
}
```

## 常用配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `DASHSCOPE_API_KEY` | 空 | 必填，DashScope API Key |
| `QWEN_MODEL` | `qwen-max` | 主 SQL 生成模型 |
| `JUDGE_MODEL` | `qwen-plus` | 可信度评估模型 |
| `ROUTER_MODEL` | `qwen-turbo` | 数据源路由和查询扩展模型 |
| `MAX_ROWS` | `200` | 单次最多返回行数 |
| `QUERY_TIMEOUT_SECONDS` | `5` | SQL 执行超时秒数 |
| `DATA_SOURCES_FILE` | `data_sources.yaml` | 数据源配置文件路径 |
| `JUDGE_ENABLED` | `true` | 是否启用异步可信度评估 |
| `JUDGE_FALLBACK_SECONDS` | `12` | 评估模型超时后的规则兜底秒数 |
| `RETRIEVAL_ENABLED` | `true` | 是否启用 Schema linking |
| `RETRIEVAL_BACKEND` | `local` | `local` 或 `server` |
| `RETRIEVAL_TOP_TABLES` | `8` | 检索保留相关表数量 |
| `RETRIEVAL_TOP_K` | `30` | 每路召回数量 |
| `RETRIEVAL_COL_CAP` | `25` | 宽表列裁剪上限 |
| `RETRIEVAL_QUERY_EXPANSION` | `true` | 是否用快模型扩展检索 query |
| `PREWARM_ENABLED` | `true` | 启动后后台预热检索器 |

## 安全边界

- 问数执行链路只允许单条 `SELECT`。
- SQLite 会尽量通过只读 URI 打开；PostgreSQL 会设置会话级只读。
- SQL 校验器会拦截危险关键字、非法表引用、禁用字段和越权字段。
- 查询结果强制限制行数并设置执行超时。
- 前端导出 CSV 时会处理 Excel 公式注入风险。
- 数据维护接口只允许有权限的演示角色访问，并且只有显式 `writable: true` 的 SQLite 源可写。

## 测试与检查

```powershell
python -m compileall -q app tests scripts
python -m pytest
```

如果只想确认应用能导入：

```powershell
python -c "import app.main; print('app import ok')"
```

## 提交前检查

仓库已经忽略本地敏感或运行时文件：

```text
.env
.claude/*.local.json
.venv/
.idea/
uvicorn*.log
data/uploads/
data/managed/*.db
data/audit/
data/governance/
data/retrieval_index/
data/bird/
volumes/
```

上传 GitHub 前建议确认：

```powershell
git status --short
git ls-files --others --exclude-standard
```

不要提交真实 `.env`、真实业务数据库、运行日志、虚拟环境和 Docker volume。

## 已知限制

- LLM 生成 SQL 不是确定性程序，复杂问题仍可能需要业务词表、画像或示例来约束。
- 默认账号密码仅用于演示，不能用于生产。
- BIRD 原始数据库未内置，需要自行下载。
- 修改数据源、prompt、词表和画像后通常需要重启服务清理缓存。
- server 检索依赖 Docker 组件，组件未就绪时会自动降级，但效果会下降。

## 许可

本项目为作者个人项目，保留所有权利。未经作者书面许可，任何个人或组织不得将本项目或其衍生作品用于商业用途、出售、再授权、再分发或作为商业产品/服务的一部分。

允许在遵守上述限制的前提下，仅出于学习、阅读和非商业研究目的查看代码。接入真实业务数据前，请自行补充认证、审计、权限、脱敏和部署安全策略。
