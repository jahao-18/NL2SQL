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
    qwen_model: str = "qwen-plus"
    db_path: str = "data/app.db"
    max_rows: int = 200
    query_timeout_seconds: int = 5

    @property
    def db_abspath(self) -> Path:
        p = Path(self.db_path)
        return p if p.is_absolute() else ROOT_DIR / p


settings = Settings()
