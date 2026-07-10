"""数据源注册表:读 data_sources.yaml,提供按名查找。

每个 DataSource 描述一个可查询的库:连接 URL + 方言 + 可选业务词表 + 可选结构化 schema 画像。
yaml 路径默认是项目根的 data_sources.yaml,可通过环境变量 DATA_SOURCES_FILE 覆盖。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url

from app.core.config import ROOT_DIR, settings

Dialect = Literal["sqlite", "postgresql", "mysql", "other"]


@dataclass(frozen=True)
class DataSource:
    name: str                       # 内部标识符,API 透传用
    label: str                      # 前端显示名
    url: str                        # SQLAlchemy 连接串
    dialect: Dialect                # 方言,用于 prompt 注入与只读策略选择
    glossary_path: Path | None      # 业务词表绝对路径,可为 None
    schema_profile_path: Path | None # 结构化 schema 画像,可为 None


def _detect_dialect(url: str) -> Dialect:
    """从 SQLAlchemy URL 推断方言。"""
    try:
        backend = make_url(url).get_backend_name()
    except Exception:
        return "other"
    if backend == "sqlite":
        return "sqlite"
    if backend in {"postgresql", "postgres"}:
        return "postgresql"
    if backend == "mysql":
        return "mysql"
    return "other"


def _resolve(path_str: str | None) -> Path | None:
    if not path_str:
        return None
    p = Path(path_str)
    return p if p.is_absolute() else ROOT_DIR / p


def _expand_url(url: str) -> str:
    return url.replace("${BIRD_DATABASE_ROOT}", Path(settings.bird_database_root).as_posix().rstrip("/"))


@lru_cache(maxsize=1)
def load_sources() -> dict[str, DataSource]:
    """读 yaml,返回 name -> DataSource 的有序字典(按 yaml 顺序保留)。"""
    config_path = Path(os.getenv("DATA_SOURCES_FILE", ROOT_DIR / "data_sources.yaml"))
    if not config_path.exists():
        raise FileNotFoundError(f"数据源配置不存在: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    items = raw.get("sources") or []
    if not items:
        raise ValueError(f"{config_path} 中没有任何 source")

    result: dict[str, DataSource] = {}
    for item in items:
        name = item.get("name")
        url = _expand_url(str(item.get("url") or ""))
        if not name or not url:
            raise ValueError(f"数据源缺 name 或 url: {item}")
        if name in result:
            raise ValueError(f"数据源 name 重复: {name}")
        result[name] = DataSource(
            name=name,
            label=item.get("label") or name,
            url=url,
            dialect=_detect_dialect(url),
            glossary_path=_resolve(item.get("glossary")),
            schema_profile_path=_resolve(item.get("schema_profile")),
        )
    return result


def get_source(name: str | None = None) -> DataSource:
    """按名取数据源;name=None 返回第一个(默认源)。"""
    sources = load_sources()
    if name is None:
        return next(iter(sources.values()))
    if name not in sources:
        raise KeyError(f"未知数据源: {name}。可用: {', '.join(sources)}")
    return sources[name]


def clear_cache() -> None:
    load_sources.cache_clear()
    _engine_for_url.cache_clear()


@lru_cache(maxsize=8)
def _engine_for_url(url: str, dialect: Dialect) -> Engine:
    """按 URL 缓存 engine,强制只读连接(尽量在 DB 层防写)。"""
    kwargs: dict = {"future": True}
    connect_args: dict = {}

    if dialect == "sqlite":
        url = _normalized_sqlite_url(url)
        connect_args["check_same_thread"] = False
    elif dialect == "postgresql":
        # 会话级只读
        connect_args["options"] = "-c default_transaction_read_only=on"

    kwargs["connect_args"] = connect_args
    return create_engine(url, **kwargs)


def _normalized_sqlite_url(url: str) -> str:
    if not url.startswith("sqlite:///"):
        return url
    body = url[len("sqlite:///"):]
    if body.startswith("file:"):
        body = body[5:]
    raw_path, separator, query = body.partition("?")
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
    params = [part for part in query.split("&") if part] if separator else []
    keys = {part.split("=", 1)[0].lower() for part in params}
    if "mode" not in keys:
        params.append("mode=ro")
    if "uri" not in keys:
        params.append("uri=true")
    return f"sqlite:///file:{path.resolve().as_posix()}?{'&'.join(params)}"


def get_engine(source: DataSource) -> Engine:
    return _engine_for_url(source.url, source.dialect)
