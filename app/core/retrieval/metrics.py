"""派生指标(计算口径)提取与匹配 —— 让"操作数感知召回"成为可能。

业务方在 glossary 里用**纯自然语言**定义派生指标,如:
    - 客单价 = 总消费金额 / 订单数量
    - 传球能力 = 短传 + 长传
字段匹配交给 LLM(它本来就擅长 NL→列)。但在走 schema linking 的大库上有个坑:
用户只说"客单价",这个词向量上匹配不到 amount/quantity 列,于是公式被召回了、源列却没召回进
精简上下文 —— LLM 想接也接不到。

本模块解决它:问题命中某个指标名时,
  (a) 把公式里的**操作数概念**(总消费金额、订单数量…)拼进检索 query,
      经查询扩展补英文别名后,对应的列就能被各路召回进上下文;
  (b) 把命中的**公式定义**强制注入上下文,保证 LLM 一定拿到口径(不依赖 glossary 向量恰好召回它,
      local 后端没有 glossary 路也照样生效)。

提取是纯文本规则,零模型调用;匹配是子串。都很轻。
"""
from __future__ import annotations

import re

# 形如 "- 客单价 = 总消费金额 / 订单数量"。要求右侧含算术运算符,以排除普通的 "A = B" 文字说明。
_METRIC_RE = re.compile(r"^[-*•]\s*(.+?)\s*=\s*(.+)$")
_OP_RE = re.compile(r"[/*+()]|\s-\s")  # / * + ( ) 或两侧带空格的减号


def extract_metrics(glossary_text: str) -> list[tuple[str, str]]:
    """从词表文本解析派生指标,返回 [(指标名, 公式)]。公式右侧须含算术运算符才算指标。"""
    out: list[tuple[str, str]] = []
    if not glossary_text:
        return out
    for raw in glossary_text.splitlines():
        s = raw.strip()
        m = _METRIC_RE.match(s)
        if not m:
            continue
        name, formula = m.group(1).strip(), m.group(2).strip()
        if not name or len(name) > 40 or not formula:
            continue
        if not _OP_RE.search(formula):
            continue
        out.append((name, formula))
    return out


def match_metrics(question: str, metrics: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """问题里出现了哪些已定义的指标名(子串匹配),返回命中的 [(名, 公式)]。"""
    if not question:
        return []
    return [(n, f) for (n, f) in metrics if n in question]
