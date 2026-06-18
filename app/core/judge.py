"""Best-effort answer confidence judging.

The judge is informational only: query results are returned first, then a
background worker evaluates the answer and /api/judge polls the finished result.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass

from app.core.chain import make_llm
from app.core.config import PROMPTS_DIR, settings

logger = logging.getLogger("nl2sql.judge")

_SCHEMA_CHARS_CAP = 4000
_PENDING_CAP = 256


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
        _pending[jid] = {"done": False, "result": None}
        while len(_pending) > _PENDING_CAP:
            _pending.popitem(last=False)
    threading.Thread(target=_judge_worker, args=(jid, args), daemon=True, name=f"judge-{jid[:8]}").start()
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
            return "pending", None
        result = item.get("result")
        _pending.pop(jid, None)
        if result is None:
            return "failed", None
        return "done", result
