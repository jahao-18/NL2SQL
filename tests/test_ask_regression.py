from __future__ import annotations

import sqlite3

from app import service
from app.core import chain
from app.core.data_sources import DataSource
from app.core.schema import SchemaInfo
from app.core.config import STATIC_DIR
from app.core.retrieval.base import RetrievedContext
from app.models.schemas import Turn


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


def test_teaching_sql_system_prompt_contains_unfinished_assignment_hard_rules():
    messages = chain._chat_prompt().format_messages(
        schema="CREATE TABLE assignment (id INTEGER);",
        question="我有哪些作业未完成",
        history=[],
        current_date="2026-07-27",
        dialect="sqlite",
        dialect_notes=chain.dialect_notes("sqlite"),
    )
    system_prompt = str(messages[0].content)

    assert "双条件 `LEFT JOIN assignment_submission`" in system_prompt
    assert "完全没有提交记录、`missing`、`not_submitted`、`returned` 属于未完成" in system_prompt
    assert "`submitted`、`late`、`late_submitted`、`resubmitted`" in system_prompt
    assert "assignment.status IN ('published', 'closed')" in system_prompt
    assert "严禁擅自增加 due_time 条件" in system_prompt
    assert "不得改成 assignment_submission 内连接" in system_prompt
    assert "不得直接使用 `due_time <= 'YYYY-MM-DD'`" in system_prompt
    assert "当日零点（含）到次日零点（不含）" in system_prompt


def test_unfinished_assignment_date_boundary_guard_rejects_raw_date_upper_bound():
    sql = (
        "SELECT a.title FROM enrollment e "
        "JOIN assignment a ON a.teaching_class_id=e.teaching_class_id "
        "LEFT JOIN assignment_submission s "
        "ON s.assignment_id=a.id AND s.student_id=e.student_id "
        "WHERE e.student_id=900001 "
        "AND a.status IN ('published','closed') "
        "AND (s.id IS NULL OR s.status IN ('missing','not_submitted','returned')) "
        "AND a.due_time <= '2026-12-31'"
    )

    error = service._unfinished_assignment_semantic_error(
        sql,
        "我有哪些在2026年12月31日截止且仍未完成的作业",
        [],
    )

    assert error is not None
    assert "2026-12-31" in error
    assert "2027-01-01" in error


def test_unfinished_assignment_date_boundary_guard_accepts_exact_and_through_day_forms():
    sql_prefix = (
        "SELECT a.title FROM enrollment e "
        "JOIN assignment a ON a.teaching_class_id=e.teaching_class_id "
        "LEFT JOIN assignment_submission s "
        "ON s.assignment_id=a.id AND s.student_id=e.student_id "
        "WHERE e.student_id=900001 "
        "AND a.status IN ('published','closed') "
        "AND (s.id IS NULL OR s.status IN ('missing','not_submitted','returned')) "
    )
    accepted = [
        (
            "我有哪些在2026年12月31日截止且仍未完成的作业",
            sql_prefix
            + "AND a.due_time >= '2026-12-31' AND a.due_time < '2027-01-01'",
        ),
        (
            "我有哪些在2026年12月31日截止且仍未完成的作业",
            sql_prefix + "AND date(a.due_time) = '2026-12-31'",
        ),
        (
            "截至2026年12月31日，我有哪些仍未完成的作业",
            sql_prefix + "AND a.due_time < '2027-01-01'",
        ),
        (
            "截至2026年12月31日，我有哪些仍未完成的作业",
            sql_prefix + "AND date(a.due_time) <= '2026-12-31'",
        ),
    ]

    for question, sql in accepted:
        assert service._unfinished_assignment_semantic_error(sql, question, []) is None


def test_exact_day_half_open_range_covers_midnight_end_of_day_and_year_boundary():
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE assignment (due_time TEXT NOT NULL)")
        conn.executemany(
            "INSERT INTO assignment(due_time) VALUES (?)",
            [
                ("2026-12-30T23:59:59",),
                ("2026-12-31T00:00:00",),
                ("2026-12-31T23:59:00",),
                ("2027-01-01T00:00:00",),
            ],
        )
        rows = conn.execute(
            "SELECT due_time FROM assignment "
            "WHERE due_time >= '2026-12-31' AND due_time < '2027-01-01' "
            "ORDER BY due_time"
        ).fetchall()
    finally:
        conn.close()

    assert rows == [
        ("2026-12-31T00:00:00",),
        ("2026-12-31T23:59:00",),
    ]


def test_ask_repairs_unfinished_assignment_date_boundary_before_execution(monkeypatch):
    _base_mocks(monkeypatch)
    ddl = """
    CREATE TABLE enrollment (student_id INTEGER, teaching_class_id INTEGER);
    CREATE TABLE assignment (
        id INTEGER, teaching_class_id INTEGER, title TEXT, status TEXT, due_time TEXT
    );
    CREATE TABLE assignment_submission (
        id INTEGER, assignment_id INTEGER, student_id INTEGER, status TEXT
    );
    """
    schema = SchemaInfo(
        ddl_text=ddl,
        pure_ddl=ddl,
        tables={
            "enrollment": ["student_id", "teaching_class_id"],
            "assignment": ["id", "teaching_class_id", "title", "status", "due_time"],
            "assignment_submission": ["id", "assignment_id", "student_id", "status"],
        },
        columns={},
    )
    sql_prefix = (
        "SELECT a.title FROM enrollment e "
        "JOIN assignment a ON a.teaching_class_id=e.teaching_class_id "
        "LEFT JOIN assignment_submission s "
        "ON s.assignment_id=a.id AND s.student_id=e.student_id "
        "WHERE e.student_id=900001 "
        "AND a.status IN ('published','closed') "
        "AND (s.id IS NULL OR s.status IN ('missing','not_submitted','returned')) "
    )
    invalid_sql = sql_prefix + "AND a.due_time <= '2026-12-31'"
    repaired_sql = (
        sql_prefix
        + "AND a.due_time >= '2026-12-31' AND a.due_time < '2027-01-01'"
    )
    repair_errors: list[str] = []
    executed: list[str] = []
    monkeypatch.setattr(service, "load_schema", lambda _name: schema)
    monkeypatch.setattr(service, "generate_sql", lambda *_args, **_kwargs: ("sql", invalid_sql))

    def _repair(_schema, _question, _previous_sql, error, **_kwargs):
        repair_errors.append(error)
        return repaired_sql

    monkeypatch.setattr(service, "repair_sql", _repair)
    monkeypatch.setattr(
        service,
        "execute",
        lambda sql, source_name=None: (executed.append(sql) or ["title"], [["跨年作业"]], 1, False),
    )

    result = service.ask(
        "我有哪些在2026年12月31日截止且仍未完成的作业",
        source="teaching",
        allowed_tables=set(schema.tables),
        row_scope={"student_id": 900001},
        role_label="学生",
    )

    assert result["error"] is None
    assert len(repair_errors) == 1
    assert "2027-01-01" in repair_errors[0]
    assert len(executed) == 1
    assert "a.due_time < '2027-01-01'" in executed[0]


def test_unfinished_assignment_semantic_guard_rejects_followup_that_loses_statuses():
    history = [
        Turn(
            question="请按课程分组统计我未完成的作业数量",
            sql=(
                "SELECT COUNT(*) FROM enrollment e JOIN assignment a "
                "ON a.teaching_class_id=e.teaching_class_id "
                "LEFT JOIN assignment_submission s "
                "ON s.assignment_id=a.id AND s.student_id=e.student_id "
                "WHERE e.student_id=900001 "
                "AND a.status IN ('published','closed') "
                "AND (s.id IS NULL OR s.status IN ('missing','not_submitted','returned'))"
            ),
        )
    ]
    invalid_cutoff_sql = (
        "SELECT COUNT(*) FROM enrollment e JOIN assignment a "
        "ON a.teaching_class_id=e.teaching_class_id "
        "LEFT JOIN assignment_submission s "
        "ON s.assignment_id=a.id AND s.student_id=e.student_id "
        "WHERE e.student_id=900001 "
        "AND a.status IN ('published','closed') "
        "AND s.id IS NULL AND a.due_time < '2026-07-27'"
    )

    error = service._unfinished_assignment_semantic_error(
        invalid_cutoff_sql,
        "只看已经截止的",
        history,
    )

    assert error is not None
    assert "missing、not_submitted、returned" in error


def test_unfinished_assignment_semantic_guard_does_not_leak_into_new_topic():
    history = [
        Turn(
            question="我有哪些作业未完成",
            sql=(
                "SELECT a.title FROM enrollment e JOIN assignment a "
                "ON a.teaching_class_id=e.teaching_class_id "
                "LEFT JOIN assignment_submission s "
                "ON s.assignment_id=a.id AND s.student_id=e.student_id "
                "WHERE e.student_id=900001"
            ),
        )
    ]

    assert not service._is_student_unfinished_assignment_query("我的平均分是多少", history)
    assert (
        service._unfinished_assignment_semantic_error(
            "SELECT AVG(sc.final_score) FROM score sc "
            "JOIN enrollment e ON e.id=sc.enrollment_id WHERE e.student_id=900001",
            "我的平均分是多少",
            history,
        )
        is None
    )


def test_ask_repairs_unfinished_assignment_inner_join_before_execution(monkeypatch):
    _base_mocks(monkeypatch)
    ddl = """
    CREATE TABLE enrollment (student_id INTEGER, teaching_class_id INTEGER);
    CREATE TABLE assignment (
        id INTEGER, teaching_class_id INTEGER, title TEXT, status TEXT, due_time TEXT
    );
    CREATE TABLE assignment_submission (
        id INTEGER, assignment_id INTEGER, student_id INTEGER, status TEXT
    );
    """
    schema = SchemaInfo(
        ddl_text=ddl,
        pure_ddl=ddl,
        tables={
            "enrollment": ["student_id", "teaching_class_id"],
            "assignment": ["id", "teaching_class_id", "title", "status", "due_time"],
            "assignment_submission": ["id", "assignment_id", "student_id", "status"],
        },
        columns={},
    )
    invalid_sql = (
        "SELECT a.title FROM enrollment e "
        "JOIN assignment a ON a.teaching_class_id=e.teaching_class_id "
        "JOIN assignment_submission s "
        "ON s.assignment_id=a.id AND s.student_id=e.student_id "
        "WHERE e.student_id=900001 "
        "AND a.status IN ('published','closed') "
        "AND s.status IN ('missing','not_submitted','returned')"
    )
    repaired_sql = (
        "SELECT a.title FROM enrollment e "
        "JOIN assignment a ON a.teaching_class_id=e.teaching_class_id "
        "LEFT JOIN assignment_submission s "
        "ON s.assignment_id=a.id AND s.student_id=e.student_id "
        "WHERE e.student_id=900001 "
        "AND a.status IN ('published','closed') "
        "AND (s.id IS NULL OR s.status IN ('missing','not_submitted','returned'))"
    )
    repair_errors: list[str] = []
    executed: list[str] = []
    monkeypatch.setattr(service, "load_schema", lambda _name: schema)
    monkeypatch.setattr(service, "generate_sql", lambda *_args, **_kwargs: ("sql", invalid_sql))

    def _repair(_schema, _question, _previous_sql, error, **_kwargs):
        repair_errors.append(error)
        return repaired_sql

    monkeypatch.setattr(service, "repair_sql", _repair)
    monkeypatch.setattr(
        service,
        "execute",
        lambda sql, source_name=None: (executed.append(sql) or ["title"], [["作业一"]], 1, False),
    )

    result = service.ask(
        "我有哪些作业未完成",
        source="teaching",
        allowed_tables=set(schema.tables),
        row_scope={"student_id": 900001},
        role_label="学生",
    )

    assert result["error"] is None
    assert len(repair_errors) == 1
    assert "不能使用提交表内连接" in repair_errors[0]
    assert len(executed) == 1
    assert "LEFT JOIN assignment_submission" in executed[0]
    assert "'late'" not in executed[0]


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


def test_ask_repairs_unscoped_submission_alias_before_any_execution(monkeypatch):
    _base_mocks(monkeypatch)
    ddl = """
    CREATE TABLE enrollment (student_id INTEGER, teaching_class_id INTEGER);
    CREATE TABLE assignment (id INTEGER, teaching_class_id INTEGER, title TEXT);
    CREATE TABLE assignment_submission (assignment_id INTEGER, student_id INTEGER, status TEXT);
    """
    schema = SchemaInfo(
        ddl_text=ddl,
        pure_ddl=ddl,
        tables={
            "enrollment": ["student_id", "teaching_class_id"],
            "assignment": ["id", "teaching_class_id", "title"],
            "assignment_submission": ["assignment_id", "student_id", "status"],
        },
        columns={},
    )
    unsafe_sql = (
        "SELECT a.title FROM enrollment e "
        "JOIN assignment a ON a.teaching_class_id = e.teaching_class_id "
        "JOIN assignment_submission asub ON asub.assignment_id = a.id "
        "WHERE e.student_id = 900001 AND asub.status = 'submitted'"
    )
    repaired_sql = (
        "SELECT a.title FROM enrollment e "
        "JOIN assignment a ON a.teaching_class_id = e.teaching_class_id "
        "JOIN assignment_submission asub "
        "ON asub.assignment_id = a.id AND asub.student_id = e.student_id "
        "WHERE e.student_id = 900001 AND asub.status = 'submitted'"
    )
    executed: list[str] = []
    monkeypatch.setattr(service, "load_schema", lambda _name: schema)
    monkeypatch.setattr(service, "generate_sql", lambda *_args, **_kwargs: ("sql", unsafe_sql))
    monkeypatch.setattr(service, "repair_sql", lambda *_args, **_kwargs: repaired_sql)
    monkeypatch.setattr(
        service,
        "execute",
        lambda sql, source_name=None: (executed.append(sql) or ["title"], [["作业一"]], 1, False),
    )

    result = service.ask(
        "我已经完成的作业",
        source="teaching",
        allowed_tables=set(schema.tables),
        row_scope={"student_id": 900001},
        role_label="学生",
    )

    assert result["error"] is None
    assert len(executed) == 1
    assert "asub.student_id = e.student_id" in executed[0]


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


def test_ask_sensitive_identity_term_stops_before_llm_for_every_role(monkeypatch):
    _base_mocks(monkeypatch)
    monkeypatch.setattr(
        service,
        "generate_sql",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("敏感身份标识请求不应调用模型")
        ),
    )
    monkeypatch.setattr(
        service,
        "execute",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("敏感身份标识请求不应执行 SQL")
        ),
    )

    for question, role_label in (
        ("查询所有学生的身份证号", "学生"),
        ("列出全部学生的证件号码", "校级管理员"),
    ):
        result = service.ask(
            question,
            source="teaching",
            allowed_tables={"enrollment"},
            role_label=role_label,
        )
        assert "不可用于问数" in result["error"]
        assert result["rows"] == []


def test_ask_converts_model_unanswerable_placeholder_to_unsupported_error(monkeypatch):
    _base_mocks(monkeypatch)
    placeholder = "无法回答: enrollment 表中没有鞋码字段"
    monkeypatch.setattr(
        service,
        "generate_sql",
        lambda *_args, **_kwargs: (
            "sql",
            "SELECT '无法回答: enrollment 表中没有鞋码字段' AS error LIMIT 1",
        ),
    )
    monkeypatch.setattr(
        service,
        "execute",
        lambda *_args, **_kwargs: (["error"], [[placeholder]], 1, False),
    )

    result = service.ask(
        "查询所有学生的鞋码",
        source="teaching",
        allowed_tables={"enrollment"},
        role_label="校级管理员",
    )

    assert result["error"] == placeholder
    assert result["rows"] == []
    assert result["trace"]["result_kind"] == "unsupported"
    assert "judge_id" not in result


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
