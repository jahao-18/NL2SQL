# NL2SQL

> **一句话**:输入"广东省 2025 年销量前 5 的电子产品",系统帮你写 SQL、查 SQLite、把结果按表格返回 —— 全程不用碰 SQL。
>
> 基于 **LangChain + FastAPI + 通义千问(Qwen)** 的极简自然语言查数据库系统。
> 设计目标:把"NL→SQL→执行→展示"的完整闭环做得**安全、可解释、好调试**,而不是堆功能。

---

## 它能做什么

- 用中文/自然语言提问 → 自动生成 SQLite `SELECT` 并执行,返回行列结果
- 支持多表 JOIN 推理(示例库故意把 `products.category_id` 设成 FK,逼 LLM 学会 JOIN `categories`)
- **多轮追问**:"北京有多少用户?" → "他们里 60 岁以上的呢?" → "再按性别分组"
- 失败自动回修:校验/执行报错时把"上次 SQL + 错误"丢回 LLM,最多重试 2 轮
- 前端表头**双行显示**:别名(`product_name`) + 源字段(`p.name`),你能一眼看出每列来自哪个表
- 结果超 200 行**显式提示"已截断"**,避免误判
- 模糊提问主动推导("最贵的用户" → 按消费总额排序),不存在的字段才回退

## 它不会做什么(设计边界)

- 只跑 `SELECT`。`INSERT/UPDATE/DELETE/DROP/...` 一律在 prompt + 校验器 + 只读连接三层拦截
- 不支持自定义函数注册、不调用外部 API
- 不保存服务端会话:历史轮次由前端 localStorage 持有,后端无状态

> 注:大库可选开启**四路 schema linking 检索**(向量 + 关键字 + 业务术语 + 关系图谱),见下文「知识库检索」一节。默认 `local` 后端纯进程内,无外部依赖。

---

## 数据流(一次提问发生了什么)

```
浏览器 (app/static/)
   │  问题 + 最近 N 轮历史 (localStorage)
   │  POST /api/ask
   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  app/service.py  ask()                                              │
│                                                                     │
│  ① schema.load_schema()       读 sqlite_master,拼 DDL + 业务说明   │
│     ─ DDL 里每个字段后跟 -- 中文注释                                │
│     ─ 业务说明:status 取值 / gender 映射 / 省份必须 JOIN addresses │
│                                                                     │
│  ② chain.generate_sql()       LangChain → Qwen 生成 SQL             │
│     ─ system prompt 注入 {schema} + {current_date}                  │
│     ─ history 作为 Human/AI 消息序列塞回上下文                       │
│     ─ ChatTongyi temperature=0                                      │
│                                                                     │
│  ③ validator.validate_and_fix()  四层安检                            │
│     ─ 必须单条 SQL                                                  │
│     ─ 顶层 DML 必须是 SELECT                                        │
│     ─ 禁用关键字黑名单(INSERT/UPDATE/.../REPLACE/...)             │
│     ─ FROM/JOIN 后的表必须在白名单                                  │
│     ─ 强制 LIMIT;超 MAX_ROWS 收紧 → (sql, truncated)                │
│                                                                     │
│  ④ executor.execute()         file:?mode=ro 只读连接 SQLite         │
│     ─ busy_timeout 防长锁                                           │
│     ─ fetchmany(MAX_ROWS)                                           │
│                                                                     │
│  ⑤ sql_meta.extract_column_sources()                                │
│     ─ sqlparse 抽 SELECT 列的源表达式("p.name"),给前端表头第二行   │
│                                                                     │
│  ↻ 失败回到 ②:chain.repair_sql() 带"上次 SQL + 错误"再试,最多 2 轮 │
└─────────────────────────────────────────────────────────────────────┘
   │
   │ JSON 响应
   ▼
浏览器渲染:SQL 框(可复制) + 结果表(双行表头 + NULL/截断标识)
```

---

## 模块职责对照

| 路径 | 角色 |
|---|---|
| `app/main.py` | FastAPI 入口,挂载 `/api/*` 路由 + 静态前端 |
| `app/api/routes.py` | `/health` `/schema` `/ask` 三个端点 |
| `app/service.py` | **业务编排核心**:schema → 生成 → 校验 → 执行 → 回修 → 格式化 |
| `app/core/config.py` | pydantic-settings 读 `.env`,路径常量 |
| `app/core/schema.py` | 从 `sqlite_master` 读 DDL,拼接 + 注入业务说明,带 lru_cache |
| `app/core/chain.py` | LangChain 链:`ChatPromptTemplate` + `ChatTongyi` + 解析器;含 `generate_sql` / `repair_sql` |
| `app/core/validator.py` | SQL 安全校验 + LIMIT 强制/收紧,返回 `(sql, truncated)` |
| `app/core/executor.py` | 只读 SQLite 执行,返回 `(columns, rows, elapsed_ms)` |
| `app/core/sql_meta.py` | sqlparse 抽 SELECT 列源表达式,服务于前端表头 |
| `app/core/formatter.py` | 统一响应字典格式(成功/失败/截断) |
| `app/models/schemas.py` | pydantic 请求/响应模型(`Turn`、`AskRequest`、`AskResponse`、`SchemaResponse`) |
| `app/static/` | 单页前端:`index.html` + `app.js` + `style.css`,Pico.css CDN |
| `prompts/sql_prompt.txt` | **主 prompt**:硬性规则 10 条 + 示例 10 条 |
| `prompts/sql_repair_prompt.txt` | 失败回修 prompt(单轮,无历史) |
| `scripts/seed_db.py` | 生成示例电商数据库(6 表/30000 订单) |
| `tests/test_cases.md` | 手工测试用例集(多表 JOIN / 模糊语义 / 边界等 35 条) |

---

## 关键设计取舍(为什么这么做)

1. **三层防御**(prompt + sqlparse + 只读 URI)
   LLM 不可信。Prompt 第 1 条已禁 INSERT/DELETE,但还是要在 validator 里 token 级检查、在 sqlite_connect 里走 `?mode=ro`。任一层失守,后两层兜底。

2. **业务说明拼到 DDL 后面**(`app/core/schema.py:BUSINESS_NOTES`)
   单看 DDL,LLM 不知道 `status` 的取值是 `'paid'` 还是 `'已支付'`,不知道 `users` 没 province 字段。把这些**取值映射 + 跨表语义**显式写出来,准确率提升明显。

3. **failure-then-repair 而不是 chain-of-thought**
   不让 LLM 一上来就解释"我要怎么写",直接给 SQL,出错时把"错误信息 + 上次 SQL"丢回去修。简单、可观察、不浪费 token。`MAX_REPAIR_ROUNDS=2` 是经验值,再多通常已经没救。

4. **多轮上下文用 ChatPromptTemplate + history,不做总结**
   把过往 `(question, sql)` 当 Human/AI 消息序列塞回,LLM 自己根据"他们""换成..."等代词推理。后端**无状态**,所有历史靠前端 localStorage,服务能力可任意水平扩展。

5. **LIMIT 强制 + 显式截断标识**
   防 LLM 写 `SELECT * FROM orders`(30000 行)拉爆响应。validator 会收紧到 `MAX_ROWS`,响应里带 `truncated=true`,前端打"⚠️ 结果已截断",避免用户误以为是全集。

6. **列源表达式回传前端**
   LLM 起的别名(`negative_review_count`)读起来友好但**丢了来源**。`sql_meta.py` 用 sqlparse 从 SQL 抽 `p.name`、`COUNT(*)` 这些原始表达式,前端表头分两行渲染:别名在上、源字段在下。

7. **prompt 文件外置,不写死在代码里**
   `prompts/sql_prompt.txt` 是普通 txt,改完不用动 Python,重启 uvicorn 即可生效。所有 LLM 行为微调先想"能不能改 prompt 解决"。

---

## 技术栈

| 层 | 选型 |
|---|---|
| Web 框架 | FastAPI + Uvicorn |
| LLM 链路 | LangChain + langchain-community(`ChatTongyi`)|
| LLM 模型 | 通义千问 `qwen-plus`(DashScope)|
| 数据库 | SQLite / PostgreSQL(只读模式) |
| SQL 解析 | sqlparse |
| 知识库检索(可选)| 向量 + 关键字 + 业务术语 + 关系图谱四路;`local` 进程内(numpy / rank_bm25 / networkx)或 `server`(Milvus + Elasticsearch+IK + PostgreSQL/pgvector)|
| 嵌入 | DashScope `text-embedding-v3` |
| 配置 | pydantic-settings + `.env` |
| 前端 | 原生 HTML/JS + Pico.css(CDN) |

---

## 目录结构

```
NL2SQL/
├── app/
│   ├── main.py                  # FastAPI 入口
│   ├── service.py               # 业务编排:schema → LLM → 校验 → 执行 → (回修) → 格式化
│   ├── api/routes.py            # /api/health  /api/schema  /api/ask
│   ├── core/
│   │   ├── config.py            # 环境变量与路径常量
│   │   ├── schema.py            # 从 sqlite_master 加载 DDL + 业务说明
│   │   ├── chain.py             # LangChain 链:生成 SQL + 失败回修
│   │   ├── validator.py         # SQL 安全校验 + LIMIT 强制
│   │   ├── executor.py          # 只读 SQLite 执行器
│   │   ├── sql_meta.py          # 解析 SELECT 列源表达式
│   │   └── formatter.py         # 响应格式化
│   ├── models/schemas.py        # Pydantic 请求/响应模型
│   └── static/                  # 前端(index.html / app.js / style.css)
├── prompts/
│   ├── sql_prompt.txt           # SQL 生成 prompt(含示例 + 多轮规则)
│   └── sql_repair_prompt.txt    # 失败回修 prompt
├── scripts/seed_db.py           # 生成示例电商数据库
├── data/app.db                  # SQLite 数据库(运行 seed 后生成)
├── tests/test_cases.md          # 手工测试用例集
├── requirements.txt
└── 需求.md
```

---

## 环境要求

- Python 3.10+(项目自带的 `.venv` 是 Python 3.14)
- 一个有效的 **DashScope API Key**(申请地址:<https://dashscope.console.aliyun.com/>)

---

## 快速开始

### 1. 准备虚拟环境并安装依赖

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置 API Key

在项目根目录新建 `.env` 文件:

```env
DASHSCOPE_API_KEY=sk-你的密钥
QWEN_MODEL=qwen-plus
DB_PATH=data/app.db
MAX_ROWS=200
QUERY_TIMEOUT_SECONDS=5
```

> 除 `DASHSCOPE_API_KEY` 必填外,其余均有默认值,可不写。

### 3. 生成示例数据库

```powershell
python scripts/seed_db.py
```

预期输出会列出每张表的行数(categories: 7 / users: 1000 / products: ~170 / orders: 30000 / reviews: ~9000 / addresses: ~1500)。

### 4. 启动服务

```powershell
uvicorn app.main:app --reload
```

启动后访问:

- 前端页面:<http://127.0.0.1:8000/>
- API 文档(Swagger UI):<http://127.0.0.1:8000/docs>
- 健康检查:<http://127.0.0.1:8000/api/health>

> 到这一步就能用了 —— 默认 `RETRIEVAL_BACKEND=local`,纯进程内,不需要 docker。
> 想开启大库的高精度检索(下一节)再起 docker。

---

## 知识库检索(四路 schema linking,可选)

大库整库 DDL 又费 token 又稀释信号。开启后,系统针对每个问题**只召回相关的表/列 + 业务规则**喂给 LLM(schema linking),小库自动跳过(整库 DDL 更省事)。

### 四路召回

| 路 | 召回信号 | 后端(server) | 后端(local) |
|---|---|---|---|
| **vector** | 语义相似(列描述/自然名)| Milvus | 进程内 numpy 余弦 |
| **keyword** | BM25 精确词(中文走 IK 分词)| Elasticsearch + analysis-ik | 进程内 rank_bm25 |
| **glossary** | 业务术语/规则(取值映射、JOIN 口径)| PostgreSQL + pgvector | —(仅 server)|
| **graph** | 表关系 / JOIN 路径(补桥接表)| networkx(进程内,两后端共用)||

前三路命中经 **RRF 倒数排名融合**选出相关表,graph 再补连通桥接表与 JOIN 条件。任一后端连不上会**自动跳过该路**,最差回退整库 DDL,不会崩。

### 两种后端

- **`local`(默认)**:全进程内,零外部依赖,开箱即用。向量/关键字用 numpy + rank_bm25。
- **`server`**:接真组件(Milvus + ES + PG),适合大库 / 生产。`glossary` 路仅在此模式启用。

切换:`.env` 里设 `RETRIEVAL_BACKEND=server`。

### 启用 server 后端

1. **装依赖**(`requirements.txt` 已含,`pip install -r` 即可):`pymilvus` / `elasticsearch` / `pgvector`。

2. **起 docker 检索服务**(ES 是含中文分词插件的自定义镜像,**必须带 `--build`**):

   ```powershell
   docker compose up -d --build
   ```

   起的服务:Elasticsearch(`:9200`,含 IK)、Milvus(`:19530`,自带 etcd+minio)、PostgreSQL+pgvector(host **`:5433`**,避开本机已装的 PG)。

3. **`.env` 开开关**:

   ```env
   RETRIEVAL_BACKEND=server
   # 以下均有默认值,一般不用改
   # ES_URL=http://localhost:9200
   # MILVUS_URI=http://localhost:19530
   # PG_DSN=postgresql://nl2sql:nl2sql@localhost:5433/nl2sql_retrieval
   # ES_ANALYZER=ik_max_word          # 索引分词器(搜索用 ik_smart)
   ```

4. **重启 uvicorn** 即可。首次查询某库会建索引(嵌入 + 入库),之后按内容签名命中缓存。

> docker 那层起一次就常驻,平时开发只跑 `uvicorn`。改了 `docker/es/Dockerfile` 才需要再 `--build`。

### 验证真组件生效

```powershell
python scripts/verify_server_backend.py superhero "哪个出版商旗下的超级英雄最多"
```

看输出 `retrievers_used` 里出现 `vector / keyword / glossary / graph`、日志有「…索引已重建/命中缓存」即生效。
(注:BIRD 库 schema 是英文、问题是中文,跨语言 BM25 几乎不命中,`keyword` 常缺席,属正常。)

### 相关配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `RETRIEVAL_ENABLED` | `true` | 总开关,关掉则始终用整库 DDL |
| `RETRIEVAL_BACKEND` | `local` | `local` 进程内 / `server` 真组件 |
| `RETRIEVAL_MIN_DDL_CHARS` | `1500` | 整库 DDL 短于此值不检索(小库全量喂)|
| `RETRIEVAL_TOP_TABLES` | `8` | 融合后保留的相关表数上限(表数 ≤ 此值的库直接跳过检索)|
| `GLOSSARY_TOP_K` | `5` | 术语路每次召回的业务规则条数 |

---

## 连接你自己的数据库

系统通过项目根目录的 `data_sources.yaml` 注册数据源,前端顶部下拉可切换。
当前支持 **SQLite** 和 **PostgreSQL**(只需改 `url`,无需改代码)。

### 1. 编辑 `data_sources.yaml`

```yaml
sources:
  - name: demo_sqlite                     # 内部标识,前端用
    label: 示例电商 (SQLite)               # 下拉显示名
    url: sqlite:///data/app.db            # SQLAlchemy 风格连接串
    glossary: data/glossaries/demo_sqlite.md   # 可选,业务词表

  - name: prod_pg
    label: 生产库 (PostgreSQL)
    url: postgresql+psycopg://readonly_user:password@127.0.0.1:5432/mydb
    glossary: data/glossaries/prod_pg.md
```

### 2. (可选)给新数据库写业务词表

在 `data/glossaries/<name>.md` 写枚举映射、跨表语义、字段口径等。系统会:
- 自动发现**低基数 TEXT 列**的枚举值(扫 `SELECT DISTINCT`,≤20 个 distinct 才注入),不用手写
- **手写词表**用于补充自动发现不到的内容,比如"客单价 = SUM(amount)/COUNT(DISTINCT order_id)"、表间业务关联等

留空文件或不配 `glossary` 字段也能跑,只是模型对该库的业务语义全靠 schema 推断。

### 3. 重启服务

`data_sources.yaml` 在启动时加载,改完需重启 `uvicorn`。前端下拉切换会自动:
- 重新拉取该源的 schema
- 清空 history(跨库历史 SQL 无意义)

### 安全说明

- SQLite 走 `?mode=ro` URI,DB 层强制只读
- PostgreSQL 走 `SET default_transaction_read_only=on`,会话级只读
- 即使 SQL 解析器漏过危险操作,DB 账号层面也会拒绝写

---

## 使用方式

### Web 前端

打开 <http://127.0.0.1:8000/>,在文本框输入问题,点击「查询」或按 Enter。
页面展示:**生成的 SQL**(可复制) + **结果表格**(双行表头:别名 / 源字段) + **耗时**。
底部 `查看数据库表结构` 可展开完整 DDL。

可追问示例:

```
Q1: 北京有多少用户?
Q2: 他们里 60 岁以上有几个?
Q3: 再按性别分组统计
```

「清空会话」可重置上下文。输入框不会因为提交而被清空,可继续编辑。

### REST API

#### `POST /api/ask`

**请求:**
```json
{
  "question": "销量前 5 的商品有哪些?",
  "history": [
    { "question": "上一轮问题", "sql": "上一轮生成的 SQL" }
  ]
}
```

**响应:**
```json
{
  "sql": "SELECT p.name AS product_name, SUM(o.quantity) AS total_sold ... LIMIT 5",
  "columns": ["product_name", "total_sold"],
  "column_sources": ["p.name", "SUM(o.quantity)"],
  "rows": [["iPhone 15", 423], ["..."]],
  "row_count": 5,
  "elapsed_ms": 12,
  "truncated": false,
  "error": null
}
```

字段说明:
- `columns`:SQL 里的别名,前端表头主标题
- `column_sources`:从 SQL parse 出的源表达式,前端表头副标题(与 `columns` 一一对应)
- `truncated`:用户请求的 LIMIT 是否被收紧到 `MAX_ROWS`
- `error`:校验/执行失败的错误信息,成功时为 `null`

#### `GET /api/schema`

返回所有表的 DDL 文本(含业务说明) + `{表名: [列名]}` 白名单。

#### `GET /api/health`

```json
{ "status": "ok" }
```

### curl 示例

```powershell
curl -X POST http://127.0.0.1:8000/api/ask `
  -H "Content-Type: application/json" `
  -d '{"question":"销量前5的商品"}'
```

---

## 示例数据库 Schema

| 表 | 字段 |
|---|---|
| `categories` | id, code, name, description |
| `users` | id, name, gender, age, city, registered_at |
| `products` | id, name, **category_id (FK)**, price, stock |
| `orders` | id, user_id, product_id, quantity, amount, status, created_at |
| `reviews` | id, order_id, user_id, product_id, rating(1-5), comment, created_at |
| `addresses` | id, user_id, province, city, detail, is_default |

注意几个有意设置的"坑"(用来测试 LLM 推理):

- `products.category_id` 是 FK,问"电子产品类目"必须 JOIN `categories`
- `users.city` 与 `addresses.city` 并存,"广东省"只能走 `addresses.province`
- `status` / `gender` 都是英文小写值,prompt 里需告知映射
- `is_default` 是 INT 0/1 不是 BOOL
- `created_at` / `registered_at` 是 ISO8601 文本

### 可玩问题

- `2025 年每个城市的已支付订单总金额,按金额降序`
- `电子产品类目销量前 3 的商品`
- `每个类目销量第一的商品分别是哪个?`(触发窗口函数)
- `平均评分最高的 5 个商品(至少 10 条评价)`
- `广东省有多少用户设置了默认地址?`
- `最贵的用户是谁?`(比喻语义 → 消费总额最高)
- `谁是体重最重的用户?`(字段不存在 → 模型主动回退说明)

更多见 `tests/test_cases.md`。

---

## 安全机制

`app/core/validator.py` 在执行前对 LLM 生成的 SQL 做多道校验:

1. **单语句限制**:`sqlparse` 解析后只允许一条语句
2. **DML 限定**:顶层 DML 必须是 `SELECT`
3. **黑名单关键字**:出现 `INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/ATTACH/PRAGMA/...` 任一即拒绝
4. **表名白名单**:`FROM/JOIN` 后的表必须存在于 `sqlite_master`
5. **强制 LIMIT**:未写 LIMIT 则自动追加 `LIMIT MAX_ROWS`;若 LIMIT 超 `MAX_ROWS` 则收紧并标记 `truncated=True`

`app/core/executor.py` 使用 `file:...?mode=ro` 只读 URI 打开 SQLite,从底层禁止任何写入。

---

## 配置项一览

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `DASHSCOPE_API_KEY` | — | **必填**,DashScope 控制台获取 |
| `QWEN_MODEL` | `qwen-plus` | 通义千问模型名(也可换 `qwen-max` / `qwen-turbo`)|
| `DB_PATH` | `data/app.db` | SQLite 路径(相对项目根目录)|
| `MAX_ROWS` | `200` | 单次查询最大返回行数(同时也是 LIMIT 上限)|
| `QUERY_TIMEOUT_SECONDS` | `5` | SQLite 连接/锁超时秒数 |

代码侧常量(改完需重启):

| 常量 | 位置 | 默认 |
|---|---|---|
| `MAX_REPAIR_ROUNDS` | `app/service.py` | `2`(回修最多重试 2 轮)|
| `MAX_HISTORY_TURNS` | `app/service.py` | `5`(后端只取最近 5 轮历史)|
| `MAX_HISTORY_TURNS` | `app/static/app.js` | `5`(前端发送最近 5 轮)|

---

## 修改入口指南(想做 X,看哪)

| 想做的事 | 看哪 |
|---|---|
| 让 LLM 学会一类新提问 | 在 `prompts/sql_prompt.txt` 加一条**示例**,通常比改规则有效 |
| 改"金额默认 paid"这类业务默认值 | `prompts/sql_prompt.txt` 硬性规则段 |
| 加新表 | 改 `scripts/seed_db.py` 重新 seed;`schema.py` 自动从 `sqlite_master` 读 |
| 告诉 LLM 新表的取值映射 | `app/core/schema.py` 的 `BUSINESS_NOTES` 常量 |
| 允许/禁止某个 SQL 关键字 | `app/core/validator.py` 的 `FORBIDDEN_KEYWORDS` 集合 |
| 调 LIMIT 上限 | `.env` 的 `MAX_ROWS` |
| 换 LLM 模型 | `.env` 的 `QWEN_MODEL`;换厂商需改 `chain.py` 里的 `ChatTongyi` |
| 加 API 字段 | 改 `app/models/schemas.py` + `formatter.py` + `service.py` 三处 |
| 改前端表格样式 | `app/static/style.css` + `app.js` 的 `renderTable` |

---

## 已知限制

- LLM 行为非确定:同一问题多次提问可能 SQL 不同;`temperature=0` 已尽力,但不保证
- 多轮对话超过 5 轮会丢失更早的上下文(前端 localStorage 也仅保留 ~10 轮)
- 长追问链条上,LLM 偶尔会引入历史中未提及的具体值(已在 prompt 第 10 条防,仍可能漏)
- CTE / WITH 子句的别名暂未被表白名单 explicitly 识别(写 `WITH x AS (...) SELECT * FROM x` 可能被拒);如需要请改 `validator._check_tables_in_whitelist`
- `REPLACE` 字符串函数与 `INSERT OR REPLACE` 共享关键字,被一刀切禁了;如需用 `REPLACE(s, a, b)` 字符串替换,需要在 validator 里精确化判断

---

## 常见问题

**Q: 启动报 `DASHSCOPE_API_KEY 未配置`?**
A: 在项目根目录建 `.env` 文件并填入 key,或直接 `set DASHSCOPE_API_KEY=...` 设置环境变量。

**Q: 报「数据库不存在」?**
A: 先运行 `python scripts/seed_db.py` 生成示例数据库。

**Q: 想换成自己的数据库?**
A: 把 `.env` 里 `DB_PATH` 指向你的 `.db` 文件。建议在 DDL 里给每个字段加 `-- 注释`(LLM 会读到),并在 `app/core/schema.py:BUSINESS_NOTES` 写一段值域/跨表说明,效果立竿见影。

**Q: 修改了 schema 后查询还在用旧 schema?**
A: schema 加载有进程级 lru_cache,重启 uvicorn 即可。代码侧可调 `app.core.schema.clear_cache()`。

**Q: 想看 LLM 生成了什么 SQL / 失败原因?**
A: 看终端日志,`service.py` 会记录 `ask ok` / `SQL 校验失败` / `SQL 执行失败` 三类。也可直接看前端「生成的 SQL」框。

**Q: 想关掉/调高回修重试?**
A: 改 `app/service.py` 顶部的 `MAX_REPAIR_ROUNDS`(0 即关闭)。

---

## 许可

仅供学习与个人项目使用。
