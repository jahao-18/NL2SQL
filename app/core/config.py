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
    max_rows: int = 200
    query_timeout_seconds: int = 5

    # ── 知识库检索(schema linking)──
    retrieval_enabled: bool = True          # 总开关:关掉则始终用整库 DDL(旧行为)
    embedding_model: str = "text-embedding-v3"
    retrieval_min_ddl_chars: int = 1500     # 整库 DDL 短于此值就不检索,直接全量喂(小库无需 schema linking)
    retrieval_top_tables: int = 8           # 融合后保留的相关表数量上限
    retrieval_top_k: int = 30               # 每路检索器返回的列命中数
    retrieval_max_bridge_tables: int = 3    # 关系图谱为连通选中表最多补的桥接表数


settings = Settings()
