"""Best-effort answer confidence judging.

The judge is informational only: query results are returned first, then a
background worker evaluates the answer and /api/judge polls the finished result.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.core.chain import make_llm
from app.core.config import PROMPTS_DIR, settings

logger = logging.getLogger("nl2sql.judge")

_SCHEMA_CHARS_CAP = 4000
_PENDING_CAP = 256
_executor = ThreadPoolExecutor(max_workers=max(1, settings.judge_workers), thread_name_prefix="judge")


@dataclass
class JudgeResult:
    final: int
    retrieval: int
    correctness: int
    reason: str


def _sys_prompt() -> str:
    return (PROMPTS_DIR / "judge_prompt.txt").read_text(encoding="utf-8")


def _result_preview(columns: list[str], rows: list[list], row_count: int) -> str:
    sample = rows[: settings.judge_sample_rows]
    lines = ["Columns: " + ", ".join(map(str, columns)), f"Total rows: {row_count}", "Sample rows:"]
    for row in sample:
        lines.append("  " + " | ".join("NULL" if cell is None else str(cell) for cell in row))
    if row_count > len(sample):
        lines.append(f"  ...({row_count - len(sample)} more rows)")
    return "\n".join(lines)


def _parse(text: str) -> tuple[int, int, str] | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        retrieval = max(0, min(100, int(obj["retrieval_score"])))
        correctness = max(0, min(100, int(obj["correctness_score"])))
        reason = str(obj.get("reason", "")).strip()
        return retrieval, correctness, reason
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def judge(
    question: str,
    schema_text: str,
    sql: str,
    columns: list[str],
    rows: list[list],
    row_count: int,
    dialect: str,
    retrieval_used: bool,
) -> JudgeResult | None:
    if not settings.judge_enabled:
        return None
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        ctx_note = "retrieved compact schema" if retrieval_used else "full database schema"
        schema_snippet = schema_text[:_SCHEMA_CHARS_CAP]
        if len(schema_text) > _SCHEMA_CHARS_CAP:
            schema_snippet += "\n...(schema truncated)"

        user = (
            f"[User question]\n{question}\n\n"
            f"[Schema context: {ctx_note}]\n{schema_snippet}\n\n"
            f"[Dialect]\n{dialect}\n\n"
            f"[Generated SQL]\n{sql}\n\n"
            f"[Result preview]\n{_result_preview(columns, rows, row_count)}\n\n"
            "Return exactly one JSON object as instructed."
        )
        llm = make_llm(settings.judge_model)
        resp = llm.invoke([SystemMessage(content=_sys_prompt()), HumanMessage(content=user)])
        text = resp.content if hasattr(resp, "content") else str(resp)
        parsed = _parse(text if isinstance(text, str) else str(text))
        if not parsed:
            logger.warning("judge output parse failed: %s", str(text)[:200])
            return None

        retrieval, correctness, reason = parsed
        weight = settings.judge_weight_correctness
        final = round(weight * correctness + (1 - weight) * retrieval)
        logger.info(
            "judge ok | final=%d retrieval=%d correctness=%d | %s",
            final, retrieval, correctness, reason,
        )
        return JudgeResult(final=final, retrieval=retrieval, correctness=correctness, reason=reason)
    except Exception:
        logger.exception("judge failed")
        return None


_pending: "OrderedDict[str, dict]" = OrderedDict()
_pending_lock = threading.Lock()


def _judge_worker(jid: str, args: dict) -> None:
    result = judge(**args)
    with _pending_lock:
        item = _pending.get(jid)
        if item is not None:
            item["result"] = result
            item["done"] = True


def _fallback_judge(args: dict) -> JudgeResult:
    columns = args.get("columns") or []
    rows = args.get("rows") or []
    row_count = int(args.get("row_count") or 0)
    retrieval_used = bool(args.get("retrieval_used"))
    sql = str(args.get("sql") or "")

    retrieval = 86 if retrieval_used else 92
    correctness = 82
    if not sql.strip():
        correctness = 35
    elif row_count == 0:
        correctness = 70
    elif columns == ["error"]:
        correctness = 40
    elif rows:
        correctness = 86

    weight = settings.judge_weight_correctness
    final = round(weight * correctness + (1 - weight) * retrieval)
    return JudgeResult(
        final=max(0, min(100, final)),
        retrieval=max(0, min(100, retrieval)),
        correctness=max(0, min(100, correctness)),
        reason="裁判模型响应较慢，系统先根据查询是否成功、结果是否返回和数据覆盖情况给出临时估算。",
    )


def stash(
    question: str,
    schema_text: str,
    sql: str,
    columns: list[str],
    rows: list[list],
    row_count: int,
    dialect: str,
    retrieval_used: bool,
) -> str | None:
    if not settings.judge_enabled:
        return None
    jid = uuid.uuid4().hex
    args = dict(
        question=question,
        schema_text=schema_text,
        sql=sql,
        columns=columns,
        rows=rows,
        row_count=row_count,
        dialect=dialect,
        retrieval_used=retrieval_used,
    )
    with _pending_lock:
        _pending[jid] = {"done": False, "result": None, "created_at": time.monotonic(), "args": args}
        while len(_pending) > _PENDING_CAP:
            _pending.popitem(last=False)
    _executor.submit(_judge_worker, jid, args)
    return jid


def run_stashed(jid: str) -> JudgeResult | None:
    with _pending_lock:
        item = _pending.get(jid)
        if not item or not item.get("done"):
            return None
        _pending.pop(jid, None)
        return item.get("result")


def stashed_status(jid: str) -> tuple[str, JudgeResult | None]:
    with _pending_lock:
        item = _pending.get(jid)
        if item is None:
            return "missing", None
        if not item.get("done"):
            elapsed = time.monotonic() - float(item.get("created_at") or time.monotonic())
            if elapsed >= max(3, int(settings.judge_fallback_seconds or 12)):
                result = _fallback_judge(item.get("args") or {})
                _pending.pop(jid, None)
                logger.warning("judge fallback used | jid=%s elapsed=%.1fs final=%d", jid[:8], elapsed, result.final)
                return "done", result
            return "pending", None
        result = item.get("result")
        _pending.pop(jid, None)
        if result is None:
            return "failed", None
        return "done", result
