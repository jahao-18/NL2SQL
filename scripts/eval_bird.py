"""BIRD 基准评测 CLI:用 BIRD dev 集测你当前 NL2SQL 链路的执行准确率(EX)。

BIRD 的官方主指标 EX(Execution Accuracy)= 执行预测 SQL 与标准 SQL,比对结果集是否一致。
这正好对应本仓库 scripts/eval.py 里的 rowset 比较,所以这里复用同一套生产链路:
  generate_sql(注入 evidence) -> validate_and_fix(仅预测 SQL 走) -> execute -> 结果集比对

与 eval.py 的关键差异(BIRD 适配):
  1. 每个 db_id 是一个独立 SQLite 库 -> 启动时动态生成 bird 专用 data_sources.yaml,
     用 DATA_SOURCES_FILE 指过去,复用现有数据源/schema 加载逻辑,零侵入。
  2. evidence(外部知识提示)是 BIRD 的核心 -> 必须拼进 question 喂给模型。
  3. 标准 SQL(gold)可信且大量使用反引号标识符 -> 直接裸执行,不过 validate_and_fix
     (否则会被表名白名单/LIMIT 逻辑误伤)。只有预测 SQL 走生产校验链路。
  4. BIRD gold 常返回 >200 行且无 ORDER BY -> 默认把 MAX_ROWS 抬到 100000,避免被
     强制 LIMIT 200 砍出假性不一致。可用环境变量 MAX_ROWS 覆盖。
  5. 可选注入每个库的列含义描述(database_description/*.csv)作为 glossary,更贴近官方设定。

用法(先下载并解压 BIRD dev 集,目录里要有 dev.json 和 dev_databases/):
    python scripts/eval_bird.py --bird-dir /path/to/dev -n 80
    python scripts/eval_bird.py --bird-dir /path/to/dev -n 50 --difficulty simple
    python scripts/eval_bird.py --bird-dir /path/to/dev -n 80 --no-glossary
    python scripts/eval_bird.py --bird-dir /path/to/dev -n 80 --json bird_result.json --verbose
退出码 0=有结果正常跑完,1=参数/数据加载错误。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml

# 必须在导入 app 模块之前设好,因为 config.settings 在 import 时就读取 MAX_ROWS。
# BIRD gold 常返回大量行,抬高上限避免被强制 LIMIT 砍出假性不一致。
os.environ.setdefault("MAX_ROWS", "100000")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# BIRD 工作目录:动态生成的数据源配置 + glossary 都放这,避免污染项目其它部分。
WORK_DIR = ROOT / "data" / "bird"


# ───────────────────────── BIRD 数据集读取 ─────────────────────────

@dataclass
class BirdItem:
    qid: int
    db_id: str
    question: str
    evidence: str
    gold_sql: str
    difficulty: str


def _find_dev_json(bird_dir: Path) -> Path:
    """定位 dev.json,兼容 dev.json / dev_20240627/dev.json 等常见解压布局。"""
    for cand in (bird_dir / "dev.json", *bird_dir.glob("**/dev.json")):
        if cand.exists():
            return cand
    raise FileNotFoundError(f"在 {bird_dir} 下找不到 dev.json")


def _db_sqlite_path(databases_root: Path, db_id: str) -> Path:
    """定位某个 db 的 .sqlite 文件,兼容不同嵌套层级。"""
    candidates = [
        databases_root / db_id / f"{db_id}.sqlite",
        databases_root / "dev_databases" / db_id / f"{db_id}.sqlite",
    ]
    for c in candidates:
        if c.exists():
            return c
    hits = list(databases_root.glob(f"**/{db_id}/{db_id}.sqlite"))
    if hits:
        return hits[0]
    raise FileNotFoundError(f"找不到数据库文件: {db_id}.sqlite (在 {databases_root} 下)")


def _databases_root(dev_json: Path) -> Path:
    base = dev_json.parent
    for cand in (base / "dev_databases", base / "database"):
        if cand.exists():
            return cand
    # 退而求其次:dev_json 同级即可,_db_sqlite_path 会做全局 glob
    return base


def load_bird_items(dev_json: Path) -> list[BirdItem]:
    raw = json.loads(dev_json.read_text(encoding="utf-8"))
    items: list[BirdItem] = []
    for i, r in enumerate(raw):
        items.append(
            BirdItem(
                qid=r.get("question_id", i),
                db_id=r["db_id"],
                question=r["question"].strip(),
                evidence=(r.get("evidence") or "").strip(),
                gold_sql=r["SQL"].strip(),
                difficulty=r.get("difficulty", "unknown"),
            )
        )
    return items


# ───────────────────────── glossary(列含义)构建 ─────────────────────────

def _read_csv_rows(path: Path) -> list[dict]:
    """BIRD 的 description CSV 编码不统一,依次尝试 utf-8-sig / gbk / latin-1。"""
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            with path.open(encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except (UnicodeDecodeError, csv.Error):
            continue
    return []


def _pick(row: dict, *keys: str) -> str:
    """大小写/空格不敏感地从 CSV 行里取第一个非空字段。"""
    norm = { (k or "").strip().lower(): (v or "").strip() for k, v in row.items() }
    for k in keys:
        v = norm.get(k.lower())
        if v:
            return v
    return ""


def build_glossary_md(db_dir: Path, db_id: str) -> str:
    """把 database_description/*.csv(每表一个文件)拼成喂给模型的 markdown 列说明。"""
    desc_dir = db_dir / "database_description"
    if not desc_dir.exists():
        return ""
    blocks: list[str] = []
    for csv_path in sorted(desc_dir.glob("*.csv")):
        table = csv_path.stem
        rows = _read_csv_rows(csv_path)
        lines: list[str] = []
        for row in rows:
            col = _pick(row, "original_column_name", "column_name")
            if not col:
                continue
            friendly = _pick(row, "column_name")
            desc = _pick(row, "column_description")
            vdesc = _pick(row, "value_description")
            parts = [f"`{col}`"]
            if friendly and friendly != col:
                parts.append(f"({friendly})")
            text = " ".join(parts)
            if desc:
                text += f": {desc}"
            if vdesc:
                text += f" | 取值含义: {vdesc}"
            lines.append(f"- {text}")
        if lines:
            blocks.append(f"## 表 {table}\n" + "\n".join(lines))
    if not blocks:
        return ""
    return "【列含义业务词表(来自 BIRD database_description)】\n\n" + "\n\n".join(blocks)


# ───────────────────────── 数据源动态注册 ─────────────────────────

def _default_sources() -> list[dict]:
    """读项目根 data_sources.yaml 里已有的源(如 demo_sqlite),供前端模式一并保留。"""
    base = ROOT / "data_sources.yaml"
    if not base.exists():
        return []
    raw = yaml.safe_load(base.read_text(encoding="utf-8")) or {}
    return raw.get("sources") or []


def prepare_sources(items: list[BirdItem], databases_root: Path, use_glossary: bool,
                    include_default: bool = False) -> Path:
    """为传入的每个 db_id 生成一条 source,写出 bird 专用 data_sources.yaml,返回其路径。

    include_default=True 时把项目原有数据源(demo_sqlite 等)也并进来,供前端 uvicorn 使用。
    """
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    glossary_dir = WORK_DIR / "glossaries"
    glossary_dir.mkdir(exist_ok=True)

    db_ids = sorted({it.db_id for it in items})
    sources: list[dict] = list(_default_sources()) if include_default else []
    for db_id in db_ids:
        sqlite_path = _db_sqlite_path(databases_root, db_id)
        # 直接构造只读 + immutable 的 SQLite URI:
        #   - 正斜杠:SQLAlchemy/SQLite URI 不吃 Windows 反斜杠
        #   - mode=ro:只读(data_sources._engine_for_url 见到 mode=ro 已存在便不再二次改写)
        #   - immutable=1:把库当不可变,跳过加锁与 WAL/-shm 访问,否则 BIRD 里 WAL 模式的库
        #     只读打开会报 "unable to open database file";基准库静态,这样最稳。
        posix = sqlite_path.resolve().as_posix()
        url = f"sqlite:///file:{posix}?mode=ro&immutable=1&uri=true"
        entry: dict[str, Any] = {"name": db_id, "label": f"BIRD: {db_id}", "url": url}
        if use_glossary:
            md = build_glossary_md(sqlite_path.parent, db_id)
            if md:
                gpath = glossary_dir / f"{db_id}.md"
                gpath.write_text(md, encoding="utf-8")
                entry["glossary"] = gpath.resolve().as_posix()
        sources.append(entry)

    cfg_path = WORK_DIR / "bird_data_sources.yaml"
    cfg_path.write_text(yaml.safe_dump({"sources": sources}, allow_unicode=True, sort_keys=False),
                        encoding="utf-8")
    return cfg_path


# ───────────────────────── 单题评测 ─────────────────────────

@dataclass
class ItemResult:
    qid: int
    db_id: str
    difficulty: str
    passed: bool
    reason: str
    elapsed_ms: int
    predicted_sql: str | None = None
    mode: str = "ddl"   # ddl=整库DDL / retrieval=多路检索


def _normalize_rows(rows: list[list[Any]]) -> list[tuple]:
    return [tuple("∅" if c is None else str(c) for c in r) for r in rows]


def _ex_match(actual: list[list], expected: list[list]) -> bool:
    """BIRD EX:无序结果集相等(多重集比较)。"""
    return sorted(_normalize_rows(actual)) == sorted(_normalize_rows(expected))


def compose_question(item: BirdItem) -> str:
    """把 evidence 拼进问题——BIRD 的外部知识提示,模型必须看到。"""
    if item.evidence:
        return f"{item.question}\n\n提示(外部知识): {item.evidence}"
    return item.question


def run_item(item: BirdItem, use_retrieval: bool, deps) -> ItemResult:
    (generate_sql, load_schema, execute, validate_and_fix,
     SQLValidationError, SQLExecutionError, retrieve_context) = deps
    mode = "retrieval" if use_retrieval else "ddl"
    schema_info = load_schema(item.db_id)

    # 喂给模型的 schema:整库 DDL,或多路检索召回的精简上下文
    schema_text = schema_info.ddl_text
    if use_retrieval:
        try:
            rc = retrieve_context(compose_question(item), item.db_id, schema_info.ddl_text)
            if rc is not None:
                schema_text = rc.context_text
        except Exception as e:
            return ItemResult(item.qid, item.db_id, item.difficulty, False,
                              f"检索失败: {e}", 0, mode=mode)

    start = time.perf_counter()
    try:
        kind, content = generate_sql(
            schema_text, compose_question(item), [], dialect="sqlite",
        )
    except Exception as e:
        return ItemResult(item.qid, item.db_id, item.difficulty, False,
                          f"LLM 调用失败: {e}", int((time.perf_counter() - start) * 1000), mode=mode)
    elapsed = int((time.perf_counter() - start) * 1000)

    if kind != "sql":
        return ItemResult(item.qid, item.db_id, item.difficulty, False,
                          f"模型触发 clarify 而非 SQL: {content[:80]}", elapsed, mode=mode)

    # 预测 SQL 走生产校验链路(与线上一致)
    try:
        safe_pred, _ = validate_and_fix(content, schema_info.tables)
    except SQLValidationError as e:
        return ItemResult(item.qid, item.db_id, item.difficulty, False,
                          f"预测 SQL 校验失败: {e}", elapsed, predicted_sql=content, mode=mode)
    try:
        _, rows_pred, _, _ = execute(safe_pred, source_name=item.db_id)
    except SQLExecutionError as e:
        return ItemResult(item.qid, item.db_id, item.difficulty, False,
                          f"预测 SQL 执行失败: {e}", elapsed, predicted_sql=content, mode=mode)

    # gold 可信,裸执行(不过 validator)
    try:
        _, rows_gold, _, _ = execute(item.gold_sql, source_name=item.db_id)
    except SQLExecutionError as e:
        return ItemResult(item.qid, item.db_id, item.difficulty, False,
                          f"标准 SQL 无法执行(跳过此题): {e}", elapsed, predicted_sql=content, mode=mode)

    if _ex_match(rows_pred, rows_gold):
        return ItemResult(item.qid, item.db_id, item.difficulty, True,
                          f"EX 通过 ({len(rows_pred)} 行)", elapsed, predicted_sql=content, mode=mode)
    return ItemResult(
        item.qid, item.db_id, item.difficulty, False,
        f"EX 不一致 | pred {len(rows_pred)} 行 vs gold {len(rows_gold)} 行",
        elapsed, predicted_sql=content, mode=mode,
    )


def _run_pass(items: list[BirdItem], use_retrieval: bool, deps) -> list[ItemResult]:
    """跑一遍全部题目(单一模式),边跑边打印,返回结果列表。"""
    results: list[ItemResult] = []
    for it in items:
        r = run_item(it, use_retrieval, deps)
        results.append(r)
        mark = "[OK]" if r.passed else "[FAIL]"
        print(f"  {mark} q{r.qid:<5} {r.db_id:<22} {r.difficulty:<11} "
              f"{r.elapsed_ms:>6}ms  {r.reason}")
    return results


def _by_diff(results: list[ItemResult]) -> dict[str, list[ItemResult]]:
    d: dict[str, list[ItemResult]] = defaultdict(list)
    for r in results:
        d[r.difficulty].append(r)
    return d


def _print_summary(results: list[ItemResult], title: str) -> None:
    by_diff = _by_diff(results)
    print(f"\n[{title}]  {'难度':<12}{'EX 通过 / 总数':>18}{'准确率':>12}")
    print("-" * 52)
    for diff in sorted(by_diff):
        g = by_diff[diff]
        p = sum(1 for r in g if r.passed)
        print(f"{'':<{len(title) + 4}}{diff:<12}{p:>8} / {len(g):<6}{p / len(g) * 100:>10.1f}%")
    tp = sum(1 for r in results if r.passed)
    avg = sum(r.elapsed_ms for r in results) // max(len(results), 1)
    print("-" * 52)
    print(f"{'':<{len(title) + 4}}{'总计 (EX)':<12}{tp:>8} / {len(results):<6}"
          f"{tp / len(results) * 100:>10.1f}%   ·  平均 {avg} ms/题")


def _print_ab(ddl: list[ItemResult], ret: list[ItemResult]) -> None:
    a, b = _by_diff(ddl), _by_diff(ret)
    print("\n=== A/B 对比:整库 DDL  vs  多路检索 ===")
    print(f"{'难度':<14}{'DDL EX':>12}{'检索 EX':>12}{'Δ':>10}")
    print("-" * 50)
    for diff in sorted(set(a) | set(b)):
        ga, gb = a.get(diff, []), b.get(diff, [])
        ra = sum(1 for r in ga if r.passed) / len(ga) * 100 if ga else 0.0
        rb = sum(1 for r in gb if r.passed) / len(gb) * 100 if gb else 0.0
        print(f"{diff:<14}{ra:>11.1f}%{rb:>11.1f}%{rb - ra:>+9.1f}%")
    ta = sum(1 for r in ddl if r.passed) / len(ddl) * 100
    tb = sum(1 for r in ret if r.passed) / len(ret) * 100
    print("-" * 50)
    print(f"{'总计 (EX)':<14}{ta:>11.1f}%{tb:>11.1f}%{tb - ta:>+9.1f}%")


def _summary_dict(results: list[ItemResult]) -> dict:
    bd = _by_diff(results)
    tp = sum(1 for r in results if r.passed)
    return {
        "total": len(results),
        "passed": tp,
        "ex": tp / len(results) * 100,
        "avg_ms": sum(r.elapsed_ms for r in results) // max(len(results), 1),
        "by_difficulty": {d: {"total": len(g), "passed": sum(1 for r in g if r.passed)}
                          for d, g in bd.items()},
        "results": [asdict(r) for r in results],
    }


# ───────────────────────── 主流程 ─────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="BIRD 基准 EX 评测")
    parser.add_argument("--bird-dir", required=True, help="BIRD dev 集目录(含 dev.json 和 dev_databases/)")
    parser.add_argument("-n", "--limit", type=int, default=80, help="抽样题数(默认 80)")
    parser.add_argument("--difficulty", default="", help="只跑某难度: simple/moderate/challenging")
    parser.add_argument("--db", default="", help="只跑指定库的题(如 formula_1),便于针对大库测检索")
    parser.add_argument("--seed", type=int, default=42, help="抽样随机种子(可复现)")
    parser.add_argument("--no-glossary", action="store_true", help="不注入列含义描述")
    parser.add_argument("--retrieval", choices=["off", "on", "ab"], default="off",
                        help="知识库检索: off=整库DDL(默认) / on=多路检索 / ab=两种各跑一遍对比EX")
    parser.add_argument("--verbose", action="store_true", help="打印失败题详情")
    parser.add_argument("--json", metavar="PATH", help="把结果写入 JSON 文件")
    parser.add_argument("--gen-sources", action="store_true",
                        help="只生成含全部 BIRD 库的数据源配置(供前端 uvicorn 用),不跑评测")
    parser.add_argument("--list-db", metavar="DB_ID",
                        help="打印某个库的题目(question/evidence/gold),方便复制到前端手动测试")
    args = parser.parse_args()

    bird_dir = Path(args.bird_dir)
    if not bird_dir.exists():
        print(f"BIRD 目录不存在: {bird_dir}", file=sys.stderr)
        return 1

    try:
        dev_json = _find_dev_json(bird_dir)
        databases_root = _databases_root(dev_json)
        items = load_bird_items(dev_json)
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        print(f"加载 BIRD 数据失败: {e}", file=sys.stderr)
        return 1

    # ── 前端辅助模式:打印某库题目,方便复制到页面手动测 ──
    if args.list_db:
        picked = [it for it in items if it.db_id == args.list_db]
        if not picked:
            print(f"库 {args.list_db} 没有题目。可用库: "
                  f"{', '.join(sorted({it.db_id for it in items}))}", file=sys.stderr)
            return 1
        print(f"# 库 {args.list_db} 共 {len(picked)} 题\n")
        for it in picked:
            print(f"## q{it.qid} [{it.difficulty}]")
            print(f"问题: {it.question}")
            if it.evidence:
                print(f"提示(evidence,要一起贴进前端): {it.evidence}")
            print(f"gold: {it.gold_sql}\n")
        return 0

    # ── 前端辅助模式:生成含全部 BIRD 库的数据源配置,供 uvicorn 用 ──
    if args.gen_sources:
        try:
            cfg = prepare_sources(items, databases_root,
                                  use_glossary=not args.no_glossary, include_default=True)
        except FileNotFoundError as e:
            print(f"生成数据源失败: {e}", file=sys.stderr)
            return 1
        print(f"已生成数据源配置(demo + {len({it.db_id for it in items})} 个 BIRD 库):\n  {cfg}\n")
        print("用它启动前端(PowerShell):")
        print(f'  $env:DATA_SOURCES_FILE = "{cfg}"')
        print('  uvicorn app.main:app --reload')
        print("\n然后打开页面,在数据源下拉里选某个 BIRD 库,粘贴该库的题目即可。")
        print(f'查看某库题目: python scripts/eval_bird.py --bird-dir "{args.bird_dir}" --list-db <库名>')
        return 0

    if args.difficulty:
        items = [it for it in items if it.difficulty == args.difficulty]
    if args.db:
        items = [it for it in items if it.db_id == args.db]
    if not items:
        print("过滤后没有题目。", file=sys.stderr)
        return 1

    rng = random.Random(args.seed)
    if args.limit and len(items) > args.limit:
        items = rng.sample(items, args.limit)

    # 生成 bird 专用数据源配置并切换 DATA_SOURCES_FILE(必须在首次 get_source 之前)
    try:
        cfg_path = prepare_sources(items, databases_root, use_glossary=not args.no_glossary)
    except FileNotFoundError as e:
        print(f"准备数据源失败: {e}", file=sys.stderr)
        return 1
    os.environ["DATA_SOURCES_FILE"] = str(cfg_path)

    # 延迟导入:确保 MAX_ROWS / DATA_SOURCES_FILE 已就位
    from app.core.chain import generate_sql
    from app.core.executor import SQLExecutionError, execute
    from app.core.retrieval import retrieve_context
    from app.core.schema import load_schema
    from app.core.validator import SQLValidationError, validate_and_fix

    deps = (generate_sql, load_schema, execute, validate_and_fix,
            SQLValidationError, SQLExecutionError, retrieve_context)

    glossary_note = "关" if args.no_glossary else "开"
    print(f"BIRD 评测 · {len(items)} 题 · {len({it.db_id for it in items})} 个库 · "
          f"列描述注入: {glossary_note} · 检索: {args.retrieval} · MAX_ROWS={os.environ['MAX_ROWS']}\n")

    if args.retrieval == "ab":
        # A/B:同一批题分别用整库 DDL 和多路检索各跑一遍(LLM 调用约 2 倍)
        print("【整库 DDL 模式】")
        ddl_results = _run_pass(items, False, deps)
        print("\n【多路检索模式】")
        ret_results = _run_pass(items, True, deps)
        _print_summary(ddl_results, "DDL")
        _print_summary(ret_results, "检索")
        _print_ab(ddl_results, ret_results)
        results = ret_results
        json_out = {"mode": "ab", "ddl": _summary_dict(ddl_results),
                    "retrieval": _summary_dict(ret_results)}
    else:
        use_ret = args.retrieval == "on"
        results = _run_pass(items, use_ret, deps)
        _print_summary(results, "检索" if use_ret else "DDL")
        json_out = {"mode": args.retrieval, **_summary_dict(results)}

    if args.verbose:
        failures = [r for r in results if not r.passed]
        if failures:
            print(f"\n--- 失败详情 ({len(failures)}) ---")
            for r in failures:
                print(f"\n  [FAIL] q{r.qid} ({r.db_id} / {r.difficulty} / {r.mode})")
                print(f"    原因: {r.reason}")
                if r.predicted_sql:
                    print(f"    predicted: {r.predicted_sql[:300]}")

    if args.json:
        Path(args.json).write_text(json.dumps(json_out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已写入 {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
