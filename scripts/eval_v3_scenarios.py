"""Validate and execute the V3 role-aware assistant scenario evaluation set."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from app.core import assignment_workflow, assistant_orchestrator, authorization, teaching_migrations  # noqa: E402
from app.core.business_domains import token_for, user_from_token  # noqa: E402
from app.main import app  # noqa: E402


DEFAULT_CASES = ROOT / "tests" / "v3_scenario_eval_cases.yaml"
REQUIRED_CATEGORIES = {
    "fixed_metric", "nl2sql", "contextual_follow_up", "ambiguous_clarification",
    "unauthorized", "empty_result", "small_sample", "retrieval_degraded",
}
REQUIRED_EXCLUSIONS = {"institutional_knowledge", "hybrid_data_policy"}
ROLE_USERS = {
    "student": "stu_zhang",
    "teacher": "tea_li",
    "counselor": "counselor_chen",
    "college_manager": "college",
    "academic_office": "jwc",
    "admin": "admin",
}


@dataclass
class ScenarioResult:
    case_id: str
    category: str
    role: str
    outcome: str
    reason: str


def load_suite(path: Path = DEFAULT_CASES) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError("评测集根节点必须是对象")
    return loaded


def validate_suite(suite: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    cases = suite.get("cases") or []
    if suite.get("version") != 1:
        errors.append("version 必须为 1")
    if not isinstance(cases, list) or not cases:
        return errors + ["cases 必须是非空列表"]
    ids: set[str] = set()
    categories: set[str] = set()
    roles: set[str] = set()
    for index, case in enumerate(cases, 1):
        prefix = f"case[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        case_id = str(case.get("id") or "")
        if not case_id:
            errors.append(f"{prefix} 缺少 id")
        elif case_id in ids:
            errors.append(f"{prefix} id 重复: {case_id}")
        ids.add(case_id)
        category = str(case.get("category") or "")
        role = str(case.get("role") or "")
        categories.add(category)
        roles.add(role)
        if role not in ROLE_USERS:
            errors.append(f"{case_id} role 不受支持: {role}")
        if case.get("execution") not in {"deterministic", "model"}:
            errors.append(f"{case_id} execution 必须是 deterministic 或 model")
        if not str(case.get("question") or "").strip():
            errors.append(f"{case_id} 缺少 question")
        if category == "contextual_follow_up" and not case.get("turns"):
            errors.append(f"{case_id} 上下文追问场景必须声明 turns")
        if not isinstance(case.get("context"), dict) or not case["context"].get("page"):
            errors.append(f"{case_id} 缺少页面 context")
        expected = case.get("expected")
        if not isinstance(expected, dict) or "http_status" not in expected or not isinstance(expected.get("scope"), dict):
            errors.append(f"{case_id} expected 必须包含 http_status 和 scope")
        if not isinstance(case.get("forbidden_response"), list) or not case["forbidden_response"]:
            errors.append(f"{case_id} 必须声明 forbidden_response")
        sql = case.get("sql_constraints")
        if not isinstance(sql, dict) or not isinstance(sql.get("required"), list) or not isinstance(sql.get("forbidden"), list):
            errors.append(f"{case_id} 必须声明 SQL required/forbidden 约束")
        actions = case.get("action_policy")
        if not isinstance(actions, dict) or not isinstance(actions.get("allowed"), bool) or not isinstance(actions.get("allowed_types"), list):
            errors.append(f"{case_id} 必须声明动作草稿策略")
    missing_categories = REQUIRED_CATEGORIES - categories
    if missing_categories:
        errors.append(f"缺少场景类别: {sorted(missing_categories)}")
    missing_roles = set(ROLE_USERS) - roles
    if missing_roles:
        errors.append(f"缺少角色覆盖: {sorted(missing_roles)}")
    exclusions = set((suite.get("excluded_categories") or {}).keys())
    if not REQUIRED_EXCLUSIONS <= exclusions:
        errors.append("V3-4 未实现类别必须显式记录为 excluded_categories")
    return errors


@contextmanager
def isolated_database() -> Iterator[None]:
    original = teaching_migrations.DB_PATH
    original_auth = authorization.DB_PATH
    original_assignment = assignment_workflow.DB_PATH
    # Windows may keep the SQLite handle briefly after TestClient lifespan exit.
    # The system temp root remains isolated; a transient cleanup lock must not
    # turn an otherwise valid evaluation into a scenario failure.
    with tempfile.TemporaryDirectory(prefix="nl2sql-v3-eval-", ignore_cleanup_errors=True) as temp:
        target = Path(temp) / "teaching.db"
        shutil.copy2(original, target)
        teaching_migrations.DB_PATH = target
        authorization.DB_PATH = target
        assignment_workflow.DB_PATH = target
        try:
            teaching_migrations.ensure_mvp_schema()
            yield
        finally:
            teaching_migrations.DB_PATH = original
            authorization.DB_PATH = original_auth
            assignment_workflow.DB_PATH = original_assignment


def _resolve(value: Any, auth: Any, context: dict[str, Any] | None = None) -> Any:
    if isinstance(value, dict):
        return {key: _resolve(item, auth, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, auth, context) for item in value]
    if value == "$owned_teaching_class":
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            row = conn.execute(
                "SELECT id FROM teaching_class WHERE teacher_id=? ORDER BY id LIMIT 1",
                (auth.row_scope["teacher_id"],),
            ).fetchone()
        if not row:
            raise ValueError("当前教师没有可用于评测的授课班")
        return int(row[0])
    if value == "$other_student":
        own = int(auth.row_scope.get("student_id") or 0)
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            row = conn.execute("SELECT id FROM student WHERE id<>? ORDER BY id LIMIT 1", (own,)).fetchone()
        if not row:
            raise ValueError("没有可用于越权评测的其他学生")
        return int(row[0])
    if value == "$owned_college":
        return int(auth.row_scope["college_id"])
    if isinstance(value, str) and value.startswith("$context."):
        return (context or {}).get(value.split(".", 1)[1])
    return value


def evaluate_case(case: dict[str, Any], client: TestClient) -> ScenarioResult:
    role = case["role"]
    auth = user_from_token(token_for(ROLE_USERS[role]))
    context = _resolve(case["context"], auth)
    expected = _resolve(case["expected"], auth, context)
    payload = {"question": case["question"], "context": context}
    if case.get("options"):
        payload["options"] = case["options"]
    headers = {"X-Demo-Token": token_for(ROLE_USERS[role])}
    response = None
    session_id = None
    questions = [*case.get("turns", []), case["question"]]
    fault = case.get("fault")
    fault_context = patch.object(assistant_orchestrator, "ask_service", _retrieval_degraded_result) if fault == "retrieval_degraded" else _null_context()
    with fault_context:
        for question in questions:
            turn_payload = dict(payload)
            turn_payload["question"] = question
            if session_id:
                turn_payload["session_id"] = session_id
            response = client.post("/api/assistant/query", headers=headers, json=turn_payload)
            if response.status_code == 200:
                session_id = response.json().get("session_id")
            elif question != questions[-1]:
                return ScenarioResult(case["id"], case["category"], role, "failed", f"前序轮次 HTTP {response.status_code}")
    assert response is not None
    failures: list[str] = []
    if response.status_code != expected["http_status"]:
        failures.append(f"HTTP {response.status_code} != {expected['http_status']}")
    body = response.json()
    if response.status_code == 200:
        if body.get("status") not in expected.get("statuses", []):
            failures.append(f"status={body.get('status')}")
        if body.get("answer_type") not in expected.get("answer_types", []):
            failures.append(f"answer_type={body.get('answer_type')}")
        for key, value in expected.get("scope", {}).items():
            if body.get("scope", {}).get(key) != value:
                failures.append(f"scope.{key}={body.get('scope', {}).get(key)!r} != {value!r}")
        warning_codes = {item.get("code") for item in body.get("warnings") or []}
        for code in expected.get("warning_codes", []):
            if code not in warning_codes:
                failures.append(f"缺少 warning {code}")
        sql = str(body.get("sql") or "")
        for pattern in case["sql_constraints"]["required"]:
            if not re.search(pattern, sql, re.IGNORECASE | re.DOTALL):
                failures.append(f"SQL 缺少约束 /{pattern}/")
        for pattern in case["sql_constraints"]["forbidden"]:
            if re.search(pattern, sql, re.IGNORECASE | re.DOTALL):
                failures.append(f"SQL 命中禁止约束 /{pattern}/")
        action_types = {item.get("type") for item in body.get("suggested_actions") or []}
        policy = case["action_policy"]
        if not policy["allowed"] and action_types:
            failures.append(f"不应产生动作: {sorted(action_types)}")
        if action_types - set(policy["allowed_types"]):
            failures.append(f"产生未允许动作: {sorted(action_types - set(policy['allowed_types']))}")
    encoded = json.dumps(body, ensure_ascii=False).lower()
    for token in case["forbidden_response"]:
        if str(token).lower() in encoded:
            failures.append(f"响应出现禁止内容: {token}")
    return ScenarioResult(
        case_id=case["id"], category=case["category"], role=role,
        outcome="failed" if failures else "passed",
        reason="；".join(failures) if failures else "契约满足",
    )


@contextmanager
def _null_context() -> Iterator[None]:
    yield


def _retrieval_degraded_result(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {
        "sql": "SELECT c.name, COUNT(*) FROM student s JOIN major m ON s.major_id=m.id JOIN college c ON m.college_id=c.id GROUP BY c.name LIMIT 200",
        "columns": ["学院", "学生人数"],
        "column_sources": ["college.name", "student.id"],
        "rows": [["示例学院", 1]],
        "row_count": 1,
        "elapsed_ms": 1,
        "truncated": False,
        "error": None,
        "clarify": None,
        "source": "teaching",
        "source_label": "教学业务库",
        "auto_routed": False,
        "confidence": 90,
        "confidence_detail": {"reason": "故障注入后的安全回退结果"},
        "trace": {
            "retrieval_status": "degraded",
            "retrievers_used": ["safe_fallback"],
            "degraded": True,
            "degradation_reason": "评测故障注入：检索服务不可用",
        },
    }


def run_suite(suite: dict[str, Any], *, include_model: bool = False) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    with isolated_database(), TestClient(app) as client:
        for case in suite["cases"]:
            if case["execution"] == "model" and not include_model:
                results.append(ScenarioResult(case["id"], case["category"], case["role"], "skipped", "需要 --include-model"))
                continue
            try:
                results.append(evaluate_case(case, client))
            except Exception as exc:
                results.append(ScenarioResult(case["id"], case["category"], case["role"], "failed", str(exc)))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="V3 多角色智能问数场景评测")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--validate-only", action="store_true", help="只校验评测集契约")
    parser.add_argument("--include-model", action="store_true", help="同时执行依赖当前模型/检索配置的场景")
    parser.add_argument("--json", type=Path, help="写出不包含问题正文和回答正文的 JSON 结果")
    args = parser.parse_args()
    suite = load_suite(args.cases)
    errors = validate_suite(suite)
    if errors:
        for error in errors:
            print(f"[INVALID] {error}")
        return 1
    print(f"评测集契约有效：{len(suite['cases'])} 个场景")
    if args.validate_only:
        return 0
    results = run_suite(suite, include_model=args.include_model)
    for item in results:
        print(f"[{item.outcome.upper():7}] {item.case_id:<38} {item.role:<16} {item.reason}")
    summary = {state: sum(item.outcome == state for item in results) for state in ("passed", "failed", "skipped")}
    print(f"结果：{summary['passed']} 通过 / {summary['failed']} 失败 / {summary['skipped']} 跳过")
    if args.json:
        report = {"suite_version": suite["version"], "summary": summary, "results": [asdict(item) for item in results]}
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 2 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
