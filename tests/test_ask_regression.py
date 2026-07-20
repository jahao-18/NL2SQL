from __future__ import annotations

from app import service
from app.core.data_sources import DataSource
from app.core.schema import SchemaInfo
from app.core.config import STATIC_DIR
from app.core.retrieval.base import RetrievedContext


def _source(name: str = "teaching") -> DataSource:
    return DataSource(name=name, label=name, url="sqlite:///unused.db", dialect="sqlite", glossary_path=None, schema_profile_path=None)


def _schema() -> SchemaInfo:
    ddl = "CREATE TABLE enrollment (id INTEGER, student_id INTEGER);"
    return SchemaInfo(ddl_text=ddl, pure_ddl=ddl, tables={"enrollment": ["id", "student_id"]}, columns={})


def _base_mocks(monkeypatch, *, source_name: str = "teaching") -> None:
    monkeypatch.setattr(service, "get_source", lambda _name: _source(source_name))
    monkeypatch.setattr(service, "load_schema", lambda _name: _schema())
    monkeypatch.setattr(service, "retrieve_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "stash_judge", lambda *_args, **_kwargs: "judge-test")
    monkeypatch.setattr(service, "explain_query", lambda *_args, **_kwargs: {"summary": "ok"})


def test_ask_success_chain_keeps_scope_validation_and_result_format(monkeypatch):
    _base_mocks(monkeypatch)
    monkeypatch.setattr(service, "generate_sql", lambda *_args, **_kwargs: ("sql", "SELECT COUNT(*) AS n FROM enrollment e WHERE e.student_id = 1"))
    monkeypatch.setattr(service, "execute", lambda sql, source_name=None: (["n"], [[2]], 3, False))
    result = service.ask(
        "我的选课数量",
        source="teaching",
        allowed_tables={"enrollment"},
        row_scope={"student_id": 1},
        role_label="学生",
    )
    assert result["error"] is None
    assert result["rows"] == [[2]]
    assert "student_id = 1" in result["sql"]
    assert result["source"] == "teaching"


def test_ask_repairs_unscoped_sql_before_any_execution(monkeypatch):
    _base_mocks(monkeypatch)
    executed: list[str] = []
    monkeypatch.setattr(service, "generate_sql", lambda *_args, **_kwargs: ("sql", "SELECT COUNT(*) FROM enrollment"))
    monkeypatch.setattr(service, "repair_sql", lambda *_args, **_kwargs: "SELECT COUNT(*) FROM enrollment e WHERE e.student_id = 1")
    monkeypatch.setattr(service, "execute", lambda sql, source_name=None: (executed.append(sql) or ["count"], [[1]], 1, False))
    result = service.ask(
        "我的选课数量",
        source="teaching",
        allowed_tables={"enrollment"},
        row_scope={"student_id": 1},
        role_label="学生",
    )
    assert result["error"] is None
    assert len(executed) == 1
    assert "student_id = 1" in executed[0]


def test_ask_repairs_model_policy_violation_instead_of_reporting_user_unauthorized(monkeypatch):
    _base_mocks(monkeypatch)
    blocked_schema = _schema()
    blocked_schema.blocked_columns = {"enrollment.student_id"}
    monkeypatch.setattr(service, "load_schema", lambda _name: blocked_schema)
    executed: list[str] = []
    monkeypatch.setattr(
        service,
        "generate_sql",
        lambda *_args, **_kwargs: ("sql", "SELECT e.student_id FROM enrollment e WHERE e.student_id = 1"),
    )
    monkeypatch.setattr(
        service,
        "repair_sql",
        lambda *_args, **_kwargs: "SELECT COUNT(*) AS n FROM enrollment e WHERE e.student_id = 1",
    )
    monkeypatch.setattr(service, "execute", lambda sql, source_name=None: (executed.append(sql) or ["n"], [[2]], 1, False))
    result = service.ask(
        "我的选课数量",
        source="teaching",
        allowed_tables={"enrollment"},
        denied_columns={"enrollment.student_id"},
        row_scope={"student_id": 1},
        role_label="学生",
    )
    assert result["error"] is None
    assert result["rows"] == [[2]]
    assert len(executed) == 1


def test_retrieval_cannot_reintroduce_table_outside_authorized_schema(monkeypatch):
    _base_mocks(monkeypatch)
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        service,
        "retrieve_context",
        lambda *_args, **_kwargs: RetrievedContext(
            context_text="表 academic_warning:\n  - student_id INTEGER",
            tables=["academic_warning"],
            retrievers_used=["keyword"],
        ),
    )
    def generate(schema, *_args, **_kwargs):
        captured["schema"] = schema
        return "sql", "SELECT COUNT(*) AS n FROM enrollment e"
    monkeypatch.setattr(service, "generate_sql", generate)
    monkeypatch.setattr(service, "execute", lambda sql, source_name=None: (["n"], [[3]], 1, False))
    result = service.ask("选课数量", source="teaching", allowed_tables={"enrollment"}, role_label="教师")
    assert result["error"] is None
    assert "academic_warning" not in captured["schema"]
    assert "CREATE TABLE enrollment" in captured["schema"]


def test_service_passes_role_filtered_schema_to_retrieval(monkeypatch):
    _base_mocks(monkeypatch)
    captured = {}

    def retrieve(_question, _source, schema_info):
        captured["schema_info"] = schema_info
        return None

    monkeypatch.setattr(service, "retrieve_context", retrieve)
    monkeypatch.setattr(service, "generate_sql", lambda *_args, **_kwargs: ("sql", "SELECT COUNT(*) FROM enrollment"))
    monkeypatch.setattr(service, "execute", lambda *_args, **_kwargs: (["n"], [[1]], 1, False))

    result = service.ask(
        "选课数量",
        source="teaching",
        allowed_tables={"enrollment"},
        denied_columns={"enrollment.student_id"},
        role_label="教师",
    )

    assert result["error"] is None
    assert set(captured["schema_info"].tables) == {"enrollment"}
    assert "enrollment.student_id" in captured["schema_info"].blocked_columns


def test_ask_denied_term_stops_before_llm_and_execution(monkeypatch):
    _base_mocks(monkeypatch)
    monkeypatch.setattr(service, "generate_sql", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM must not run")))
    monkeypatch.setattr(service, "execute", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("SQL must not run")))
    result = service.ask(
        "显示其他学生名单",
        source="teaching",
        allowed_tables={"enrollment"},
        denied_terms=["学生名单"],
        role_label="学生",
    )
    assert "无权查询" in result["error"]


def test_ask_llm_and_retrieval_failures_are_isolated(monkeypatch):
    _base_mocks(monkeypatch)
    monkeypatch.setattr(service, "retrieve_context", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("retrieval down")))
    monkeypatch.setattr(service, "generate_sql", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("llm down")))
    result = service.ask("查询数量", source="teaching", allowed_tables={"enrollment"})
    assert "LLM 调用失败" in result["error"]
    assert result["rows"] == []


def test_external_admin_source_is_not_filtered_by_teaching_table_policy(monkeypatch):
    _base_mocks(monkeypatch, source_name="external")
    external = SchemaInfo(
        ddl_text="CREATE TABLE external_fact (id INTEGER);",
        pure_ddl="CREATE TABLE external_fact (id INTEGER);",
        tables={"external_fact": ["id"]},
        columns={},
    )
    monkeypatch.setattr(service, "load_schema", lambda _name: external)
    monkeypatch.setattr(service, "generate_sql", lambda *_args, **_kwargs: ("sql", "SELECT COUNT(*) FROM external_fact"))
    monkeypatch.setattr(service, "execute", lambda sql, source_name=None: (["count"], [[3]], 1, False))
    result = service.ask("外部事实数量", source="external", allowed_tables=set(), row_scope={"student_id": 1})
    assert result["error"] is None
    assert result["rows"] == [[3]]


def test_frontend_skips_ask_bootstrap_for_profiles_without_ask_permission():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert '["ask","knowledge","schema","governance","data_access"].some(hasFeature)' in script
    assert 'if (hasFeature("ask")) return "assistant-view";' in script
    assert 'return "profile-view";' in script
    assert "showView(preferredHomeView())" in script
