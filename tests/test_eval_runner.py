from pathlib import Path
from types import SimpleNamespace

import scripts.eval as eval_runner


def _stub_runtime(monkeypatch, predicted_rows, gold_rows, *, predicted_capped=False, gold_capped=False):
    monkeypatch.setattr(
        eval_runner,
        "get_source",
        lambda _name=None: SimpleNamespace(name="teaching", dialect="sqlite"),
    )
    monkeypatch.setattr(
        eval_runner,
        "load_schema",
        lambda _name: SimpleNamespace(ddl_text="CREATE TABLE metric(value REAL)", tables={"metric"}),
    )
    monkeypatch.setattr(eval_runner, "generate_sql", lambda *_args, **_kwargs: ("sql", "SELECT value FROM metric"))
    monkeypatch.setattr(eval_runner, "validate_and_fix", lambda sql, _tables: (sql, False))

    results = iter(
        [
            (["value"], predicted_rows, 1, predicted_capped),
            (["value"], gold_rows, 1, gold_capped),
        ]
    )
    monkeypatch.setattr(eval_runner, "execute", lambda *_args, **_kwargs: next(results))


def _case(**overrides):
    case = {
        "id": "controlled",
        "category": "controlled",
        "source": "teaching",
        "question": "受控问题",
        "expected_sql": "SELECT value FROM metric",
        "match": "rowset",
        "expected_capped": False,
    }
    case.update(overrides)
    return case


def test_load_cases_inherits_top_level_source(tmp_path: Path):
    cases_file = tmp_path / "cases.yaml"
    cases_file.write_text(
        "source: teaching\ncases:\n  - id: inherited\n    question: test\n"
        "  - id: explicit\n    source: other\n    question: test\n",
        encoding="utf-8",
    )

    cases = eval_runner.load_cases(cases_file)

    assert cases[0]["source"] == "teaching"
    assert cases[1]["source"] == "other"


def test_numeric_comparators_treat_integer_and_float_as_equivalent():
    assert eval_runner._cmp_rowset([[1]], [[1.0]])
    assert eval_runner._cmp_ordered([[1]], [[1.0]])
    assert eval_runner._cmp_cell([[1]], [[1.0]])


def test_run_case_accepts_equivalent_result(monkeypatch):
    _stub_runtime(monkeypatch, [[1.0]], [[1]])

    result = eval_runner.run_case(_case())

    assert result.passed is True
    assert "rowset 通过" in result.reason


def test_run_case_rejects_wrong_or_empty_result(monkeypatch):
    _stub_runtime(monkeypatch, [], [[1]])

    result = eval_runner.run_case(_case())

    assert result.passed is False
    assert "结果集不一致" in result.reason


def test_run_case_rejects_capped_state_mismatch(monkeypatch):
    _stub_runtime(monkeypatch, [[1]], [[1]], predicted_capped=False, gold_capped=True)

    result = eval_runner.run_case(_case(expected_capped=True))

    assert result.passed is False
    assert "预测 SQL 截断状态不匹配" in result.reason


def test_run_case_reports_missing_expected_sql(monkeypatch):
    _stub_runtime(monkeypatch, [[1]], [[1]])
    case = _case()
    del case["expected_sql"]

    result = eval_runner.run_case(case)

    assert result.passed is False
    assert "标准 SQL 无法执行" in result.reason
