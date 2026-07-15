from __future__ import annotations

import json
from types import SimpleNamespace

from app import service
from app.core import judge as judge_module


class _FakeJudgeLlm:
    def __init__(self, captured):
        self.captured = captured

    def invoke(self, messages):
        self.captured.append(messages)
        return SimpleNamespace(content=json.dumps({
            "retrieval_score": 90,
            "correctness_score": 92,
            "reason": "系统在当前账号可查看的数据范围内完成了统计。",
        }, ensure_ascii=False))


def _run_controlled_judge(monkeypatch, *, role_label, row_scope):
    captured = []
    monkeypatch.setattr(judge_module.settings, "judge_enabled", True)
    monkeypatch.setattr(judge_module, "make_llm", lambda _model: _FakeJudgeLlm(captured))
    result = judge_module.judge(
        question="平均成绩是多少？",
        schema_text="CREATE TABLE enrollment(student_id INTEGER)",
        sql="SELECT AVG(final_score) FROM enrollment WHERE student_id = 1",
        columns=["average_score"],
        rows=[[82.5]],
        row_count=1,
        dialect="sqlite",
        retrieval_used=True,
        role_label=role_label,
        row_scope=row_scope,
    )
    assert result is not None
    return captured[0][1].content


def test_judge_message_includes_trusted_mandatory_scope(monkeypatch):
    message = _run_controlled_judge(
        monkeypatch,
        role_label="学生",
        row_scope={"student_id": 1},
    )

    assert "Role: 学生" in message
    assert 'Required row filters: {"student_id": 1}' in message
    assert "trusted authorization constraints" in message


def test_judge_message_does_not_invent_scope_for_admin(monkeypatch):
    message = _run_controlled_judge(monkeypatch, role_label="管理员", row_scope=None)

    assert "Role: 管理员" in message
    assert "No mandatory account-level row filter" in message
    assert "Required row filters:" not in message


def test_stash_preserves_scope_for_background_worker(monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, *, target, args, daemon, name):
            self.target = target
            self.args = args
            self.daemon = daemon
            self.name = name

        def start(self):
            started.append(self)

    monkeypatch.setattr(judge_module.settings, "judge_enabled", True)
    monkeypatch.setattr(judge_module.threading, "Thread", FakeThread)
    jid = judge_module.stash(
        "平均成绩是多少？", "schema", "SELECT 1", ["value"], [[1]], 1, "sqlite", True,
        role_label="教师", row_scope={"teacher_id": 37},
    )

    try:
        assert jid is not None
        assert len(started) == 1
        with judge_module._pending_lock:
            args = judge_module._pending[jid]["args"]
        assert args["role_label"] == "教师"
        assert args["row_scope"] == {"teacher_id": 37}
    finally:
        if jid is not None:
            with judge_module._pending_lock:
                judge_module._pending.pop(jid, None)


def test_service_forwards_scope_to_validator_and_judge(monkeypatch):
    calls = {}
    schema_info = SimpleNamespace(
        ddl_text="CREATE TABLE enrollment(student_id INTEGER, final_score REAL)",
        tables={"enrollment": ["student_id", "final_score"]},
        blocked_columns=set(),
    )
    monkeypatch.setattr(
        service,
        "get_source",
        lambda _source: SimpleNamespace(name="teaching", label="教学数据库", dialect="sqlite"),
    )
    monkeypatch.setattr(service, "list_table_names", lambda _source: [])
    monkeypatch.setattr(service, "load_schema", lambda _source: schema_info)
    monkeypatch.setattr(service, "retrieve_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        service,
        "generate_sql",
        lambda *_args, **_kwargs: ("sql", "SELECT AVG(final_score) FROM enrollment WHERE student_id = 1"),
    )

    def fake_validate(sql, _tables, _blocked_columns, *, required_scope):
        calls["validator_scope"] = required_scope
        return sql, False

    monkeypatch.setattr(service, "validate_and_fix", fake_validate)
    monkeypatch.setattr(
        service,
        "execute",
        lambda *_args, **_kwargs: (["average_score"], [[82.5]], 1, False),
    )
    monkeypatch.setattr(service, "extract_column_sources", lambda _sql: [])
    monkeypatch.setattr(service, "explain_query", lambda *_args, **_kwargs: {})

    def fake_stash(**kwargs):
        calls["judge"] = kwargs
        return "controlled-judge"

    monkeypatch.setattr(service, "stash_judge", fake_stash)

    result = service.ask(
        "平均成绩是多少？",
        source="teaching",
        role_label="学生",
        row_scope={"student_id": 1},
    )

    assert result["judge_id"] == "controlled-judge"
    assert calls["validator_scope"] == {"student_id": 1}
    assert calls["judge"]["role_label"] == "学生"
    assert calls["judge"]["row_scope"] == {"student_id": 1}
