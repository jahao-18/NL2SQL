"""Data onboarding and maintenance APIs."""
from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.business_domains import AuthContext, require_feature, user_from_token
from app.core.data_access import (
    audit_logs,
    copy_uploaded_db,
    import_csv_as_source,
    insert_row,
    list_registered_sources,
    register_sqlite_source,
    save_upload,
    scan_source,
    table_rows,
    test_connection,
    update_row,
    delete_row,
)


router = APIRouter(prefix="/api/data-access")


class TestConnectionRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=1000)


class RegisterSqliteRequest(BaseModel):
    name: str
    label: str = ""
    db_path: str
    writable: bool = False


class CsvImportRequest(BaseModel):
    name: str
    label: str = ""
    table_name: str = "imported_data"
    csv_text: str
    writable: bool = True


class RowRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


def _require_maintainer(token: str | None):
    return require_feature(user_from_token(token), "data_access")


def _require_admin(token: str | None):
    ctx = user_from_token(token)
    if ctx.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以新增数据源")
    return ctx


def _table_policy(
    auth: AuthContext,
    table: str,
    columns: list[str],
) -> tuple[set[str], dict[str, Any]]:
    if not auth.is_admin and table not in auth.allowed_tables:
        raise HTTPException(status_code=403, detail="当前角色不能访问该表")
    visible = {
        column
        for column in columns
        if auth.is_admin or f"{table}.{column}" not in auth.denied_columns
    }
    if not visible:
        raise HTTPException(status_code=403, detail="当前角色没有可访问字段")
    for key in auth.row_scope:
        entity = key[:-3] if key.endswith("_id") else ""
        if key not in columns and not (entity == table and "id" in columns):
            raise HTTPException(status_code=403, detail="当前账号范围无法安全应用到该表")
    return visible, dict(auth.row_scope)


def _filtered_scan(auth: AuthContext, report: dict[str, Any]) -> dict[str, Any]:
    tables: dict[str, list[str]] = {}
    for table, columns in (report.get("tables") or {}).items():
        try:
            visible, _ = _table_policy(auth, table, list(columns))
        except HTTPException:
            continue
        tables[table] = [column for column in columns if column in visible]
    return {
        **report,
        "tables": tables,
        "table_count": len(tables),
        "column_count": sum(len(columns) for columns in tables.values()),
    }


def _filtered_sources(auth: AuthContext, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        safe = dict(item)
        if not auth.is_admin:
            safe["url"] = ""
        try:
            report = scan_source(str(item.get("name") or ""))
            filtered = _filtered_scan(auth, report)
            tables = list(filtered["tables"])
        except Exception:
            tables = []
        safe["tables"] = tables
        safe["table_count"] = len(tables)
        out.append(safe)
    return out


def _table_access(auth: AuthContext, source: str, table: str) -> tuple[set[str], dict[str, Any]]:
    report = scan_source(source)
    columns = (report.get("tables") or {}).get(table)
    if columns is None:
        raise KeyError(table)
    return _table_policy(auth, table, list(columns))


def _filtered_audit(auth: AuthContext, items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        table = str(item.get("table") or "")
        sample = item.get("after") if isinstance(item.get("after"), dict) else item.get("before")
        columns = list(sample) if isinstance(sample, dict) else []
        try:
            visible, scope = _table_policy(auth, table, columns)
        except HTTPException:
            continue
        if scope:
            resolved: dict[str, Any] = {}
            for key, value in scope.items():
                entity = key[:-3] if key.endswith("_id") else ""
                column = key if key in columns else "id" if entity == table and "id" in columns else ""
                if not column or not isinstance(sample, dict) or sample.get(column) != value:
                    resolved = {}
                    break
                resolved[column] = value
            if not resolved:
                continue
        safe = dict(item)
        for side in ("before", "after"):
            row = item.get(side)
            if isinstance(row, dict):
                safe[side] = {column: row[column] for column in row if column in visible}
        out.append(safe)
        if len(out) >= limit:
            break
    return out


@router.get("/sources")
def sources(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _require_maintainer(ctx)
    return {"items": _filtered_sources(auth, list_registered_sources())}


@router.post("/test")
def test(req: TestConnectionRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    _require_admin(ctx)
    try:
        return test_connection(req.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sources/sqlite")
def register_sqlite(req: RegisterSqliteRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    _require_admin(ctx)
    try:
        return register_sqlite_source(req.name, req.label, req.db_path, req.writable)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sources/csv")
def import_csv(req: CsvImportRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    _require_admin(ctx)
    try:
        with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as f:
            f.write(req.csv_text)
            tmp = Path(f.name)
        try:
            return import_csv_as_source(req.name, req.label, req.table_name, tmp, writable=req.writable)
        finally:
            tmp.unlink(missing_ok=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sources/db-file")
def import_db_file(payload: dict[str, Any], ctx=Header(None, alias="X-Demo-Token")) -> dict:
    _require_admin(ctx)
    try:
        name = str(payload.get("name") or "")
        label = str(payload.get("label") or "")
        filename = str(payload.get("filename") or f"{name}.db")
        content = str(payload.get("content_base64") or "")
        import base64
        uploaded = save_upload(filename, base64.b64decode(content))
        managed = copy_uploaded_db(name, uploaded)
        return register_sqlite_source(name, label, str(managed), bool(payload.get("writable", False)))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sources/{source}/scan")
def scan(source: str, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _require_maintainer(ctx)
    try:
        return _filtered_scan(auth, scan_source(source))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sources/{source}/tables/{table}/rows")
def rows(
    source: str,
    table: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    auth = _require_maintainer(ctx)
    try:
        visible, scope = _table_access(auth, source, table)
        return table_rows(
            source,
            table,
            limit=limit,
            offset=offset,
            allowed_columns=visible,
            required_scope=scope,
        )
    except HTTPException:
        raise
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sources/{source}/tables/{table}/rows")
def create_row(source: str, table: str, req: RowRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _require_maintainer(ctx)
    try:
        visible, scope = _table_access(auth, source, table)
        return insert_row(
            source,
            table,
            req.values,
            auth.username,
            allowed_columns=visible,
            required_scope=scope,
        )
    except HTTPException:
        raise
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/sources/{source}/tables/{table}/rows/{pk}")
def patch_row(source: str, table: str, pk: str, req: RowRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _require_maintainer(ctx)
    try:
        visible, scope = _table_access(auth, source, table)
        return update_row(
            source,
            table,
            pk,
            req.values,
            auth.username,
            allowed_columns=visible,
            required_scope=scope,
        )
    except HTTPException:
        raise
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/sources/{source}/tables/{table}/rows/{pk}")
def remove_row(source: str, table: str, pk: str, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _require_maintainer(ctx)
    try:
        visible, scope = _table_access(auth, source, table)
        return delete_row(
            source,
            table,
            pk,
            auth.username,
            allowed_columns=visible,
            required_scope=scope,
        )
    except HTTPException:
        raise
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/audit")
def audit(limit: int = Query(100, ge=1, le=500), ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _require_maintainer(ctx)
    return {"items": _filtered_audit(auth, audit_logs(500), limit)}
