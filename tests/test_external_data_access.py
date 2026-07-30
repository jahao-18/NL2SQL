from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from app.api import data_access as data_access_api
from app.api import routes as api_routes
from app.core import data_access, data_sources
from app.core.business_domains import AuthorizationError, token_for
from app.core.config import STATIC_DIR
from app.core.schema import SchemaInfo


def _headers(username: str) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username)}


def _postgresql_payload() -> dict[str, object]:
    return {
        "name": "library_pg",
        "label": "图书业务 PostgreSQL",
        "host": "localhost",
        "port": 5432,
        "database": "library",
        "username": "library_reader",
        "password_env": "TEST_LIBRARY_PG_PASSWORD",
        "sslmode": "prefer",
    }


def _isolate_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    registry = tmp_path / "data_sources.yaml"
    registry.write_text("sources: []\n", encoding="utf-8")
    monkeypatch.setattr(data_access, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(data_access, "DATA_SOURCES_FILE", registry)
    monkeypatch.setattr(data_access, "_clear_runtime_caches", lambda: None)
    monkeypatch.setattr(data_access, "_write_starter_profile", lambda _name, _tables: "")
    return registry


def test_postgresql_register_endpoint_is_admin_only_and_never_accepts_password(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    def fake_register(*args):
        captured["args"] = args
        return {
            "item": {
                "name": "library_pg",
                "url": "postgresql+psycopg://library_reader@localhost:5432/library",
                "writable": False,
            },
            "scan": {"table_count": 1, "column_count": 2, "tables": {"book": ["id", "title"]}},
        }

    monkeypatch.setattr(data_access_api, "register_postgresql_source", fake_register)
    payload = _postgresql_payload()
    assert "password" not in payload
    request = data_access_api.RegisterPostgresqlRequest(**payload)

    with pytest.raises(AuthorizationError):
        data_access_api.register_postgresql(
            request,
            ctx=token_for("stu_zhang"),
        )
    accepted = data_access_api.register_postgresql(
        request,
        ctx=token_for("admin"),
    )

    assert any(
        getattr(route, "path", "") == "/api/data-access/sources/postgresql"
        for route in data_access_api.router.routes
    )
    assert captured["args"][6] == "TEST_LIBRARY_PG_PASSWORD"
    assert "password_env" not in accepted["item"]


def test_postgresql_registration_persists_only_environment_reference(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    registry = _isolate_registry(monkeypatch, tmp_path)
    monkeypatch.setenv("TEST_LIBRARY_PG_PASSWORD", "unit-only-secret")

    def fake_scan(url: str) -> dict[str, list[str]]:
        assert make_url(url).password == "unit-only-secret"
        return {"branch": ["id", "name"], "book": ["id", "title", "branch_id"]}

    monkeypatch.setattr(data_access, "_scan_url", fake_scan)
    result = data_access.register_postgresql_source(
        "library_pg",
        "图书业务 PostgreSQL",
        "localhost",
        5432,
        "library",
        "library_reader",
        "TEST_LIBRARY_PG_PASSWORD",
        "prefer",
    )

    saved = yaml.safe_load(registry.read_text(encoding="utf-8"))["sources"][0]
    assert saved["password_env"] == "TEST_LIBRARY_PG_PASSWORD"
    assert "unit-only-secret" not in registry.read_text(encoding="utf-8")
    assert make_url(saved["url"]).password is None
    assert result["item"]["writable"] is False
    assert "password_env" not in result["item"]
    assert result["scan"]["table_count"] == 2
    assert result["scan"]["column_count"] == 5


def test_postgresql_registration_rolls_back_registry_and_new_glossary_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    registry = _isolate_registry(monkeypatch, tmp_path)
    monkeypatch.setenv("TEST_LIBRARY_PG_PASSWORD", "unit-only-secret")
    monkeypatch.setattr(data_access, "_scan_url", lambda _url: {"book": ["id"]})
    monkeypatch.setattr(
        data_access,
        "_write_starter_profile",
        lambda _name, _tables: (_ for _ in ()).throw(RuntimeError("profile failed")),
    )

    with pytest.raises(RuntimeError, match="profile failed"):
        data_access.register_postgresql_source(
            "library_pg",
            "图书业务 PostgreSQL",
            "localhost",
            5432,
            "library",
            "library_reader",
            "TEST_LIBRARY_PG_PASSWORD",
        )

    assert yaml.safe_load(registry.read_text(encoding="utf-8"))["sources"] == []
    assert not (tmp_path / "data" / "glossaries" / "library_pg.md").exists()
    assert not (tmp_path / "data" / "schema_profiles" / "library_pg.yaml").exists()


def test_source_url_can_resolve_password_from_local_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.delenv("TEST_LIBRARY_PG_PASSWORD", raising=False)
    monkeypatch.setattr(data_sources, "ROOT_DIR", tmp_path)
    (tmp_path / ".env").write_text("TEST_LIBRARY_PG_PASSWORD=local-only-secret\n", encoding="utf-8")
    resolved = data_sources.resolve_source_url(
        "postgresql+psycopg://library_reader@localhost:5432/library",
        "TEST_LIBRARY_PG_PASSWORD",
    )
    assert make_url(resolved).password == "local-only-secret"


def test_data_source_url_redaction_hides_existing_inline_password():
    redacted = data_access._redact_url(
        "postgresql+psycopg://library_reader:inline-secret@localhost:5432/library"
    )
    assert "inline-secret" not in redacted
    assert "***" in redacted


def test_connection_error_does_not_echo_inline_password(monkeypatch: pytest.MonkeyPatch):
    url = "postgresql+psycopg://library_reader:inline-secret@localhost:5432/library"
    monkeypatch.setattr(
        data_access_api,
        "test_connection",
        lambda _url: (_ for _ in ()).throw(RuntimeError(f"cannot connect with {url}")),
    )
    with pytest.raises(HTTPException) as raised:
        data_access_api.test(
            data_access_api.TestConnectionRequest(url=url),
            ctx=token_for("admin"),
        )
    assert raised.value.status_code == 400
    assert "inline-secret" not in str(raised.value.detail)
    assert "***" in str(raised.value.detail)


def test_external_schema_keeps_external_tables_and_filters_profile_blocked_columns(
    monkeypatch: pytest.MonkeyPatch,
):
    info = SchemaInfo(
        ddl_text='CREATE TABLE "branch" (\n  "id" INTEGER,\n  "secret" TEXT\n);',
        pure_ddl='CREATE TABLE "branch" (\n  "id" INTEGER,\n  "secret" TEXT\n);',
        tables={"branch": ["id", "secret"]},
        columns={
            "branch": [
                {"table_name": "branch", "column_name": "id", "data_type": "INTEGER"},
                {"table_name": "branch", "column_name": "secret", "data_type": "TEXT"},
            ]
        },
        blocked_columns={"branch.secret"},
    )
    monkeypatch.setattr(api_routes, "get_source", lambda _source: SimpleNamespace(name="library_pg"))
    monkeypatch.setattr(api_routes, "load_schema", lambda _source: info)

    response = api_routes.get_schema(
        source="library_pg",
        ctx=token_for("admin"),
    )
    payload = response.model_dump()
    assert payload["tables"] == {"branch": ["id"]}
    assert [column["column_name"] for column in payload["columns"]["branch"]] == ["id"]
    assert "secret" not in payload["ddl"]


def test_postgresql_form_and_api_client_are_present():
    html = Path(STATIC_DIR / "index.html").read_text(encoding="utf-8")
    api_js = Path(STATIC_DIR / "api.js").read_text(encoding="utf-8")
    view_js = Path(STATIC_DIR / "data-access-view.js").read_text(encoding="utf-8")

    assert 'data-access-tab="postgresql"' in html
    assert 'id="postgresql-source-form"' in html
    assert 'id="postgresql-source-password-env"' in html
    assert 'type="password"' not in html.split('id="postgresql-source-form"', 1)[1].split("</form>", 1)[0]
    assert "/api/data-access/sources/postgresql" in api_js
    assert "registerPostgresqlSource" in view_js
    assert "const form = e.currentTarget;" in view_js
    assert "form.reset();" in view_js
    assert "e.currentTarget.reset();" not in view_js
    assert 'selected.dialect === "postgresql"' in view_js
    assert "postgresqlBrowseOnly" in view_js
    assert 'addButton.style.display = postgresqlBrowseOnly ? "none" : "";' in view_js
    assert "/data-access-view.js?v=zjh-021" in html


def test_postgresql_table_preview_uses_read_only_sqlalchemy_path(
    monkeypatch: pytest.MonkeyPatch,
):
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE book (id INTEGER PRIMARY KEY, title TEXT NOT NULL)"))
        conn.execute(
            text("INSERT INTO book (id, title) VALUES (1, '数据库系统'), (2, '软件工程')")
        )
    source = SimpleNamespace(
        name="library_pg",
        dialect="postgresql",
        url="postgresql+psycopg://library_reader@localhost:5432/library",
    )
    monkeypatch.setattr(data_access.ds_cache, "get_source", lambda _name: source)
    monkeypatch.setattr(data_access.ds_cache, "get_engine", lambda _source: engine)

    result = data_access.table_rows("library_pg", "book", limit=1, offset=1)

    assert result == {
        "columns": ["id", "title"],
        "rows": [{"id": 2, "title": "软件工程"}],
        "total": 2,
        "limit": 1,
        "offset": 1,
    }
    with pytest.raises(KeyError):
        data_access.table_rows("library_pg", "missing_table")
    engine.dispose()


def test_sqlite_table_preview_contract_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    db_path = tmp_path / "library.sqlite"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE book (id INTEGER PRIMARY KEY, title TEXT NOT NULL)"))
        conn.execute(text("INSERT INTO book (id, title) VALUES (1, '编译原理')"))
    engine.dispose()
    source = SimpleNamespace(
        name="library_sqlite",
        dialect="sqlite",
        url=f"sqlite:///{db_path.as_posix()}",
    )
    monkeypatch.setattr(data_access.ds_cache, "get_source", lambda _name: source)

    result = data_access.table_rows("library_sqlite", "book")

    assert result["columns"] == ["id", "title"]
    assert result["rows"] == [{"id": 1, "title": "编译原理"}]
    assert result["total"] == 1


def test_postgresql_table_preview_api_remains_admin_only(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        data_access_api,
        "table_rows",
        lambda source, table, limit, offset: {
            "source": source,
            "table": table,
            "columns": ["id"],
            "rows": [{"id": 1}],
            "total": 1,
        },
    )

    with pytest.raises(AuthorizationError):
        data_access_api.rows(
            "library_pg",
            "book",
            ctx=token_for("stu_zhang"),
        )
    accepted = data_access_api.rows(
        "library_pg",
        "book",
        ctx=token_for("admin"),
    )
    assert accepted["source"] == "library_pg"
    assert accepted["total"] == 1


def test_postgresql_source_remains_non_writable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    registry = _isolate_registry(monkeypatch, tmp_path)
    registry.write_text(
        yaml.safe_dump(
            {
                "sources": [
                    {
                        "name": "library_pg",
                        "url": "postgresql+psycopg://library_reader@localhost:5432/library",
                        "writable": False,
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(PermissionError, match="未开启数据维护"):
        data_access.insert_row("library_pg", "book", {"title": "不能写入"}, "admin")
