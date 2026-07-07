"""执行准确率评估 CLI。

跑 tests/eval_cases.yaml 中所有 case,每个 case:
  1. 调 generate_sql 拿预测 SQL(或 CLARIFY)
  2. 调 validate_and_fix 走和生产相同的安全/LIMIT 链路
  3. 执行预测 SQL 和标准 SQL,按 case.match 比较结果集
  4. 输出分类通过率 + 失败详情

用法:
    python scripts/eval.py                    # 全量
    python scripts/eval.py --filter multi_    # 只跑 id 前缀匹配的
    python scripts/eval.py --source demo_sqlite
    python scripts/eval.py --verbose          # 显示失败 case 详情
    python scripts/eval.py --json out.json    # 把结果写 JSON
退出码 0=全通过,2=有失败,1=参数/加载错误。
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# 让脚本能从项目根直接跑
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.chain import generate_sql  # noqa: E402
from app.core.data_sources import get_source  # noqa: E402
from app.core.executor import SQLExecutionError, execute  # noqa: E402
from app.core.schema import load_schema  # noqa: E402
from app.core.validator import SQLValidationError, validate_and_fix  # noqa: E402
from app.models.schemas import Turn  # noqa: E402

CASES_FILE = ROOT / "tests" / "eval_cases.yaml"


@dataclass
class CaseResult:
    case_id: str
    category: str
    passed: bool
    reason: str
    elapsed_ms: int
    predicted_sql: str | None = None
    predicted_clarify: str | None = None
    expected_kind: str = "sql"


def _normalize_rows(rows: list[list[Any]]) -> list[tuple]:
    """把结果行规整为可比较的元组列表。None 保留;数字统一字符串化避免 1 vs 1.0。"""
    return [tuple("∅" if c is None else str(c) for c in r) for r in rows]


def _cmp_rowset(actual: list[list], expected: list[list]) -> bool:
    return sorted(_normalize_rows(actual)) == sorted(_normalize_rows(expected))


def _cmp_ordered(actual: list[list], expected: list[list]) -> bool:
    return _normalize_rows(actual) == _normalize_rows(expected)


def _cmp_cell(actual: list[list], expected: list[list]) -> bool:
    if not actual or not expected or not actual[0] or not expected[0]:
        return False
    return str(actual[0][0]) == str(expected[0][0])


COMPARATORS = {
    "rowset": _cmp_rowset,
    "ordered": _cmp_ordered,
    "cell": _cmp_cell,
}


def run_case(case: dict) -> CaseResult:
    case_id = case.get("id", "<no-id>")
    category = case.get("category", "uncategorized")
    source_name = case.get("source")  # None => 默认源
    history_data = case.get("history") or []

    try:
        history = [
            Turn(question=t["question"], sql=t["sql"], kind=t.get("kind", "sql"))
            for t in history_data
        ]
    except Exception as e:
        return CaseResult(case_id, category, False, f"history 解析失败: {e}", 0)

    ds = get_source(source_name)
    schema_info = load_schema(ds.name)
    expected_kind = case.get("expected")  # clarify / error_placeholder / None(普通 SQL)

    start = time.perf_counter()
    try:
        kind, content = generate_sql(
            schema_info.ddl_text, case["question"], history, dialect=ds.dialect,
        )
    except Exception as e:
        return CaseResult(case_id, category, False, f"LLM 调用失败: {e}",
                          int((time.perf_counter() - start) * 1000))
    elapsed = int((time.perf_counter() - start) * 1000)

    # 期望 clarify
    if expected_kind == "clarify":
        if kind == "clarify":
            return CaseResult(case_id, category, True, "clarify 触发,符合预期",
                              elapsed, predicted_clarify=content, expected_kind="clarify")
        return CaseResult(case_id, category, False,
                          f"期望 clarify,实际返回 SQL: {content[:100]}",
                          elapsed, predicted_sql=content, expected_kind="clarify")

    # 期望 "无法回答" 占位 SQL
    if expected_kind == "error_placeholder":
        if kind == "sql" and "无法回答" in content:
            return CaseResult(case_id, category, True, "回退占位符,符合预期",
                              elapsed, predicted_sql=content, expected_kind="error_placeholder")
        if kind == "clarify":
            return CaseResult(case_id, category, False,
                              f"期望占位 SQL,实际触发 clarify: {content[:100]}",
                              elapsed, predicted_clarify=content, expected_kind="error_placeholder")
        return CaseResult(case_id, category, False,
                          f"期望占位 SQL,实际是常规 SQL: {content[:120]}",
                          elapsed, predicted_sql=content, expected_kind="error_placeholder")

    # 普通 SQL 比对
    if kind != "sql":
        return CaseResult(case_id, category, False,
                          f"期望 SQL,实际触发 clarify: {content[:100]}",
                          elapsed, predicted_clarify=content)

    try:
        safe_pred, _ = validate_and_fix(content, schema_info.tables)
    except SQLValidationError as e:
        return CaseResult(case_id, category, False, f"预测 SQL 校验失败: {e}",
                          elapsed, predicted_sql=content)

    try:
        cols_pred, rows_pred, _, _ = execute(safe_pred, source_name=ds.name)
    except SQLExecutionError as e:
        return CaseResult(case_id, category, False, f"预测 SQL 执行失败: {e}",
                          elapsed, predicted_sql=content)

    try:
        gold_sql = case["expected_sql"].strip()
        safe_gold, _ = validate_and_fix(gold_sql, schema_info.tables)
        cols_gold, rows_gold, _, _ = execute(safe_gold, source_name=ds.name)
    except (SQLValidationError, SQLExecutionError, KeyError) as e:
        return CaseResult(case_id, category, False, f"标准 SQL 无法执行: {e}",
                          elapsed, predicted_sql=content)

    if len(cols_pred) != len(cols_gold):
        return CaseResult(
            case_id, category, False,
            f"列数不匹配: predicted {len(cols_pred)} {cols_pred} vs expected {len(cols_gold)} {cols_gold}",
            elapsed, predicted_sql=content,
        )

    match_type = case.get("match", "rowset")
    cmp = COMPARATORS.get(match_type)
    if cmp is None:
        return CaseResult(case_id, category, False, f"未知 match 类型: {match_type}",
                          elapsed, predicted_sql=content)

    if cmp(rows_pred, rows_gold):
        return CaseResult(case_id, category, True,
                          f"{match_type} 通过 ({len(rows_pred)} 行)",
                          elapsed, predicted_sql=content)

    head_pred = rows_pred[:2]
    head_gold = rows_gold[:2]
    return CaseResult(
        case_id, category, False,
        f"结果集不一致 | predicted {len(rows_pred)} 行, expected {len(rows_gold)} 行 | "
        f"pred_head={head_pred} gold_head={head_gold}",
        elapsed, predicted_sql=content,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="NL2SQL 执行准确率评估")
    parser.add_argument("--filter", default="", help="只跑 id 前缀匹配的 case")
    parser.add_argument("--source", default="", help="只跑指定 source 的 case")
    parser.add_argument("--verbose", action="store_true", help="显示失败 case 详情")
    parser.add_argument("--json", metavar="PATH", help="把结果写入 JSON 文件")
    parser.add_argument("--cases", default=str(CASES_FILE), help="评估集 yaml 路径")
    args = parser.parse_args()

    cases_path = Path(args.cases)
    if not cases_path.exists():
        print(f"评估集不存在: {cases_path}", file=sys.stderr)
        return 1

    with cases_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    cases = data.get("cases") or []
    if args.filter:
        cases = [c for c in cases if str(c.get("id", "")).startswith(args.filter)]
    if args.source:
        cases = [c for c in cases if c.get("source", "demo_sqlite") == args.source]

    if not cases:
        print("没有匹配的 case。", file=sys.stderr)
        return 1

    print(f"运行 {len(cases)} 个 case...\n")
    results: list[CaseResult] = []
    for c in cases:
        r = run_case(c)
        results.append(r)
        mark = "[OK]" if r.passed else "[FAIL]"
        print(f"  {mark} {r.case_id:<14}  {r.category:<20} {r.elapsed_ms:>5}ms  {r.reason}")

    # 分类汇总
    by_cat: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r)

    print(f"\n{'类别':<22}{'通过 / 总数':>16}{'通过率':>12}")
    print("-" * 54)
    for cat in sorted(by_cat):
        group = by_cat[cat]
        passed = sum(1 for r in group if r.passed)
        rate = passed / len(group) * 100
        print(f"{cat:<22}{passed:>6} / {len(group):<6}{rate:>10.1f}%")

    total_passed = sum(1 for r in results if r.passed)
    total_rate = total_passed / len(results) * 100
    avg_ms = sum(r.elapsed_ms for r in results) // len(results)
    print("-" * 54)
    print(f"{'总计':<22}{total_passed:>6} / {len(results):<6}{total_rate:>10.1f}%")
    print(f"\nLLM 平均耗时: {avg_ms} ms/case  ·  总耗时: {sum(r.elapsed_ms for r in results)} ms")

    if args.verbose:
        failures = [r for r in results if not r.passed]
        if failures:
            print(f"\n--- 失败详情 ({len(failures)}) ---")
            for r in failures:
                print(f"\n  [FAIL] {r.case_id} ({r.category})")
                print(f"    原因: {r.reason}")
                if r.predicted_sql:
                    print(f"    predicted SQL: {r.predicted_sql[:200]}")
                if r.predicted_clarify:
                    print(f"    predicted CLARIFY: {r.predicted_clarify[:200]}")

    if args.json:
        out = {
            "summary": {
                "total": len(results),
                "passed": total_passed,
                "rate": total_rate,
                "avg_ms": avg_ms,
            },
            "by_category": {
                cat: {
                    "total": len(g),
                    "passed": sum(1 for r in g if r.passed),
                }
                for cat, g in by_cat.items()
            },
            "results": [dataclasses.asdict(r) for r in results],
        }
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已写入 {args.json}")

    return 0 if total_passed == len(results) else 2


if __name__ == "__main__":
    sys.exit(main())
