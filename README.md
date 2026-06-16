# NL2SQL

> **一句话**:用中文提问"梅西的惯用脚是哪只 / 广东 2025 年销量前 5 的电子产品",系统自动判断查哪个库、写 SQL、执行、按表格返回,并给出一个可信度评分 —— 全程不用碰 SQL,也不用先选数据库。
>
> 基于 **LangChain + FastAPI + 通义千问(Qwen)** 的自然语言查数据库系统。
> 设计目标:把"NL → 选库 → 检索 schema → 生成 SQL → 执行 → 展示 → 评估"的完整闭环做得 **安全、可解释、好调试、面向业务用户**,而不是堆功能。

---

## 它能做什么

- **中文提问直接出结果**:自然语言 → 生成 `SELECT` → 执行 → 行列表格,支持多表 JOIN 推理
- **数据源自动路由**:挂多个数据库时,后端按问题(+ 会话上下文)自动判断该查哪个库,前端不用先选;也可手动锁库
- **四路知识库检索(schema linking)**:大库/宽表只把**相关的表与字段 + 业务规则**喂给 LLM,而不是整库 DDL —— 提准确率、省 token(向量 + 关键字 + 业务术语 + 关系图谱四路融合)
- **结构化 Schema 画像**:按库维护表粒度、默认过滤、人工 JOIN 关系、字段语义、指标口径和字段可用性;这些知识会同时进入 prompt、检索索引、关系图谱和安全校验
- **查询侧术语扩展**:中文问题自动补英文列名别名(惯用脚 → `preferred_foot`),缓解"中文问题对英文列名"的跨语言召回短板
- **多轮追问**:"北京有多少用户?" → "他们里 60 岁以上的呢?" → "再按性别分组",指代/省略自动理解
- **结果可信度评估(后台异步)**:每次查询后另一个 LLM 当裁判,给「数据完整度 + 结果匹配度」打分,合成 0-100% 可信度勋章。**结果先返回、后台线程评估、前端短轮询补上勋章**,不阻塞看结果;评语用**业务语言**(不堆表名列名),面向不懂 SQL 的业务用户
- **查询进度条**:点击查询后按真实流水线阶段(判断数据源 → 检索 → 生成 SQL → 执行)显示进度
- **推荐问法 / 查询历史 / 结果操作**:前端提供按数据源切换的推荐问法、可见查询历史;结果表支持复制、下载 CSV、保存查询和简单柱状图预览
- **我的术语表**:用户可给每个库补充「业务术语 / 取值映射」(如 `交易后出账 = frequency 的 'POPLATEK PO OBRATU'`),按库存浏览器、提问自动带上 —— 解决模型猜不出加密取值的问题
- **派生指标 / 计算口径**:业务方用**纯自然语言**定义指标(`客单价 = 总消费金额 / 订单数量`,不写任何列名),用户问"客单价是多少"时,LLM 自动把概念匹配到字段、按公式计算;大库走检索时还会把公式操作数对应的列主动召回进上下文(详见下文)
- **失败自动回修**:校验/执行报错时把"上次 SQL + 错误"丢回 LLM,最多重试 2 轮
- **信息不足主动澄清**:口径二义("最有价值的客户")时反问一次,而非硬猜
- **多层安全与资源保护**:prompt 约束 + sqlparse 递归表白名单 + 只读连接 + 强制/收紧 LIMIT + 查询超时;只跑 `SELECT`

## 它不会做什么(设计边界)

- 只跑 `SELECT`,`INSERT/UPDATE/DELETE/DROP/...` 三层拦截
- 不保存服务端会话:历史轮次由前端 localStorage 持有,后端无状态
- 评估分是 AI **估算**的可信度参考,非真值;裁判不碰数据库、没有标准答案

---

## 数据流(一次提问发生了什么)

```
浏览器 (app/static/)
   │  问题 + 最近 N 轮历史(localStorage)+ 该库自定义术语
   │  POST /api/ask                                    （前端同时显示进度条）
   ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  app/service.py  ask()                                                       │
│                                                                              │
│  ① source_router.route()   未手动锁库时,快模型(qwen-turbo)按问题+历史+当前 │
│                            库判断查哪个数据源(追问留原库 / 换话题切新库)   │
│                                                                              │
│  ② schema.load_schema()    读 DDL + 业务词表 + 结构化 schema 画像 + 字段取值 │
│                                                                              │
│  ③ retrieval.retrieve_context()  仅"宽/大库"触发:四路召回 → RRF 融合 →      │
│                            选表 + 列级裁剪 → 精简 schema 上下文(替代整库DDL）│
│                            小库自动跳过、用整库 DDL                          │
│                                                                              │
│  ④ chain.generate_sql()    LangChain → Qwen(qwen3.7-plus)生成 SQL          │
│                            system prompt 注入 {schema}+{dialect}+{date}       │
│                            history 作为 Human/AI 消息序列;可输出 CLARIFY     │
│                                                                              │
│  ⑤ validator.validate_and_fix()  单条/只读/黑名单/递归表白名单/强制 LIMIT  │
│                                                                              │
│  ⑥ executor.execute()      只读连接执行,DB 侧超时保护,fetchmany(MAX_ROWS)   │
│                                                                              │
│  ⑦ judge.stash()           入队后台评估、立即返回 judge_id(见下)           │
│                                                                              │
│  ↻ 失败回到 ④:chain.repair_sql() 带"上次 SQL + 错误"再试,最多 2 轮         │
└────────────────────────────────────────────────────────────────────────────┘
   │ JSON(含 sql / 结果 / 实际数据源 / judge_id)
   ▼
浏览器:进度条补满 → 渲染 SQL + 结果表/图表 → 凭 judge_id 轮询 /api/judge 补可信度勋章
```

---

## 多数据源与自动路由

系统通过项目根目录的 `data_sources.yaml` 注册多个数据源(SQLite / PostgreSQL),`app/core/source_router.py` 让快模型按问题自动选库:

- **自动模式(默认)**:前端「🤖 自动识别」。后端**每轮**按"问题 + 最近提问 + 当前会话库"重新路由 —— 追问("再按城市拆分")留在原库,换话题("超级英雄…")切到对应库。路由拿不准时:已在某库则保持,否则反问用户。
- **手动锁库**:前端下拉选具体库 → 硬锁,跳过路由。
- 路由用独立的快模型 `ROUTER_MODEL`(默认 `qwen-turbo`),与主生成分开 —— 选库是分类小任务,无需主力模型,降低延迟。**路由只决定查哪个库,不影响库内的表/列召回。**

切库会清空前端历史(跨库历史 SQL 无意义),并刷新该库的 schema 面板与术语表。

---

## 结构化 Schema 画像(P0/P1 知识层)

除数据库 DDL 和自由文本词表外,系统还支持给每个数据源配置一个结构化 `schema_profile`。它面向产品和数据治理,把最容易影响 SQL 正确率的知识显式沉淀下来:

- **表粒度(P0)**:说明一行代表什么,避免 JOIN 后重复计数。例如 `orders` 一行是一笔订单,`addresses` 一行是一条地址且用户一对多。
- **默认过滤(P0)**:把业务默认口径写清楚。例如销售额/销量默认 `orders.status = 'paid'`,默认地址默认 `addresses.is_default = 1`。
- **人工 JOIN 关系(P0)**:生产库常常没有外键,可以手工声明 `orders.user_id = users.id` 这类关系,供关系图谱和 JOIN 渲染使用。
- **字段业务语义(P1)**:中文名、描述、枚举值、单位、语义类型、默认聚合方式,用于前端展示、召回索引和 prompt。
- **字段可用性(P1)**:可标记 `sensitive / deprecated / enabled=false`;敏感/禁用/废弃字段不会进检索索引,即使模型写进 SQL 也会被校验器拒绝。
- **结构化指标(P1)**:把客单价、件单价、复购用户数等指标按公式、默认过滤、默认时间字段维护,比散落在 prompt 里更可治理。

数据源通过 `data_sources.yaml` 关联 profile:

```yaml
sources:
  - name: demo_sqlite
    label: 示例电商 (SQLite)
    url: sqlite:///data/app.db
    glossary: data/glossaries/demo_sqlite.md
    schema_profile: data/schema_profiles/demo_sqlite.yaml
```

profile 示例:

```yaml
tables:
  orders:
    business_name: 订单
    grain: 一行代表一笔订单,包含一个商品和购买数量。
    default_time_column: created_at
    default_filters:
      - status = 'paid'

columns:
  orders:
    amount:
      business_name: 订单金额
      semantic_type: metric
      default_aggregation: sum
      unit: 元
    status:
      business_name: 订单状态
      semantic_type: dimension
      enum_values:
        - pending=待支付
        - paid=已支付
        - cancelled=已取消
        - refunded=已退款
      default_filter: status = 'paid'

relations:
  - left: orders.user_id
    right: users.id
    type: many_to_one
    description: 每笔订单属于一个用户。

metrics:
  客单价:
    formula: 已支付订单的订单金额求和 / 已支付订单数量
    default_filters:
      - orders.status = 'paid'
    default_time_column: orders.created_at
```

运行时影响:

- `schema.py` 会把 profile 渲染进 LLM 上下文,并合并到 `/api/schema` 的字段元数据。
- `retrieval/atoms.py` 会把字段中文名、描述、枚举、语义类型纳入向量/关键词索引;敏感/禁用字段直接排除。
- `retrieval/graph.py` 会把人工关系并入关系图,用于结构召回和 JOIN 路径提示。
- `validator.py` 会拦截 profile 中标记不可用于问数的字段。

---

## 知识库检索(四路 schema linking)

大库/宽表整库 DDL 又费 token 又稀释信号(如足球库的 `Match` 表有 115 列)。开启后,系统针对每个问题**只召回相关的表/列 + 业务规则**喂给 LLM。

### 触发条件(按 schema 体量,不是只看表数)

`retrieve_context` 在 **表多(需选表)或 总列数多(需裁列,哪怕表很少)** 时才介入;两者都小 = 小库,直接整库 DDL。这样像 `european_football_2`(7 表但 199 列、`Match` 115 列)这种"表少但有宽表"的库也能走检索 —— 这正是最需要列裁剪的场景。

### 四路召回

| 路 | 召回信号 | 后端(server) | 后端(local) |
|---|---|---|---|
| **vector** | 语义相似(列描述/自然名)| Milvus | 进程内 numpy 余弦 |
| **keyword** | BM25 精确词(中文走 IK 分词)| Elasticsearch + analysis-ik | 进程内 rank_bm25 |
| **glossary** | 业务术语/规则(取值映射、去重口径、JOIN 提示)| PostgreSQL + pgvector | —(仅 server)|
| **graph** | **表结构相关性**(PPR 沿 FK 扩散)+ JOIN 路径 | networkx + numpy PPR(进程内,两后端共用)||

前三路(内容路)**并行执行**(线程池,墙钟 ≈ 最慢一路),经 **RRF 倒数排名融合**得到表分。graph 是**第 4 路**但需种子,故二阶段:以前三路融合 top 表为种子跑 **Personalized PageRank** 沿外键扩散,把结构上相关(枢纽/桥接)但内容路没捞到的表打分并入 → 再融合一次。选表定下后用 FK 最短路径补桥接表 + 输出 JOIN 条件喂 LLM。任一后端连不上自动跳过该路,最差回退整库 DDL,不会崩。

### 提召回准确率的几个关键设计

- **查询侧术语扩展**:embedding 前用快模型把中文问题的实体/属性抽出来、补英文列名别名(惯用脚→`preferred_foot`、已支付→`paid status`)。既帮向量路(语义更近),也帮 BM25(中英 token 本来零重叠)。按问题 LRU 缓存。
- **列级裁剪**:选中一张宽表时,只渲染**命中列 + 主键 + 外键列 + 补满到 `RETRIEVAL_COL_CAP`(默认 25)**,其余折叠成"另有 N 个字段未列出";窄表整表不裁。避免上百列的大表淹没信号、撑爆 token。
- **选表打分去偏**:把"列分求和"(宽表靠列多无限膨胀)改成"最强命中主导 + 其余几何衰减加成"(`TABLE_SCORE_DECAY`),多列膨胀从 Nx 封顶到约 2x,削弱宽表偏置。
- **RRF 每路可调权重**:`RRF_WEIGHT_*` 让你给"更可信的路"(如精确命中的 keyword)更大融合权重,默认全 1.0(等权)。
- **检索 query 当前问题主导**:只带最近 `RETRIEVAL_HISTORY_TURNS`(默认 2)条历史,避免 5 轮老话题稀释当前语义。
- **启动预热**:服务启动后台为会走检索的库预先建好索引(`PREWARM_ENABLED`),消除各库首次查询的冷启动。

### 两种后端

- **`local`(默认)**:全进程内(numpy + rank_bm25 + networkx),零外部依赖,开箱即用;`glossary` 路仅 server 模式启用。
- **`server`**:接真组件(Milvus + ES + PG),适合大库/生产。`.env` 设 `RETRIEVAL_BACKEND=server`。

---

## 结果可信度评估(后台异步裁判)

查询成功后,裁判 LLM(`JUDGE_MODEL`,与主生成分开)基于「问题 + 喂给生成器的 schema 上下文 + SQL + 结果预览」给**召回质量**和**SQL/结果正确性**各打 0-100,代码按 `JUDGE_WEIGHT_CORRECTNESS` 合成一个 `confidence`(0-100)。

- **后台异步化**:评估是纯信息性的(不影响 SQL/结果),却要一次完整 LLM 往返。所以 `/api/ask` **只入队后台评估、返回 `judge_id`**,结果先到;前端拿到结果后短轮询 `POST /api/judge` 读取已完成的勋章。用户无需等待裁判模型即可看到表格。
- **业务语言评语**:裁判 prompt 要求评语面向不懂 SQL 的业务用户,**禁止出现表名/列名/JOIN 等技术词**,用"系统找到了订单和客户数据…"这类说法。前端 tooltip 也用「数据完整度 / 结果匹配度」而非「召回质量 / SQL 正确性」。
- **best-effort**:裁判失败/关闭/超时轮询未取到,勋章会消失或保持为空,不影响查询。`JUDGE_ENABLED=false` 可整体关掉。

---

## 前端工作台能力

前端不是只展示 SQL 和表格,还提供面向业务用户的轻量工作台能力:

- **推荐问法**:按当前数据源 / 自动模式切换问题模板,帮助用户从空输入框起步。
- **最近查询**:浏览器本地保存最近查询记录,可点击回填问题;服务端仍保持无状态。
- **结果操作**:结果表支持复制、下载 CSV、保存查询到本地、以及基于「文本列 + 数值列」的简单柱状图预览。
- **CSV 安全**:导出/复制时会对 `= + - @` 开头的单元格加前缀,降低 Excel 公式注入风险。

这些信息都保存在浏览器 `localStorage`,不会写入服务端。

---

## 派生指标 / 计算口径(业务语义层)

很多业务问题问的是**指标**(客单价、件单价、传球能力、毛利率),而这些大多**不是表里的现成列**,要由现有字段按公式算出来。系统让业务方用**纯自然语言**定义指标,字段匹配交给 LLM —— 业务方**不需要知道任何列名**。

### 怎么定义

在该库的 glossary(`data/glossaries/<name>.md`)里,用 `- 名称 = 公式` 写,公式里也只用自然语言概念:

```markdown
【派生指标 / 计算口径(用自然语言定义,公式里的概念由系统自动匹配到字段)】
- 客单价 = 总消费金额 / 订单数量
- 件单价 = 总消费金额 / 总商品件数
- 传球能力 = 短传 + 长传
```

注意:`总消费金额`、`订单数量`、`短传` 都是**自然语言概念,不是列名**。系统会自动把它们匹配到 `SUM(amount)`、`COUNT(id)`、`short_passing` 等。

### 工作原理

1. **检测**:问题里出现已定义的指标名(子串匹配,`app/core/retrieval/metrics.py`)。
2. **操作数感知召回(大库关键)**:把公式里的操作数概念(`短传 + 长传`)并入检索 query,经查询扩展补英文别名(`short_pass / long_pass`),让操作数对应的列被各路召回进精简上下文 —— 否则会出现"公式召回了、源列却没召回,LLM 接不上"。
3. **强制注入公式**:把命中的口径定义直接写进上下文,不依赖 glossary 向量恰好召回它(`local` 后端没有 glossary 路也照样生效)。
4. **LLM 自动接列计算**:模型看到公式 + 上下文里的字段,自己把概念接到列上,写出 SQL。

> **小库**(整库 DDL 全喂,不走检索)开箱即用,第 2 步不需要;**大库**(schema linking)靠第 2 步补齐源列。

### 兜底与边界

- **匹配不到就别硬凑**:公式里某个概念在表中找不到任何字段(如"毛利率"需要"成本"、而库里无成本列),LLM 会回 `无法回答: 缺 X 口径` 或按澄清规则反问,而不是编一个错误计算。
- **方言安全**:整数列相除是整除、除零会出错。涉及比率的口径建议在公式里写清安全形式(如 `CAST(销售额 AS REAL) / NULLIF(订单数量, 0)`)。
- **歧义是天花板**:一个概念对应多个候选列(如"速度"对 `sprint_speed`/`agility`)时,LLM 倾向自信地挑一个而非反问 —— 这种"错得理直气壮"目前无法 100% 拦住,口径命名尽量明确可降低概率。
- **不支持递归**:指标引用指标暂不自动展开,需拍平写。

---

## 模块职责对照

| 路径 | 角色 |
|---|---|
| `app/main.py` | FastAPI 入口,挂 `/api/*` + 静态前端;启动后台预热检索器 |
| `app/api/routes.py` | `/health` `/sources` `/schema` `/ask` `/judge` 端点 |
| `app/service.py` | **业务编排核心**:路由 → schema → 检索 → 生成 → 校验 → 执行 → 暂存评估 → 回修 |
| `app/core/config.py` | pydantic-settings 读 `.env`,所有可调项与路径常量 |
| `app/core/data_sources.py` | 读 `data_sources.yaml`,建/缓存 SQLAlchemy 引擎(只读),解析词表/profile 路径 |
| `app/core/source_router.py` | 数据源自动路由(快模型按问题选库) |
| `app/core/schema.py` | 读 DDL + 业务词表 + schema profile + 自动发现字段取值;`count_columns` 供检索触发判断 |
| `app/core/schema_profile.py` | 结构化 schema 画像:表粒度、默认过滤、字段语义、人工关系、指标口径、字段可用性 |
| `app/core/chain.py` | LangChain 链:`generate_sql` / `repair_sql`;`_llm`(主)/`_router_llm`(快)/`make_llm` |
| `app/core/retrieval/` | 四路检索子系统(见下表) |
| `app/core/validator.py` | SQL 安全校验:单条 SELECT、黑名单、递归表白名单、禁用字段拦截、LIMIT 强制/收紧 |
| `app/core/executor.py` | 只读执行 + 查询超时保护,返回 `(columns, rows, elapsed_ms)` |
| `app/core/judge.py` | 结果可信度评估 + 后台异步评估队列(`stash` / `run_stashed`) |
| `app/core/sql_meta.py` | sqlparse 抽 SELECT 列源表达式,服务于前端双行表头 |
| `app/core/formatter.py` | 统一响应字典格式 |
| `app/models/schemas.py` | Pydantic 请求/响应模型 |
| `app/static/` | 单页前端:`index.html` + `app.js` + `style.css`(推荐问法 / 查询历史 / 结果操作 / 进度条 / 异步勋章 / 术语表面板) |
| `prompts/*.txt` | 外置 prompt:`sql_prompt`(12 条规则)/ `sql_repair` / `router` / `judge` / `query_expand` |

### `app/core/retrieval/` 子模块

| 文件 | 角色 |
|---|---|
| `pipeline.py` | 检索编排:触发判断 → 查询扩展 → 四路召回 → RRF 融合 → 选表 → 列裁剪 → 渲染 |
| `atoms.py` | 把 schema 拆成可检索的 `SchemaAtom`(每列一个 + 每表一个) |
| `base.py` | `SchemaAtom` / `Hit` / `Retriever` 接口 |
| `embedding.py` | DashScope `text-embedding-v3` 封装(批量 + L2 归一化) |
| `query_expand.py` | 查询侧术语扩展(中文 → 英文列名别名) |
| `metrics.py` | 派生指标:从词表提取 `名称 = 公式`,命中时操作数并入召回 + 强制注入公式 |
| `vector.py` / `keyword.py` | local 后端:numpy 余弦 / rank_bm25 |
| `milvus_vector.py` / `es_keyword.py` | server 后端:Milvus / Elasticsearch |
| `glossary_vector.py` | 业务术语路(PG + pgvector),`parse_glossary` 拆条目 |
| `graph.py` | 关系图谱:PPR 结构检索 + FK/人工关系最短路径 JOIN 渲染 |

---

## 技术栈

| 层 | 选型 |
|---|---|
| Web 框架 | FastAPI + Uvicorn |
| LLM 链路 | LangChain + langchain-community(`ChatTongyi` / 多模态封装)|
| LLM 模型 | 生成 `qwen3.7-plus` · 裁判 `qwen3.6-plus` · 路由/查询扩展 `qwen-turbo`(均 DashScope,可配)|
| 数据库 | SQLite / PostgreSQL(只读模式) |
| SQL 解析 | sqlparse(递归提取表引用,含 quoted/schema/子查询/CTE 场景) |
| 检索 | 四路:`local`(numpy / rank_bm25 / networkx)或 `server`(Milvus + Elasticsearch+IK + PostgreSQL/pgvector)|
| 嵌入 | DashScope `text-embedding-v3` |
| 配置 | pydantic-settings + `.env` + `data_sources.yaml` |
| 前端 | 原生 HTML/JS + CSS |

---

## 目录结构

```
NL2SQL/
├── app/
│   ├── main.py                  # FastAPI 入口 + 启动预热
│   ├── service.py               # 业务编排:路由→schema→检索→生成→校验→执行→暂存评估→回修
│   ├── api/routes.py            # /health /sources /schema /ask /judge
│   ├── core/
│   │   ├── config.py            # 所有可调项与路径常量
│   │   ├── data_sources.py      # 多数据源注册 + 只读引擎
│   │   ├── source_router.py     # 数据源自动路由
│   │   ├── schema.py            # DDL + 业务词表 + schema profile + 取值发现
│   │   ├── schema_profile.py    # 结构化 schema 画像(P0/P1 知识层)
│   │   ├── chain.py             # LangChain 链:生成 / 回修;主/快模型
│   │   ├── retrieval/           # 四路 schema linking 检索子系统
│   │   ├── validator.py         # SQL 安全校验 + 表白名单 + LIMIT 强制
│   │   ├── executor.py          # 只读执行器 + 查询超时
│   │   ├── judge.py             # 结果可信度评估 + 后台异步队列
│   │   ├── sql_meta.py          # 列源表达式解析
│   │   └── formatter.py         # 响应格式化
│   ├── models/schemas.py        # Pydantic 模型
│   └── static/                  # 前端(推荐问法 / 历史 / 结果操作 / 进度条 / 异步勋章 / 术语表)
├── prompts/
│   ├── sql_prompt.txt           # 主 prompt(12 条规则 + 示例)
│   ├── sql_repair_prompt.txt    # 失败回修
│   ├── router_prompt.txt        # 数据源路由
│   ├── judge_prompt.txt         # 结果可信度裁判(业务语言评语)
│   └── query_expand_prompt.txt  # 查询侧术语扩展
├── data_sources.yaml            # 数据源注册表
├── data/
│   ├── app.db                   # 示例 SQLite(seed 后生成)
│   ├── glossaries/              # 各库业务词表
│   ├── schema_profiles/         # 各库结构化 schema 画像
│   ├── bird/                    # BIRD 基准库的词表/源配置
│   └── retrieval_index/         # 检索索引缓存(向量/签名)
├── docker-compose.yml + docker/ # server 后端组件(ES+IK / Milvus / pgvector)
├── scripts/
│   ├── seed_db.py               # 生成示例电商库
│   ├── eval.py / eval_bird.py   # 评测脚本
│   └── verify_server_backend.py # 验证 server 检索生效
├── tests/                       # manual_test_cases.md / eval_cases.yaml
└── requirements.txt
```

---

## 快速开始

### 1. 装依赖

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 配置 `.env`

项目根目录新建 `.env`:

```env
DASHSCOPE_API_KEY=sk-你的密钥        # 必填,https://dashscope.console.aliyun.com/
QWEN_MODEL=qwen3.7-plus              # 主生成模型
JUDGE_MODEL=qwen3.6-plus             # 裁判模型
ROUTER_MODEL=qwen-turbo              # 路由/查询扩展(快模型)
# 其余均有默认值,可不写
```

> 除 `DASHSCOPE_API_KEY` 必填外,模型名等都有默认值。

### 3. 生成示例数据库

```powershell
python scripts/seed_db.py
```

### 4. 启动服务

```powershell
uvicorn app.main:app --reload
```

- 前端:<http://127.0.0.1:8000/>
- Swagger:<http://127.0.0.1:8000/docs>
- 健康检查:<http://127.0.0.1:8000/api/health>

> 默认 `RETRIEVAL_BACKEND=local`,纯进程内、不需要 docker。想开大库的 server 检索见下一节。

---

## 启用 server 检索后端(可选)

接真组件(Milvus + ES + PG),适合大库/生产;`glossary` 业务术语路仅此模式启用。

1. **起 docker 检索服务**(ES 含中文分词插件,**必须带 `--build`**):

   ```powershell
   docker compose up -d --build
   ```

   起的服务:Elasticsearch(`:9200`,含 IK)、Milvus(`:19530`,自带 etcd+minio)、PostgreSQL+pgvector(host **`:5433`**,避开本机 PG)。

2. **`.env` 开开关**:

   ```env
   RETRIEVAL_BACKEND=server
   # 以下均有默认值,一般不用改
   # ES_URL=http://localhost:9200
   # MILVUS_URI=http://localhost:19530
   # PG_DSN=postgresql://nl2sql:nl2sql@localhost:5433/nl2sql_retrieval
   ```

3. **重启 uvicorn**。首次查询某库会建索引(嵌入 + 入库),之后按内容签名命中缓存;启动预热会在后台提前把会走检索的库建好。

### 验证

```powershell
python scripts/verify_server_backend.py superhero "哪个出版商旗下的超级英雄最多"
```

看 `retrievers_used` 含 `vector / keyword / glossary / graph`、日志有「…索引已重建/命中缓存」即生效。

---

## 连接你自己的数据库

编辑根目录 `data_sources.yaml`(SQLite / PostgreSQL,只改 `url` 不改代码):

```yaml
sources:
  - name: demo_sqlite                          # 内部标识
    label: 示例电商 (SQLite)                    # 下拉显示名
    url: sqlite:///data/app.db                 # SQLAlchemy 连接串
    glossary: data/glossaries/demo_sqlite.md   # 可选,业务词表
    schema_profile: data/schema_profiles/demo_sqlite.yaml  # 可选,结构化 schema 画像

  - name: prod_pg
    label: 生产库 (PostgreSQL)
    url: postgresql+psycopg://readonly_user:password@127.0.0.1:5432/mydb
    glossary: data/glossaries/prod_pg.md
    schema_profile: data/schema_profiles/prod_pg.yaml
```

**业务词表**(`data/glossaries/<name>.md`,可选)写枚举映射、跨表语义、字段口径、**派生指标**(`- 客单价 = 总消费金额 / 订单数量`,见上文「派生指标」一节)等。系统会自动发现低基数 TEXT 列的取值;手写词表补充自动发现不到的内容。

> ⚠️ 词表里的业务规则一律用 `- ` 开头的条目写。`parse_glossary` 只解析 `- ` 项与 `## 表 X` 分节,**`>` 引用块 / 纯标题不会被检索到**(走检索的库尤其要注意)。

**结构化 schema 画像**(`data/schema_profiles/<name>.yaml`,可选)写表粒度、默认过滤、人工 JOIN 关系、字段中文名/枚举/默认聚合、敏感/禁用字段和结构化指标。建议真实业务库优先补齐:

1. 表粒度:每张事实表一行代表什么。
2. 默认过滤:有效/已支付/未删除等默认口径。
3. 人工关系:没有外键的生产库必须补 JOIN 关系。
4. 字段语义:中文名、枚举含义、指标/维度/时间/ID 类型。
5. 字段可用性:敏感、废弃、临时字段标记为不可用于问数。

`data_sources.yaml` 启动时加载,改完重启 `uvicorn`。

### 安全

- SQLite 走 `?mode=ro` URI;PostgreSQL 走会话级 `default_transaction_read_only=on` —— DB 账号层强制只读,即使校验器漏过也写不进去。
- SQL 校验器只允许单条 `SELECT`,递归抽取 `FROM/JOIN` 表引用并做白名单校验,覆盖 quoted 表名、schema 前缀、子查询和 CTE 常见场景。
- 执行器按 `QUERY_TIMEOUT_SECONDS` 做数据库侧超时保护:PostgreSQL 使用 `statement_timeout`,SQLite 使用 progress handler 中断长查询。
- 前端 CSV/表格复制对公式起始字符做转义,降低本地打开导出文件时的公式注入风险。

---

## REST API

| 端点 | 说明 |
|---|---|
| `POST /api/ask` | 主查询。返回 sql / 结果 / 实际数据源 / `judge_id` |
| `POST /api/judge` | 凭 `judge_id` 读取后台评估结果;未完成/失败时返回空 |
| `GET /api/sources` | 数据源列表 + 默认源 |
| `GET /api/schema?source=` | 某库 DDL + `{表名:[列名]}` 白名单 + 字段治理元数据 |
| `GET /api/health` | `{"status":"ok"}` |

**`POST /api/ask` 请求:**
```json
{
  "question": "梅西的惯用脚是哪只?",
  "history": [{ "question": "上一轮问题", "sql": "上一轮 SQL", "kind": "sql" }],
  "source": null,                 // 手动锁库的 name;null=自动路由
  "current_source": "european_football_2",  // 本会话当前库(路由提示)
  "user_glossary": []             // 该库的自定义术语
}
```

**响应(节选):**
```json
{
  "sql": "SELECT DISTINCT pl.player_name, pa.preferred_foot FROM Player pl JOIN ...",
  "columns": ["player_name", "preferred_foot"],
  "column_sources": ["pl.player_name", "pa.preferred_foot"],
  "rows": [["Lionel Messi", "left"]],
  "row_count": 1,
  "elapsed_ms": 79,
  "truncated": false,
  "error": null,
  "clarify": null,
  "source": "european_football_2",
  "source_label": "BIRD: european_football_2",
  "auto_routed": true,
  "confidence": null,             // 首响应为 null,前端随后轮询 /api/judge 补
  "judge_id": "8bcdfcb3deeb44..."
}
```

`clarify` 非空表示模型需要先澄清;`source`/`auto_routed` 透明展示本次实际用的库。

---

## 配置项一览(`.env`)

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `DASHSCOPE_API_KEY` | — | **必填** |
| `QWEN_MODEL` | `qwen-max` | 主生成模型(本项目 `.env` 设为 `qwen3.7-plus`)|
| `JUDGE_MODEL` | `qwen-plus` | 裁判模型(设为 `qwen3.6-plus`)|
| `ROUTER_MODEL` | `qwen-turbo` | 路由 + 查询扩展用的快模型 |
| `MAX_ROWS` | `200` | 单次最大返回行数(同时是 LIMIT 上限)|
| `QUERY_TIMEOUT_SECONDS` | `5` | 查询执行超时秒数(PostgreSQL `statement_timeout` / SQLite progress handler) |
| `JUDGE_ENABLED` | `true` | 是否启用结果可信度评估 |
| `JUDGE_WEIGHT_CORRECTNESS` | `0.7` | 最终分 = 此权重×正确性 +(1-此)×召回 |
| `JUDGE_SAMPLE_ROWS` | `20` | 喂裁判的结果行样本上限 |
| `ENUM_DISCOVERY_ENABLED` | `true` | 是否自动发现低基数 TEXT 列取值 |
| `ENUM_DISCOVERY_MAX_TABLES` | `20` | 表数超过此值时跳过自动取值发现 |
| `ENUM_DISCOVERY_MAX_COLUMNS` | `120` | 总列数超过此值时跳过自动取值发现 |
| **检索** | | |
| `RETRIEVAL_ENABLED` | `true` | 总开关 |
| `RETRIEVAL_BACKEND` | `local` | `local` 进程内 / `server` 真组件 |
| `RETRIEVAL_MIN_DDL_CHARS` | `1500` | DDL 短于此值不检索(小库全量喂)|
| `RETRIEVAL_MIN_COLUMNS` | `40` | 总列数 > 此值即触发检索(即便表数 ≤ 上限)|
| `RETRIEVAL_TOP_TABLES` | `8` | 融合后保留的相关表数上限 |
| `RETRIEVAL_TOP_K` | `30` | 每路返回的列命中数 |
| `RETRIEVAL_COL_CAP` | `25` | 宽表渲染的列数上限(命中+主外键优先)|
| `RETRIEVAL_MAX_BRIDGE_TABLES` | `3` | 图谱为连通选中表最多补的桥接表数 |
| `RETRIEVAL_QUERY_EXPANSION` | `true` | 查询侧术语扩展(关掉省一次快模型往返)|
| `RETRIEVAL_HISTORY_TURNS` | `2` | 检索 query 纳入的最近历史条数 |
| `RRF_WEIGHT_VECTOR/KEYWORD/GLOSSARY/GRAPH` | `1.0` | 各路 RRF 融合权重 |
| `TABLE_SCORE_DECAY` | `0.5` | 选表打分衰减(1.0=纯求和,0=纯取最强命中)|
| `GLOSSARY_TOP_K` | `5` | 术语路每次召回条数 |
| `PREWARM_ENABLED` | `true` | 启动后台预热检索器 |

代码侧常量(改完需重启):`MAX_REPAIR_ROUNDS`(`service.py`,回修轮数)、`MAX_HISTORY_TURNS`(`service.py` 与 `app.js`,各 5)。

---

## 修改入口指南(想做 X,看哪)

| 想做的事 | 看哪 |
|---|---|
| 让 LLM 学会一类新提问 | `prompts/sql_prompt.txt` 加一条**示例**,通常比改规则有效 |
| 改业务默认值(如"金额默认 paid")| `prompts/sql_prompt.txt` 硬性规则段 |
| 调路由判库行为 | `prompts/router_prompt.txt` |
| 改可信度评语口吻 | `prompts/judge_prompt.txt` |
| 调查询扩展的别名风格 | `prompts/query_expand_prompt.txt` |
| 加/换数据源 | `data_sources.yaml`(改完重启)|
| 给某库补业务规则/取值映射 | `data/glossaries/<name>.md`(用 `- ` 条目)|
| 给某库补表粒度/默认过滤/JOIN/字段语义/敏感字段 | `data/schema_profiles/<name>.yaml`,并在 `data_sources.yaml` 配 `schema_profile` |
| 加派生指标(客单价、毛利率等)| `data/glossaries/<name>.md` 写 `- 名称 = 公式`(纯自然语言);逻辑在 `app/core/retrieval/metrics.py` |
| 调检索召回(触发/裁列/权重)| `.env` 的 `RETRIEVAL_*` / `RRF_*` / `TABLE_SCORE_DECAY` |
| 换模型 | `.env` 的 `QWEN_MODEL` / `JUDGE_MODEL` / `ROUTER_MODEL` |
| 允许/禁止某 SQL 关键字 | `app/core/validator.py` 的 `FORBIDDEN_KEYWORDS` |
| 加 API 字段 | `app/models/schemas.py` + `formatter.py` + `service.py` 三处 |
| 改前端推荐问法/历史/结果操作/进度条/勋章 | `app/static/app.js` + `style.css` |

---

## 已知限制

- LLM 行为非确定:同一问题多次提问 SQL 可能不同;`temperature=0` 已尽力但不保证
- 多轮对话超过 5 轮会丢更早上下文(前端 localStorage 也仅保留 ~10 轮)
- 列级裁剪有极小漏列风险:既没被任一路命中、又非主外键的列可能被折叠 —— 已用查询扩展提命中率 + 主外键强制保留 + 折叠提示缓解;必要时调高 `RETRIEVAL_COL_CAP`
- 查询扩展在检索路径上加一次快模型往返(可 `RETRIEVAL_QUERY_EXPANSION=false` 关闭做 A/B)
- 跨语言 BM25:BIRD 库 schema 英文、问题中文,`keyword` 路命中有限(查询扩展已大幅缓解)
- `REPLACE` 字符串函数与 `INSERT OR REPLACE` 共享关键字,当前仍被一刀切禁用;如确需字符串替换函数,需在 `validator.py` 中做函数级放行。
- 自动取值发现为了稳定性有表数/列数上限;大库可能需要更多依赖手写 glossary 来补充枚举映射。
- `schema_profile` 目前是文件级发布,改完需要重启服务清缓存;多人协作/审核发布还未做成服务端工作流。

---

## 常见问题

**Q: 启动报 `DASHSCOPE_API_KEY 未配置`?** 在根目录建 `.env` 填 key。

**Q: 改了 schema / 词表 / schema profile / prompt 后没生效?** schema、profile 与部分 prompt 有进程级缓存,检索器索引也按签名缓存;**重启 uvicorn** 即可(`sql_prompt` 被 lru_cache,词表/profile 内容变更也需重启清 `_get` 缓存)。

**Q: 自动路由选错库?** 调 `prompts/router_prompt.txt`,或前端下拉手动锁库。

**Q: 结果可信度勋章一直"评估中"?** 可信度由后台线程 best-effort 计算;如果裁判模型失败、关闭或前端轮询超时,勋章会消失/为空,不影响结果。

**Q: 想关检索 / 可信度评估 / 自动取值发现?** `.env` 设 `RETRIEVAL_ENABLED=false` / `JUDGE_ENABLED=false` / `ENUM_DISCOVERY_ENABLED=false`。

**Q: 想看生成了什么 SQL / 失败原因?** 看终端日志(`ask ok` / 校验失败 / 执行失败),或前端「生成的 SQL」框。

---

## 许可

仅供学习与个人项目使用。
