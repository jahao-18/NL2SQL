"""LangChain 链:Qwen 生成 SQL + 失败回修。

generate_sql 走 ChatPromptTemplate 支持多轮对话;
repair_sql 保留单轮 PromptTemplate,因为回修只需要"上次 SQL + error",不需要历史上下文。
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
import time
from typing import Literal

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate

from app.core.config import PROMPTS_DIR, settings
from app.models.schemas import Turn

CLARIFY_PREFIX = "CLARIFY:"

# 方言提示:LLM 生成 SQL 时需要的方言专有写法概览。
# 故意保持简短,避免污染上下文;详细差异让模型从 schema 推断。
_DIALECT_NOTES: dict[str, str] = {
    "sqlite": (
        "- 时间字段是 ISO8601 文本时:用 substr(col,1,4) 取年、substr(col,1,7) 取年-月、"
        "或 col LIKE '2025%' 这类前缀匹配。也支持 strftime('%Y-%m', col)。\n"
        "- 字符串拼接用 ||。\n"
        "- LIMIT N 强制分页;ROW_NUMBER() OVER (PARTITION BY ...) 支持窗口函数。"
    ),
    "postgresql": (
        "- 时间字段若是 timestamp/date,用 EXTRACT(YEAR FROM col)、DATE_TRUNC('month', col)、"
        "或 to_char(col,'YYYY-MM');若是 text 列存的 ISO8601,用 substr(col,1,4)。\n"
        "- 字符串拼接用 || 或 CONCAT()。\n"
        "- LIMIT N 强制分页;严格类型——数字与字符串比较需 CAST。"
    ),
    "mysql": (
        "- 时间字段:用 YEAR(col)、DATE_FORMAT(col,'%Y-%m')、或 DATE(col)。\n"
        "- 字符串拼接用 CONCAT(a,b),不要用 ||(会被当成 OR)。\n"
        "- LIMIT N 强制分页。"
    ),
    "other": (
        "- 用标准 SQL 写法;LIMIT N 分页,窗口函数 ROW_NUMBER() OVER (...) 可用。"
    ),
}


def dialect_notes(dialect: str) -> str:
    return _DIALECT_NOTES.get(dialect, _DIALECT_NOTES["other"])


def _read(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


class ChatQwenMultiModal(BaseChatModel):
    """走 dashscope MultiModalConversation 接口的 Qwen 模型(如 qwen3.7-plus)。

    qwen3.x 等模型只在多模态 endpoint 上,文本 Generation 接口(ChatTongyi 用的)会 400。
    这里用纯文本消息把它当普通 chat 模型用,接口与 ChatTongyi 对齐,chain 无需改动。
    """
    model: str
    dashscope_api_key: str
    temperature: float = 0.0

    @property
    def _llm_type(self) -> str:
        return "qwen-multimodal"

    @staticmethod
    def _to_dashscope(messages: list[BaseMessage]) -> list[dict]:
        role_map = {"system": "system", "human": "user", "ai": "assistant"}
        return [
            {"role": role_map.get(m.type, "user"), "content": [{"text": m.content}]}
            for m in messages
        ]

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        import dashscope

        # qwen3.x 在国内主站的多模态 endpoint;显式指定避免 SDK 默认到国际站导致 url error
        dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"
        resp = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                resp = dashscope.MultiModalConversation.call(
                    api_key=self.dashscope_api_key,
                    model=self.model,
                    messages=self._to_dashscope(messages),
                    temperature=self.temperature,
                    timeout=settings.llm_timeout_seconds,
                )
                if resp.status_code == 200:
                    break
                last_error = RuntimeError(f"{resp.code} {resp.message}")
            except Exception as e:
                last_error = e
            if attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
        if resp is None:
            raise RuntimeError(f"Qwen multimodal call failed: {last_error}")
        if resp.status_code != 200:
            raise RuntimeError(f"Qwen 多模态调用失败: {resp.code} {resp.message}")
        content = resp.output.choices[0].message.content
        # content 可能是字符串,也可能是 [{'text': ...}] 形式
        if isinstance(content, list):
            text = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        else:
            text = str(content)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


def _is_multimodal_model(name: str) -> bool:
    """判断该模型是否走多模态 endpoint(qwen3.x / qwen-vl 系列)。"""
    n = name.lower()
    return n.startswith("qwen3") or "-vl" in n or "vl-" in n


def make_llm(model: str) -> BaseChatModel:
    """按模型名构建 chat 模型(qwen3.x/vl 走多模态 endpoint,其余走 ChatTongyi)。生成与裁判共用。"""
    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置,请在 .env 中填入")
    if _is_multimodal_model(model):
        return ChatQwenMultiModal(
            model=model,
            dashscope_api_key=settings.dashscope_api_key,
            temperature=0,
        )
    return ChatTongyi(
        model=model,
        dashscope_api_key=settings.dashscope_api_key,
        temperature=0,
        max_retries=2,
        model_kwargs={"timeout": settings.llm_timeout_seconds},
    )


@lru_cache(maxsize=1)
def _llm() -> BaseChatModel:
    return make_llm(settings.qwen_model)


@lru_cache(maxsize=1)
def _router_llm() -> BaseChatModel:
    """路由专用的快模型(qwen-turbo 级),与主生成 _llm() 分开,降低选库延迟。"""
    return make_llm(settings.router_model)


def _strip_sql(raw: str) -> str:
    """去掉模型可能加的 markdown 围栏或解释。"""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if "\n" in s:
            first, rest = s.split("\n", 1)
            if first.strip().lower() in {"sql", "sqlite"}:
                s = rest
    return s.strip().rstrip(";").strip()


def _parse_output(raw: str) -> tuple[Literal["sql", "clarify"], str]:
    """识别 LLM 输出是 SQL 还是 CLARIFY 澄清请求。

    CLARIFY 形如 'CLARIFY: <一句话问题>',大小写不敏感,允许半/全角冒号。
    其它一律按 SQL 处理(再走 _strip_sql)。
    """
    s = raw.strip()
    if s.startswith("```"):
        stripped = s.strip("`")
        if "\n" in stripped:
            first, rest = stripped.split("\n", 1)
            s = rest.strip() if first.strip().lower() in {"sql", "sqlite", "text"} else stripped.strip()
        else:
            s = stripped.strip()

    if s[:8].upper().startswith("CLARIFY"):
        rest = s[len("CLARIFY"):].lstrip()
        # 半角 ':' (U+003A) 或全角 '：' (U+FF1A) 都接受
        if rest and rest[0] in {":", "："}:
            question = rest[1:].strip().splitlines()[0].strip() if rest[1:].strip() else ""
            if question:
                return "clarify", question

    return "sql", _strip_sql(raw)


def _history_to_messages(history: list[Turn]) -> list[BaseMessage]:
    """把 Turn 列表展平成 [HumanMessage, AIMessage, HumanMessage, AIMessage, ...]。

    clarify 轮的 AIMessage 内容会带上 'CLARIFY: ' 前缀(若未带),
    以便下一轮 LLM 看到自己之前问过澄清,从而避免重复发问。
    """
    msgs: list[BaseMessage] = []
    for t in history:
        msgs.append(HumanMessage(content=t.question))
        content = t.sql
        if t.kind == "clarify" and not content.upper().startswith("CLARIFY"):
            content = f"{CLARIFY_PREFIX} {content}"
        msgs.append(AIMessage(content=content))
    return msgs


@lru_cache(maxsize=1)
def _chat_prompt() -> ChatPromptTemplate:
    system_text = _read("sql_prompt.txt")
    return ChatPromptTemplate.from_messages(
        [
            ("system", system_text),
            MessagesPlaceholder("history"),
            ("human", "{question}"),
        ]
    )


def generate_sql(
    schema: str,
    question: str,
    history: list[Turn] | None = None,
    dialect: str = "sqlite",
) -> tuple[Literal["sql", "clarify"], str]:
    """返回 (kind, content):kind=sql 时 content 是 SQL,kind=clarify 时 content 是要问用户的问题。"""
    chain = _chat_prompt() | _llm() | StrOutputParser()
    raw = chain.invoke(
        {
            "schema": schema,
            "question": question,
            "history": _history_to_messages(history or []),
            "current_date": date.today().isoformat(),
            "dialect": dialect,
            "dialect_notes": dialect_notes(dialect),
        }
    )
    return _parse_output(raw)


@lru_cache(maxsize=1)
def _repair_prompt() -> PromptTemplate:
    return PromptTemplate.from_template(_read("sql_repair_prompt.txt"))


def repair_sql(
    schema: str,
    question: str,
    previous_sql: str,
    error: str,
    dialect: str = "sqlite",
) -> str:
    chain = _repair_prompt() | _llm() | StrOutputParser()
    raw = chain.invoke(
        {
            "schema": schema,
            "question": question,
            "previous_sql": previous_sql,
            "error": error,
            "current_date": date.today().isoformat(),
            "dialect": dialect,
        }
    )
    return _strip_sql(raw)
