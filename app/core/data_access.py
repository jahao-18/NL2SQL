"""Data source onboarding and controlled table maintenance."""
from __future__ import annotations

import csv
import json
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus
from uuid import uuid4

import yaml
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url

from app.core.config import ROOT_DIR
from app.core import data_sources as ds_cache
from app.core.schema import clear_cache as clear_schema_cache
from app.core.schema_profile import empty_profile_dict, save_profile_dict
from app.core.file_store import atomic_write_text, lock_for


DATA_SOURCES_FILE = ROOT_DIR / "data_sources.yaml"
UPLOAD_DIR = ROOT_DIR / "data" / "uploads"
AUDIT_DIR = ROOT_DIR / "data" / "audit"
AUDIT_FILE = AUDIT_DIR / "data_change_logs.jsonl"
MANAGED_DB_DIR = ROOT_DIR / "data" / "managed"
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,48}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_yaml() -> dict[str, Any]:
    raw = yaml.safe_load(DATA_SOURCES_FILE.read_text(encoding="utf-8")) or {}
    raw.setdefault("sources", [])
    return raw


def _save_yaml(raw: dict[str, Any]) -> None:
    atomic_write_text(DATA_SOURCES_FILE, yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
    _clear_runtime_caches()


def _clear_runtime_caches() -> None:
    ds_cache.clear_cache()
    clear_schema_cache()
    try:
        from app.core.source_router import clear_cache as clear_router_cache
        clear_router_cache()
    except Exception:
        pass
    try:
        from app.core.retrieval.pipeline import clear_cache as clear_retrieval_cache
        clear_retrieval_cache()
    except Exception:
        pass


def _append_source_entry(entry: dict[str, Any]) -> None:
    with lock_for(DATA_SOURCES_FILE):
        raw = _load_yaml()
        if any(item.get("name") == entry.get("name") for item in raw["sources"]):
            raise ValueError(f"数据源已存在: {entry.get('name')}")
        raw["sources"].append(entry)
        _save_yaml(raw)


def _remove_source_entry(name: str) -> None:
    """Rollback one newly appended source without touching unrelated entries."""
    with lock_for(DATA_SOURCES_FILE):
        raw = _load_yaml()
        original = list(raw["sources"])
        raw["sources"] = [item for item in original if item.get("name") != name]
        if len(raw["sources"]) != len(original):
            _save_yaml(raw)


def _source_entry(name: str) -> dict[str, Any]:
    for item in _load_yaml().get("sources") or []:
        if item.get("name") == name:
            return item
    raise KeyError(name)


def _safe_name(name: str) -> str:
    clean = (name or "").strip()
    if not NAME_RE.match(clean):
        raise ValueError("数据源标识只能使用英文字母、数字、下划线，且必须以字母开头")
    return clean


def _relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def _sqlite_path_from_url(url: str) -> Path:
    if not url.startswith("sqlite:///"):
        raise ValueError("当前数据维护仅支持 SQLite 数据源")
    value = url[len("sqlite:///"):]
    if value.startswith("file:"):
        value = value[5:].split("?", 1)[0]
    path = Path(value)
    return path if path.is_absolute() else ROOT_DIR / path


def _quote_ident(value: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value):
        raise ValueError(f"非法标识符: {value}")
    return '"' + value.replace('"', '""') + '"'


def _redact_url(url: str) -> str:
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return ""


def safe_connection_error(exc: Exception, url: str) -> str:
    message = str(exc)
    try:
        secret = make_url(url).password or ""
    except Exception:
        secret = ""
    for value in {secret, quote(secret, safe=""), quote_plus(secret)} if secret else set():
        if value:
            message = message.replace(value, "***")
    return message


def list_registered_sources() -> list[dict[str, Any]]:
    out = []
    for item in _load_yaml().get("sources") or []:
        name = item.get("name") or ""
        try:
            source = ds_cache.get_source(name)
            engine = ds_cache.get_engine(source)
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            status = "published"
            error = ""
        except Exception as exc:
            tables = []
            status = "error"
            error = str(exc)
        out.append({
            "name": name,
            "label": item.get("label") or name,
            "url": _redact_url(str(item.get("url") or "")),
            "dialect": ds_cache._detect_dialect(item.get("url") or ""),
            "glossary": item.get("glossary") or "",
            "schema_profile": item.get("schema_profile") or "",
            "status": item.get("status") or status,
            "writable": bool(item.get("writable", False)),
            "table_count": len(tables),
            "tables": tables,
            "error": error,
        })
    return out


def test_connection(url: str) -> dict[str, Any]:
    engine = create_engine(url, future=True, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    return {"ok": True, "table_count": len(tables), "tables": tables[:50]}


def _scan_url(url: str) -> dict[str, list[str]]:
    engine = create_engine(
        url,
        future=True,
        connect_args={"options": "-c default_transaction_read_only=on"},
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        inspector = inspect(engine)
        return {
            table: [column["name"] for column in inspector.get_columns(table)]
            for table in inspector.get_table_names()
        }
    finally:
        engine.dispose()


def scan_source(name: str) -> dict[str, Any]:
    source = ds_cache.get_source(name)
    engine = ds_cache.get_engine(source)
    inspector = inspect(engine)
    tables = {}
    for table in inspector.get_table_names():
        tables[table] = [c["name"] for c in inspector.get_columns(table)]
    return {"source": name, "tables": tables, "table_count": len(tables), "column_count": sum(len(v) for v in tables.values())}


def _write_starter_profile(name: str, tables: dict[str, list[str]]) -> str:
    profile = empty_profile_dict()
    for table, columns in tables.items():
        profile["tables"][table] = {
            "business_name": table,
            "grain": f"一行代表一条 {table} 记录。",
        }
        profile["columns"][table] = {
            col: {"business_name": col, "semantic_type": "identifier" if col == "id" or col.endswith("_id") else "dimension"}
            for col in columns
        }
    save_profile_dict(name, profile)
    return f"data/schema_profiles/{name}.yaml"


def register_sqlite_source(name: str, label: str, db_path: str, writable: bool = False) -> dict[str, Any]:
    name = _safe_name(name)
    path = Path(db_path.strip())
    path = path if path.is_absolute() else ROOT_DIR / path
    if not path.exists():
        raise FileNotFoundError(str(path))
    rel_db = _relative(path)
    glossary = ROOT_DIR / "data" / "glossaries" / f"{name}.md"
    glossary.parent.mkdir(parents=True, exist_ok=True)
    if not glossary.exists():
        glossary.write_text(f"# {label or name} Business Glossary\n\n- 请在 Schema 配置中补充业务术语和指标口径。\n", encoding="utf-8")
    entry = {
        "name": name,
        "label": label.strip() or name,
        "url": f"sqlite:///{rel_db}",
        "glossary": _relative(glossary),
        "schema_profile": f"data/schema_profiles/{name}.yaml",
        "writable": bool(writable),
        "status": "published",
    }
    _append_source_entry(entry)
    tables = scan_source(name)["tables"]
    _write_starter_profile(name, tables)
    return {"item": entry, "scan": scan_source(name)}


def register_postgresql_source(
    name: str,
    label: str,
    host: str,
    port: int,
    database: str,
    username: str,
    password_env: str,
    sslmode: str = "prefer",
) -> dict[str, Any]:
    """Register a read-only PostgreSQL source while keeping its password external."""
    name = _safe_name(name)
    host = (host or "").strip()
    database = (database or "").strip()
    username = (username or "").strip()
    password_env = (password_env or "").strip()
    sslmode = (sslmode or "prefer").strip().lower()
    if not host or not database or not username:
        raise ValueError("PostgreSQL 主机、数据库和用户名不能为空")
    if not 1 <= int(port) <= 65535:
        raise ValueError("PostgreSQL 端口必须在 1 到 65535 之间")
    if sslmode not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
        raise ValueError("PostgreSQL sslmode 不合法")

    stored_url = URL.create(
        "postgresql+psycopg",
        username=username,
        host=host,
        port=int(port),
        database=database,
        query={"sslmode": sslmode},
    ).render_as_string(hide_password=False)
    runtime_url = ds_cache.resolve_source_url(stored_url, password_env)
    try:
        tables = _scan_url(runtime_url)
    except Exception as exc:
        message = safe_connection_error(exc, runtime_url)
        raise ValueError(f"PostgreSQL 连接失败: {message}") from exc

    glossary = ROOT_DIR / "data" / "glossaries" / f"{name}.md"
    profile = ROOT_DIR / "data" / "schema_profiles" / f"{name}.yaml"
    if glossary.exists() or profile.exists():
        raise ValueError(f"数据源配套文件已存在: {name}")
    entry = {
        "name": name,
        "label": label.strip() or name,
        "url": stored_url,
        "password_env": password_env,
        "glossary": _relative(glossary),
        "schema_profile": _relative(profile),
        "writable": False,
        "status": "published",
    }
    _append_source_entry(entry)
    try:
        glossary.parent.mkdir(parents=True, exist_ok=True)
        glossary.write_text(
            f"# {label.strip() or name} Business Glossary\n\n"
            "- 请在 Schema 配置中补充业务术语和指标口径。\n",
            encoding="utf-8",
        )
        _write_starter_profile(name, tables)
    except Exception:
        _remove_source_entry(name)
        glossary.unlink(missing_ok=True)
        profile.unlink(missing_ok=True)
        raise

    scan = {
        "source": name,
        "tables": tables,
        "table_count": len(tables),
        "column_count": sum(len(columns) for columns in tables.values()),
    }
    public_item = {key: value for key, value in entry.items() if key != "password_env"}
    public_item["url"] = _redact_url(stored_url)
    return {"item": public_item, "scan": scan}


def import_csv_as_source(name: str, label: str, table_name: str, csv_path: Path, writable: bool = True) -> dict[str, Any]:
    name = _safe_name(name)
    table_name = _safe_name(table_name)
    MANAGED_DB_DIR.mkdir(parents=True, exist_ok=True)
    db_path = MANAGED_DB_DIR / f"{name}.db"
    if db_path.exists():
        raise ValueError(f"托管数据库已存在: {db_path}")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = [c.strip() for c in (reader.fieldnames or []) if c and c.strip()]
    if not columns:
        raise ValueError("CSV 文件没有表头")
    conn = sqlite3.connect(db_path)
    try:
        col_defs = ", ".join([f"{_quote_ident(c)} TEXT" for c in columns])
        conn.execute(f"CREATE TABLE {_quote_ident(table_name)} (id INTEGER PRIMARY KEY AUTOINCREMENT, {col_defs})")
        if rows:
            col_sql = ", ".join(_quote_ident(c) for c in columns)
            marks = ", ".join("?" for _ in columns)
            conn.executemany(
                f"INSERT INTO {_quote_ident(table_name)} ({col_sql}) VALUES ({marks})",
                [[row.get(c, "") for c in columns] for row in rows],
            )
        conn.commit()
    finally:
        conn.close()
    return register_sqlite_source(name, label, _relative(db_path), writable=writable)


def _postgresql_table_rows(source: Any, table: str, limit: int, offset: int) -> dict[str, Any]:
    """Read one PostgreSQL table through the existing read-only SQLAlchemy engine."""
    engine = ds_cache.get_engine(source)
    try:
        inspector = inspect(engine)
        if table not in inspector.get_table_names():
            raise KeyError(table)
        quoted_table = engine.dialect.identifier_preparer.quote(table)
        with engine.connect() as conn:
            with conn.begin():
                total = int(conn.execute(text(f"SELECT COUNT(*) FROM {quoted_table}")).scalar_one())
                result = conn.execute(
                    text(f"SELECT * FROM {quoted_table} LIMIT :limit OFFSET :offset"),
                    {"limit": limit, "offset": offset},
                )
                columns = list(result.keys())
                rows = [dict(row) for row in result.mappings()]
        return {
            "columns": columns,
            "rows": rows,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except KeyError:
        raise
    except Exception as exc:
        message = safe_connection_error(exc, source.url)
        raise ValueError(f"PostgreSQL 表预览失败: {message}") from exc


def table_rows(source_name: str, table: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    source = ds_cache.get_source(source_name)
    if source.dialect == "postgresql":
        return _postgresql_table_rows(
            source,
            table,
            max(1, min(int(limit), 200)),
            max(0, int(offset)),
        )
    path = _sqlite_path_from_url(source.url)
    table = _quote_ident(table)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        rows = conn.execute(f"SELECT * FROM {table} LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        columns = [d[1] for d in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        return {"columns": columns, "rows": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> tuple[list[str], str]:
    rows = conn.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()
    if not rows:
        raise KeyError(table)
    columns = [r[1] for r in rows]
    pk = next((r[1] for r in rows if r[5]), columns[0])
    return columns, pk


def _ensure_writable(source_name: str) -> dict[str, Any]:
    entry = _source_entry(source_name)
    if not entry.get("writable", False):
        raise PermissionError("该数据源未开启数据维护")
    if not str(entry.get("url") or "").startswith("sqlite:///"):
        raise PermissionError("当前仅支持维护 SQLite 数据源")
    return entry


def _audit(actor: str, source: str, table: str, action: str, pk: Any, before: Any, after: Any) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    item = {
        "id": uuid4().hex,
        "created_at": _now(),
        "actor": actor,
        "source": source,
        "table": table,
        "action": action,
        "pk": pk,
        "before": before,
        "after": after,
    }
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def insert_row(source_name: str, table: str, values: dict[str, Any], actor: str) -> dict[str, Any]:
    entry = _ensure_writable(source_name)
    path = _sqlite_path_from_url(entry["url"])
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        columns, pk = _table_columns(conn, table)
        data = {k: v for k, v in values.items() if k in columns and k != pk}
        if not data:
            raise ValueError("没有可写入字段")
        col_sql = ", ".join(_quote_ident(k) for k in data)
        marks = ", ".join("?" for _ in data)
        cur = conn.execute(f"INSERT INTO {_quote_ident(table)} ({col_sql}) VALUES ({marks})", list(data.values()))
        conn.commit()
        new_pk = cur.lastrowid
        row = dict(conn.execute(f"SELECT * FROM {_quote_ident(table)} WHERE {_quote_ident(pk)} = ?", (new_pk,)).fetchone())
        _audit(actor, source_name, table, "insert", new_pk, None, row)
        return {"row": row}
    finally:
        conn.close()


def update_row(source_name: str, table: str, pk_value: Any, values: dict[str, Any], actor: str) -> dict[str, Any]:
    entry = _ensure_writable(source_name)
    path = _sqlite_path_from_url(entry["url"])
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        columns, pk = _table_columns(conn, table)
        before_row = conn.execute(f"SELECT * FROM {_quote_ident(table)} WHERE {_quote_ident(pk)} = ?", (pk_value,)).fetchone()
        if not before_row:
            raise KeyError(pk_value)
        data = {k: v for k, v in values.items() if k in columns and k != pk}
        if not data:
            raise ValueError("没有可更新字段")
        set_sql = ", ".join(f"{_quote_ident(k)} = ?" for k in data)
        conn.execute(f"UPDATE {_quote_ident(table)} SET {set_sql} WHERE {_quote_ident(pk)} = ?", [*data.values(), pk_value])
        conn.commit()
        after = dict(conn.execute(f"SELECT * FROM {_quote_ident(table)} WHERE {_quote_ident(pk)} = ?", (pk_value,)).fetchone())
        _audit(actor, source_name, table, "update", pk_value, dict(before_row), after)
        return {"row": after}
    finally:
        conn.close()


def delete_row(source_name: str, table: str, pk_value: Any, actor: str) -> dict[str, Any]:
    entry = _ensure_writable(source_name)
    path = _sqlite_path_from_url(entry["url"])
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        columns, pk = _table_columns(conn, table)
        before_row = conn.execute(f"SELECT * FROM {_quote_ident(table)} WHERE {_quote_ident(pk)} = ?", (pk_value,)).fetchone()
        if not before_row:
            raise KeyError(pk_value)
        before = dict(before_row)
        conn.execute(f"DELETE FROM {_quote_ident(table)} WHERE {_quote_ident(pk)} = ?", (pk_value,))
        conn.commit()
        _audit(actor, source_name, table, "delete", pk_value, before, None)
        return {"deleted": True, "row": before}
    finally:
        conn.close()


def audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    if not AUDIT_FILE.exists():
        return []
    lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    items = []
    for line in lines[-max(1, min(limit, 500)):]:
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return list(reversed(items))


def save_upload(filename: str, content: bytes) -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".db", ".sqlite", ".sqlite3"}:
        raise ValueError("仅支持 .csv / .db / .sqlite 文件")
    path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    path.write_bytes(content)
    return path


def copy_uploaded_db(name: str, src: Path) -> Path:
    name = _safe_name(name)
    MANAGED_DB_DIR.mkdir(parents=True, exist_ok=True)
    dst = MANAGED_DB_DIR / f"{name}.db"
    if dst.exists():
        raise ValueError(f"托管数据库已存在: {dst}")
    shutil.copyfile(src, dst)
    return dst
