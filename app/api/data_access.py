"""Data onboarding and maintenance APIs."""
from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.business_domains import require_admin
from app.core.config import settings
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
    name: str = Field(..., min_length=2, max_length=49)
    label: str = Field("", max_length=120)
    db_path: str = Field(..., min_length=1, max_length=1000)
    writable: bool = False


class CsvImportRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=49)
    label: str = Field("", max_length=120)
    table_name: str = Field("imported_data", min_length=2, max_length=49)
    csv_text: str
    writable: bool = True


class RowRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


def _require_maintainer(token: str | None):
    return require_admin(token)


def _require_admin(token: str | None):
    return require_admin(token)


@router.get("/sources")
def sources(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    _require_maintainer(ctx)
    return {"items": list_registered_sources()}


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
        if len(req.csv_text.encode("utf-8")) > settings.max_upload_bytes:
            raise ValueError(f"CSV 文件不能超过 {settings.max_upload_bytes // (1024 * 1024)} MB")
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
        if len(content) > (settings.max_upload_bytes * 4 // 3 + 8):
            raise ValueError(f"数据库文件不能超过 {settings.max_upload_bytes // (1024 * 1024)} MB")
        decoded = base64.b64decode(content, validate=True)
        if len(decoded) > settings.max_upload_bytes:
            raise ValueError(f"数据库文件不能超过 {settings.max_upload_bytes // (1024 * 1024)} MB")
        uploaded = save_upload(filename, decoded)
        managed = copy_uploaded_db(name, uploaded)
        return register_sqlite_source(name, label, str(managed), bool(payload.get("writable", False)))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sources/{source}/scan")
def scan(source: str, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    _require_maintainer(ctx)
    try:
        return scan_source(source)
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
    _require_maintainer(ctx)
    try:
        return table_rows(source, table, limit=limit, offset=offset)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sources/{source}/tables/{table}/rows")
def create_row(source: str, table: str, req: RowRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _require_maintainer(ctx)
    try:
        return insert_row(source, table, req.values, auth.username)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/sources/{source}/tables/{table}/rows/{pk}")
def patch_row(source: str, table: str, pk: str, req: RowRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _require_maintainer(ctx)
    try:
        return update_row(source, table, pk, req.values, auth.username)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/sources/{source}/tables/{table}/rows/{pk}")
def remove_row(source: str, table: str, pk: str, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _require_maintainer(ctx)
    try:
        return delete_row(source, table, pk, auth.username)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/audit")
def audit(limit: int = Query(100, ge=1, le=500), ctx=Header(None, alias="X-Demo-Token")) -> dict:
    _require_maintainer(ctx)
    return {"items": audit_logs(limit)}
