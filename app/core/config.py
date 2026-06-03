"""集中读取环境变量与路径常量。"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = ROOT_DIR / "prompts"
STATIC_DIR = ROOT_DIR / "app" / "static"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    dashscope_api_key: str = ""
    qwen_model: str = "qwen-max"
    # 数据源路由模型:只做"从库目录里选一个库"的分类小任务,无需主生成那么强,
    # 用快模型砍掉路由这一步的延迟(只影响选库速度,不碰库内 schema 召回质量)。
    router_model: str = "qwen-turbo"
    max_rows: int = 200
    query_timeout_seconds: int = 5

    # ── 答案准确率评估(用另一个 LLM 当裁判,给用户参考)──
    # 成功执行后,裁判模型对「召回质量」+「SQL/结果正确性」各打 0-100,合成一个最终准确率展示。
    # best-effort:裁判失败不影响查询本身。关掉则不评分、响应里 confidence 为 None。
    judge_enabled: bool = True
    judge_model: str = "qwen-plus"          # 裁判模型,与生成模型 qwen_model 分开(另一个 LLM),可调
    judge_weight_correctness: float = 0.7   # 最终分 = 此权重*SQL正确性 + (1-此权重)*召回质量
    judge_sample_rows: int = 20             # 喂给裁判的结果行样本上限(控 token)

    # ── 知识库检索(schema linking)──
    retrieval_enabled: bool = True          # 总开关:关掉则始终用整库 DDL(旧行为)
    # 检索后端:"local" = 进程内(numpy 向量 + rank_bm25);"server" = Milvus + Elasticsearch。
    # server 模式下若服务连不上,各检索器 available() 返回 False,自动回退整库 DDL,不会崩。
    retrieval_backend: str = "local"
    es_url: str = "http://localhost:9200"
    # ES 分词器:中文用 IK(需镜像装 analysis-ik 插件,见 docker/es/Dockerfile)。
    # 索引用 ik_max_word(最细粒度,多切词,提召回);搜索用 ik_smart(粗粒度,少切词,提精度)。
    # 插件没装时建索引会被 ES 拒,es_keyword 自动回退 standard(按字切),不影响可用性。
    es_analyzer: str = "ik_max_word"
    es_search_analyzer: str = "ik_smart"
    milvus_uri: str = "http://localhost:19530"
    # 业务术语词表检索(第 4 路)的存储库:PostgreSQL + pgvector(docker-compose 的 postgres 服务)。
    # 注意这是检索存储库,与 data_sources.yaml 里被查询的业务 PG 数据源无关。连不上则该路 available()=False。
    pg_dsn: str = "postgresql://nl2sql:nl2sql@localhost:5433/nl2sql_retrieval"
    glossary_top_k: int = 5                 # glossary 路按问题召回的术语条目数上限
    embedding_model: str = "text-embedding-v3"
    retrieval_min_ddl_chars: int = 1500     # 整库 DDL 短于此值就不检索,直接全量喂(小库无需 schema linking)
    retrieval_top_tables: int = 8           # 融合后保留的相关表数量上限
    retrieval_top_k: int = 30               # 每路检索器返回的列命中数
    retrieval_max_bridge_tables: int = 3    # 关系图谱为连通选中表最多补的桥接表数
    # 启动时后台预热:提前为"会真正走检索的大库"建好原子/检索器/图/术语索引(含嵌入全部原子),
    # 消除每个库首次查询的冷启动延迟。后台线程跑,不阻塞启动;小库/检索关闭时自动跳过。
    prewarm_enabled: bool = True


settings = Settings()
