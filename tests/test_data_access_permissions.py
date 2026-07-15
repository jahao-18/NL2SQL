import importlib
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import data_access
from app.main import app


client = TestClient(app)


def _headers(token: str) -> dict[str, str]:
    return {"X-Demo-Token": token}


def test_source_list_redacts_non_admin_url_and_filters_tables_by_scope():
    teacher_response = client.get("/api/data-access/sources", headers=_headers("teacher"))
    assert teacher_response.status_code == 200
    teaching = next(item for item in teacher_response.json()["items"] if item["name"] == "teaching")
    assert teaching["url"] == ""
    assert "student" not in teaching["tables"]
    assert teaching["table_count"] == len(teaching["tables"])

    admin_response = client.get("/api/data-access/sources", headers=_headers("admin"))
    assert admin_response.status_code == 200
    admin_teaching = next(item for item in admin_response.json()["items"] if item["name"] == "teaching")
    assert admin_teaching["url"] == "sqlite:///data/teaching.db"
    assert "student" in admin_teaching["tables"]


def test_teacher_scan_and_rows_only_expose_direct_personal_scope():
    scan = client.post("/api/data-access/sources/teaching/scan", headers=_headers("teacher"), json={})
    assert scan.status_code == 200
    tables = scan.json()["tables"]
    assert "student" not in tables
    assert tables
    for table, columns in tables.items():
        assert table == "teacher" or "teacher_id" in columns

    denied = client.get(
        "/api/data-access/sources/teaching/tables/student/rows?limit=1",
        headers=_headers("teacher"),
    )
    assert denied.status_code == 403

    allowed = client.get(
        "/api/data-access/sources/teaching/tables/teaching_class/rows?limit=200",
        headers=_headers("teacher"),
    )
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["rows"]
    assert payload["total"] == len(payload["rows"])
    assert all(row["teacher_id"] == 37 for row in payload["rows"])


def test_college_rows_are_limited_to_bound_college():
    response = client.get(
        "/api/data-access/sources/teaching/tables/student/rows?limit=200",
        headers=_headers("college"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"]
    assert payload["total"] > len(payload["rows"])
    assert all(row["college_id"] == 1 for row in payload["rows"])


def test_academic_office_keeps_allowed_table_but_not_denied_teacher_number():
    response = client.get(
        "/api/data-access/sources/teaching/tables/teacher/rows?limit=1",
        headers=_headers("jwc"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert "teacher_no" not in payload["columns"]
    assert payload["rows"]
    assert "teacher_no" not in payload["rows"][0]


def test_audit_is_filtered_by_table_columns_and_row_scope(monkeypatch):
    api = importlib.import_module("app.api.data_access")
    monkeypatch.setattr(
        api,
        "audit_logs",
        lambda limit: [
            {
                "id": "own",
                "table": "teaching_class",
                "before": {"id": 1, "teacher_id": 37, "course_id": 10},
                "after": {"id": 1, "teacher_id": 37, "course_id": 11},
            },
            {
                "id": "other",
                "table": "teaching_class",
                "before": {"id": 2, "teacher_id": 38, "course_id": 10},
                "after": {"id": 2, "teacher_id": 38, "course_id": 11},
            },
            {
                "id": "student",
                "table": "student",
                "before": {"id": 1, "student_no": "S001", "name": "controlled"},
                "after": None,
            },
        ],
    )

    response = client.get("/api/data-access/audit?limit=10", headers=_headers("teacher"))
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == ["own"]
    assert items[0]["before"]["teacher_id"] == 37


def test_api_rejects_disallowed_write_before_storage(monkeypatch):
    api = importlib.import_module("app.api.data_access")
    calls = []
    monkeypatch.setattr(
        api,
        "insert_row",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"row": {}},
    )

    response = client.post(
        "/api/data-access/sources/teaching/tables/student/rows",
        headers=_headers("teacher"),
        json={"values": {"name": "controlled"}},
    )
    assert response.status_code == 403
    assert calls == []


@pytest.fixture
def scoped_sqlite(tmp_path, monkeypatch):
    path = tmp_path / "scoped.db"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE teaching_class ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "teacher_id INTEGER NOT NULL, "
            "title TEXT NOT NULL, "
            "secret TEXT DEFAULT ''"
            ")"
        )
        conn.executemany(
            "INSERT INTO teaching_class (teacher_id, title, secret) VALUES (?, ?, ?)",
            [(37, "own", "a"), (38, "other", "b")],
        )
        conn.commit()
    finally:
        conn.close()

    url = f"sqlite:///{path}"
    monkeypatch.setattr(data_access.ds_cache, "get_source", lambda name: SimpleNamespace(url=url))
    monkeypatch.setattr(data_access, "_ensure_writable", lambda name: {"url": url})
    audits = []
    monkeypatch.setattr(data_access, "_audit", lambda *args: audits.append(args))
    return path, audits


def test_core_read_filters_columns_rows_and_total(scoped_sqlite):
    result = data_access.table_rows(
        "controlled",
        "teaching_class",
        limit=200,
        allowed_columns={"id", "teacher_id", "title"},
        required_scope={"teacher_id": 37},
    )
    assert result["columns"] == ["id", "teacher_id", "title"]
    assert result["total"] == 1
    assert result["rows"] == [{"id": 1, "teacher_id": 37, "title": "own"}]


def test_core_insert_enforces_scope_and_denied_columns(scoped_sqlite):
    _, audits = scoped_sqlite
    allowed = {"id", "teacher_id", "title"}

    inserted = data_access.insert_row(
        "controlled",
        "teaching_class",
        {"title": "new"},
        "teacher",
        allowed_columns=allowed,
        required_scope={"teacher_id": 37},
    )
    assert inserted["row"]["teacher_id"] == 37
    assert inserted["row"]["title"] == "new"
    assert "secret" not in inserted["row"]
    assert len(audits) == 1

    with pytest.raises(PermissionError, match="范围之外"):
        data_access.insert_row(
            "controlled",
            "teaching_class",
            {"teacher_id": 38, "title": "wrong"},
            "teacher",
            allowed_columns=allowed,
            required_scope={"teacher_id": 37},
        )
    with pytest.raises(PermissionError, match="不能写入字段"):
        data_access.insert_row(
            "controlled",
            "teaching_class",
            {"title": "wrong", "secret": "hidden"},
            "teacher",
            allowed_columns=allowed,
            required_scope={"teacher_id": 37},
        )
    assert len(audits) == 1


def test_core_update_and_delete_reject_cross_scope(scoped_sqlite):
    _, audits = scoped_sqlite
    allowed = {"id", "teacher_id", "title"}

    updated = data_access.update_row(
        "controlled",
        "teaching_class",
        1,
        {"title": "updated"},
        "teacher",
        allowed_columns=allowed,
        required_scope={"teacher_id": 37},
    )
    assert updated["row"] == {"id": 1, "teacher_id": 37, "title": "updated"}

    with pytest.raises(PermissionError, match="范围之外"):
        data_access.update_row(
            "controlled",
            "teaching_class",
            2,
            {"title": "blocked"},
            "teacher",
            allowed_columns=allowed,
            required_scope={"teacher_id": 37},
        )
    with pytest.raises(PermissionError, match="账号范围"):
        data_access.update_row(
            "controlled",
            "teaching_class",
            1,
            {"teacher_id": 38},
            "teacher",
            allowed_columns=allowed,
            required_scope={"teacher_id": 37},
        )
    with pytest.raises(PermissionError, match="范围之外"):
        data_access.delete_row(
            "controlled",
            "teaching_class",
            2,
            "teacher",
            allowed_columns=allowed,
            required_scope={"teacher_id": 37},
        )

    deleted = data_access.delete_row(
        "controlled",
        "teaching_class",
        1,
        "teacher",
        allowed_columns=allowed,
        required_scope={"teacher_id": 37},
    )
    assert deleted == {"deleted": True, "row": {"id": 1, "teacher_id": 37, "title": "updated"}}
    assert [entry[3] for entry in audits] == ["update", "delete"]
