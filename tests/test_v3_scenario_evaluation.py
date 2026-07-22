from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "eval_v3_scenarios.py"
SPEC = importlib.util.spec_from_file_location("eval_v3_scenarios", SCRIPT)
assert SPEC and SPEC.loader
EVAL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = EVAL
SPEC.loader.exec_module(EVAL)


def test_v3_scenario_suite_contract_covers_roles_categories_and_safety_fields():
    suite = EVAL.load_suite()
    assert EVAL.validate_suite(suite) == []
    cases = suite["cases"]
    assert EVAL.REQUIRED_CATEGORIES <= {item["category"] for item in cases}
    assert set(EVAL.ROLE_USERS) <= {item["role"] for item in cases}
    assert all(item["expected"]["scope"] for item in cases)
    assert all(item["forbidden_response"] for item in cases)
    assert all("required" in item["sql_constraints"] and "forbidden" in item["sql_constraints"] for item in cases)
    assert all("allowed" in item["action_policy"] and "allowed_types" in item["action_policy"] for item in cases)


def test_v3_unimplemented_policy_categories_are_explicitly_excluded():
    suite = EVAL.load_suite()
    excluded = suite["excluded_categories"]
    assert EVAL.REQUIRED_EXCLUSIONS <= set(excluded)
    assert all("尚未实现" in excluded[key] for key in EVAL.REQUIRED_EXCLUSIONS)


def test_v3_deterministic_scenario_evaluation_passes_without_external_model():
    suite = EVAL.load_suite()
    results = EVAL.run_suite(suite, include_model=False)
    deterministic = [item for item in results if item.outcome != "skipped"]
    assert deterministic
    assert all(item.outcome == "passed" for item in deterministic), [item for item in deterministic if item.outcome != "passed"]
    assert sum(item.outcome == "skipped" for item in results) == sum(item["execution"] == "model" for item in suite["cases"])


def test_v3_evaluation_json_contract_never_contains_questions_or_answers(tmp_path: Path):
    suite = EVAL.load_suite()
    results = [EVAL.ScenarioResult("safe-id", "fixed_metric", "teacher", "passed", "契约满足")]
    report = {"suite_version": suite["version"], "results": [EVAL.asdict(item) for item in results]}
    target = tmp_path / "report.json"
    target.write_text(EVAL.json.dumps(report, ensure_ascii=False), encoding="utf-8")
    rendered = target.read_text(encoding="utf-8")
    assert "question" not in rendered.lower()
    assert "answer" not in rendered.lower()
