"""检索编排:多路召回 -> RRF 融合 -> 选相关表 -> 拼精简 schema 上下文。

retrieve_context 是对外唯一入口。任何一步异常或库太小都返回 None,调用方据此回退整库 DDL。
第二期把 KeywordRetriever / GraphRetriever 加进 _build_retrievers 即可,融合与拼装无需改动。
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import threading
from collections import defaultdict

from app.core.config import settings
from app.core.data_sources import get_source
from app.core.schema import list_table_names, count_columns, _read_glossary
from app.core.retrieval.atoms import extract_atoms
from app.core.retrieval.base import Hit, RetrievedContext, Retriever, SchemaAtom
from app.core.retrieval.glossary_vector import GlossaryEntry, GlossaryRetriever, parse_glossary
from app.core.retrieval.graph import RelationGraph
from app.core.retrieval.keyword import KeywordRetriever
from app.core.retrieval.metrics import extract_metrics, match_metrics
from app.core.retrieval.query_expand import expand_query
from app.core.retrieval.vector import VectorRetriever
from app.core.schema_profile import profile_context

logger = logging.getLogger("nl2sql.retrieval")

_RRF_K = 60  # 倒数排名融合常数

# 每个数据源的缓存:原子 + 已建好的检索器 + 关系图 + 业务术语词表检索器(懒构建)
_cache: dict[str, tuple[list[SchemaAtom], list[Retriever], RelationGraph, GlossaryRetriever]] = {}
_cache_lock = threading.Lock()


def _candidate_retrievers(source: str) -> list[Retriever]:
    """按配置选检索后端。server = Milvus + ES;local = 进程内 numpy + rank_bm25。

    两套实现同接口(向量路 name='vector',关键字路 name='keyword'),所以融合/拼装无感。
    Milvus/ES 客户端在此惰性导入:local 模式下不依赖、也不会因未安装而报错。
    """
    if settings.retrieval_backend == "server":
        from app.core.retrieval.es_keyword import ESRetriever
        from app.core.retrieval.milvus_vector import MilvusRetriever
        return [MilvusRetriever(source), ESRetriever(source)]
    return [VectorRetriever(source), KeywordRetriever(source)]


def _build_retrievers(source: str, atoms: list[SchemaAtom]) -> list[Retriever]:
    """构建该数据源所有"按问题召回原子"的检索器,只保留就绪的。

    向量路(语义) + 关键字路(BM25 精确词)。关系图谱不在此列——它是关系层,单独处理。
    """
    candidates: list[Retriever] = _candidate_retrievers(source)
    ready: list[Retriever] = []
    for r in candidates:
        try:
            r.build(atoms)
            if r.available():
                ready.append(r)
            else:
                logger.info("检索器未就绪,跳过 | %s/%s", source, r.name)
        except Exception:
            logger.exception("检索器构建失败,跳过 | %s/%s", source, r.name)
    return ready


def _build_graph(source: str) -> RelationGraph:
    g = RelationGraph(source)
    try:
        g.build()
    except Exception:
        logger.exception("关系图构建失败 | source=%s", source)
    return g


def _build_glossary(source: str) -> GlossaryRetriever:
    """第 4 路:把 glossary 拆条目存进 PG/pgvector。仅 server 模式启用(需 PG);glossary 缺失则不就绪。"""
    g = GlossaryRetriever(source)
    if settings.retrieval_backend != "server":
        return g
    try:
        text = _read_glossary(get_source(source).glossary_path)
        if not text:
            return g
        entries = parse_glossary(text, list(list_table_names(source)))
        g.build(entries)
    except Exception:
        logger.exception("术语索引构建失败 | source=%s", source)
    return g


def _get(source: str) -> tuple[list[SchemaAtom], list[Retriever], RelationGraph, GlossaryRetriever]:
    if source not in _cache:
        with _cache_lock:
            if source in _cache:
                return _cache[source]
            atoms = extract_atoms(source)
            _cache[source] = (atoms, _build_retrievers(source, atoms),
                              _build_graph(source), _build_glossary(source))
    return _cache[source]


def _route_weights() -> dict[str, float]:
    """各检索路在 RRF 里的权重(可配)。未列出的路默认 1.0。"""
    return {
        "vector": settings.rrf_weight_vector,
        "keyword": settings.rrf_weight_keyword,
        "glossary": settings.rrf_weight_glossary,
        "graph": settings.rrf_weight_graph,
    }


def _rrf(hit_lists: list[list[Hit]], weights: dict[str, float] | None = None) -> dict[str, float]:
    """倒数排名融合:atom_id -> 累计分。多路命中靠前的原子得分更高。
    weights 给每路一个系数(默认 1.0),让"更可信的路"对融合排名贡献更大。"""
    weights = weights or {}
    scores: dict[str, float] = defaultdict(float)
    for hits in hit_lists:
        for rank, h in enumerate(hits):
            w = weights.get(h.retriever, 1.0)
            scores[h.atom_id] += w / (_RRF_K + rank)
    return scores


def _table_scores(atoms: list[SchemaAtom], scores: dict[str, float]) -> dict[str, float]:
    """把(列级/表级)命中分聚合到表上,返回 表 -> 聚合分。

    不再简单求和(那样宽表靠列多就赢)。改为:同一张表的命中分降序排列,最强命中作主导项,
    其余按 table_score_decay 几何衰减加成 —— 一张表的相关度主要由它最匹配的那列决定,
    多个相关列仍加分但边际递减,从而削弱"宽表偏置"。decay=1.0 时退化回纯求和。
    """
    id_to_table = {a.id: a.table for a in atoms}
    per_table: dict[str, list[float]] = defaultdict(list)
    for atom_id, sc in scores.items():
        tbl = id_to_table.get(atom_id)
        if tbl:
            per_table[tbl].append(sc)

    decay = settings.table_score_decay
    table_score: dict[str, float] = {}
    for tbl, scs in per_table.items():
        scs.sort(reverse=True)
        agg = scs[0]
        for i, s in enumerate(scs[1:], start=1):
            agg += s * (decay ** i)
        table_score[tbl] = agg
    return table_score


def _select_tables(atoms: list[SchemaAtom], scores: dict[str, float], top_n: int) -> list[str]:
    """聚合到表后选累计分最高的若干张表。"""
    table_score = _table_scores(atoms, scores)
    return sorted(table_score, key=lambda t: table_score[t], reverse=True)[:top_n]


def _fk_columns(graph: RelationGraph) -> set[tuple[str, str]]:
    """图里所有外键涉及的 (表, 列),裁剪时这些列必须保留以维持 JOIN 可写。"""
    cols: set[tuple[str, str]] = set()
    for (t1, c1, t2, c2) in graph.fks:
        cols.add((t1, c1))
        cols.add((t2, c2))
    return cols


def _select_columns(
    cols: list[SchemaAtom], matched_ids: set[str], fk_cols: set[tuple[str, str]], cap: int
) -> tuple[list[SchemaAtom], int]:
    """宽表列裁剪:保留 命中列 + 主键 + 外键列;不足 cap 再按原序补满。返回(保留原子, 省略列数)。

    窄表(列数 <= cap)整表返回、不裁。优先列(命中/主键/外键)即便数量超过 cap 也全保留——
    宁可略超上限,也不漏掉对回答和 JOIN 关键的列。输出保持原始 schema 列序。
    """
    if len(cols) <= cap:
        return cols, 0
    keep_ids: set[str] = set()
    for a in cols:
        if a.is_pk or a.id in matched_ids or (a.table, a.column) in fk_cols:
            keep_ids.add(a.id)
    if len(keep_ids) < cap:
        for a in cols:                       # 原序补充非优先列,补到 cap 为止
            if a.id not in keep_ids:
                keep_ids.add(a.id)
                if len(keep_ids) >= cap:
                    break
    kept = [a for a in cols if a.id in keep_ids]   # 保持原 schema 列序
    return kept, len(cols) - len(kept)


def _render(
    tables: list[str],
    atoms: list[SchemaAtom],
    join_lines: list[str],
    matched_ids: set[str] | None = None,
    fk_cols: set[tuple[str, str]] | None = None,
    col_cap: int = 25,
) -> str:
    """把选中的表渲染成精简上下文:每张表列出列 + 类型/主键/描述/取值;末尾附 JOIN 路径。

    宽表(列数 > col_cap)按 _select_columns 裁剪,只渲染相关列 + 主外键,其余折叠成一行提示,
    避免一张上百列的大表把上下文淹没;窄表整表照常渲染。
    """
    matched_ids = matched_ids or set()
    fk_cols = fk_cols or set()
    by_table: dict[str, list[SchemaAtom]] = defaultdict(list)
    for a in atoms:
        if a.column:  # 只渲染列级原子
            by_table[a.table].append(a)

    blocks: list[str] = []
    for tbl in tables:
        cols = by_table.get(tbl, [])
        kept, omitted = _select_columns(cols, matched_ids, fk_cols, col_cap)
        lines = [f"表 {tbl}:"]
        for a in kept:
            seg = f"  - {a.column} {a.col_type}".rstrip()
            if a.is_pk:
                seg += " [主键]"
            tail = []
            if a.natural_name and a.natural_name.lower() != a.column.lower():
                tail.append(a.natural_name)
            if a.description:
                tail.append(a.description)
            if a.value_hints:
                tail.append(f"取值: {a.value_hints}")
            if tail:
                seg += "  -- " + " | ".join(tail)
            lines.append(seg)
        if omitted:
            lines.append(f"  - …(此表另有 {omitted} 个与本问题关联较弱的字段未列出,如确需可追问)")
        blocks.append("\n".join(lines))

    header = "【与问题相关的表与字段(已按相关度筛选,如缺字段请基于表名合理推断)】"
    text = header + "\n\n" + "\n\n".join(blocks)
    if join_lines:
        text += ("\n\n【可用的表关联(外键,写 JOIN 时优先用这些条件)】\n"
                 + "\n".join(f"  - {ln}" for ln in join_lines))
    return text


def retrieve_context(question: str, source: str, ddl_text: str) -> RetrievedContext | None:
    """针对问题召回精简 schema 上下文。返回 None 表示应回退整库 DDL(关闭/库太小/失败/召回为空)。"""
    if not settings.retrieval_enabled:
        return None
    if len(ddl_text) < settings.retrieval_min_ddl_chars:
        return None  # 小库直接全量喂,无需 schema linking

    # 触发条件按"schema 体量":表多(需选表)**或**总列数多(需裁列,哪怕表很少)。
    # 旧逻辑只看表数,把 european_football_2(7 表但 Match 有 115 列)这类宽表库挡在外面;
    # 现在列多也触发,配合 _render 的列级裁剪,正是这类库最需要的。两者都小 = 小库,整库 DDL 足矣。
    try:
        n_tables = len(list_table_names(source))
        n_columns = count_columns(source)
    except Exception:
        return None
    if n_tables <= settings.retrieval_top_tables and n_columns <= settings.retrieval_min_columns:
        return None

    try:
        atoms, retrievers, graph, glossary = _get(source)
    except Exception:
        logger.exception("schema 原子/检索器准备失败,回退整库 DDL | source=%s", source)
        return None
    if not retrievers:
        return None

    # 派生指标(计算口径)感知:问题命中已定义的指标时,把公式里的操作数概念并入检索 query,
    # 让操作数对应的列也被召回进上下文(否则只召回到公式、却缺源列,LLM 接不上)。
    hit_metrics = match_metrics(question, extract_metrics(_read_glossary(get_source(source).glossary_path)))
    metric_operands = " ".join(f for (_, f) in hit_metrics)

    # 查询侧术语扩展:补英文列名别名,提升中文问题对英文列名的跨语言召回(best-effort)。
    # 把命中指标的公式操作数一并喂给扩展,使"总消费金额/订单数量"这类概念也拿到英文别名。
    eq = expand_query((question + " " + metric_operands).strip() if metric_operands else question)

    # ── 三路召回并行执行 ──
    # vector / keyword / glossary 都是 I/O 密集(嵌入 HTTP + Milvus/ES/PG 网络往返),
    # 用线程池并发,墙钟≈最慢一路而非三路之和。graph 是后置关系层(依赖融合选出的表),
    # 无法与召回并行,留到融合之后。每路结果按提交顺序回收,RRF 与 used 仍确定性。
    specs: list[tuple[str, callable]] = [
        (r.name, lambda r=r: r.query(eq, settings.retrieval_top_k)) for r in retrievers
    ]
    if glossary.available():
        specs.append(("glossary", lambda: glossary.query(eq, settings.glossary_top_k)))

    results: list[tuple[str, object]] = []
    with cf.ThreadPoolExecutor(max_workers=len(specs)) as ex:
        futures = [ex.submit(fn) for _, fn in specs]
        for (name, _), fut in zip(specs, futures):
            try:
                results.append((name, fut.result()))
            except Exception:
                logger.exception("检索器查询失败,跳过 | %s/%s", source, name)
                results.append((name, None))

    hit_lists: list[list[Hit]] = []
    used: list[str] = []
    glossary_entries: list[GlossaryEntry] = []
    for name, res in results:
        if not res:
            continue
        if name == "glossary":
            # 术语路:命中条目引用的表 -> 表级 Hit 并入 RRF(影响选表);正文稍后注入「业务说明」段。
            glossary_entries = res
            g_hits = [Hit(tbl, e.score, "glossary")
                      for e in glossary_entries for tbl in e.tables]
            if g_hits:
                hit_lists.append(g_hits)
            used.append("glossary")
        else:
            hit_lists.append(res)
            used.append(name)

    if not hit_lists:
        return None

    # 首次融合:前三路(内容路)得到表分,作为图检索的种子。
    weights = _route_weights()
    scores = _rrf(hit_lists, weights)
    tscore = _table_scores(atoms, scores)
    if not tscore:
        return None

    # 第 4 路:图结构检索(二阶段)。以首次融合 top 表为种子做 Personalized PageRank,
    # 沿 FK 扩散,把结构上相关的表(桥接/中心表)作为 graph 路 Hit 并入,再融合一次。
    # graph 需要种子,故跑在前三路并行召回之后,不与之并行。
    if graph.available():
        seeds = dict(sorted(tscore.items(), key=lambda kv: kv[1], reverse=True)[:settings.retrieval_top_tables])
        graph_ranked = graph.rank(seeds, settings.retrieval_top_k)
        if graph_ranked:
            hit_lists.append([Hit(t, s, "graph") for t, s in graph_ranked])
            used.append("graph")
            scores = _rrf(hit_lists, weights)      # 纳入图结构信号后重新融合(同一套权重)
            tscore = _table_scores(atoms, scores)

    tables = sorted(tscore, key=lambda t: tscore[t], reverse=True)[:settings.retrieval_top_tables]
    if not tables:
        return None

    # JOIN 渲染(保留):FK 最短路径补桥接表 + 输出 JOIN 条件行喂 LLM。这是上下文构建,非检索。
    join_lines: list[str] = []
    if graph.available():
        tables, join_lines = graph.connect(tables, max_extra=settings.retrieval_max_bridge_tables)

    # 业务术语正文注入:无论条目的表是否进了 top-N,召回到的业务规则都附上(可能跨表也相关)。
    matched_ids = {aid for aid, sc in scores.items() if sc > 0}        # 命中的列(裁剪时保留)
    fk_cols = _fk_columns(graph) if graph.available() else set()       # 外键列(裁剪时保留,保 JOIN)
    context_text = _render(tables, atoms, join_lines, matched_ids, fk_cols, settings.retrieval_col_cap)
    profile_block = profile_context(source, tables)
    if profile_block:
        context_text += "\n\n" + profile_block
    if glossary_entries:
        context_text += ("\n\n【相关业务说明 / 术语(按问题召回,写 SQL 时务必遵守)】\n"
                         + "\n".join(f"  - {e.content}" for e in glossary_entries))

    # 派生指标:强制注入命中的公式定义(不依赖 glossary 向量恰好召回它;local 后端无 glossary 路也生效)。
    # 操作数对应的列已经通过上面的 metric_operands 并入 query 被召回进上下文,这里给出口径让 LLM 计算。
    if hit_metrics:
        context_text += ("\n\n【相关派生指标 / 计算口径(这些不是现成的列,请按公式用上面的字段计算;"
                         "公式中的概念请自行匹配到最合适的字段/聚合,匹配不到则按澄清规则说明缺哪个口径)】\n"
                         + "\n".join(f"  - {n} = {f}" for (n, f) in hit_metrics))

    logger.info("schema 检索 | source=%s | retrievers=%s | tables=%s | joins=%d | glossary=%d | metrics=%d",
                source, used, tables, len(join_lines), len(glossary_entries), len(hit_metrics))
    return RetrievedContext(
        context_text=context_text,
        tables=tables,
        retrievers_used=used,
    )


def warm(source: str) -> bool:
    """预热一个数据源:提前 _get() 建好原子/检索器/图/术语索引(含嵌入全部原子)并入缓存。

    与 retrieve_context 用同样的"跳过条件"——检索关闭、或表数 <= top_tables(小库走整库 DDL,
    根本不检索)——直接跳过,避免为不会用检索的库白嵌入。返回是否真的做了预热。
    """
    if not settings.retrieval_enabled:
        return False
    try:
        n_tables = len(list_table_names(source))
        n_columns = count_columns(source)
    except Exception:
        return False
    if n_tables <= settings.retrieval_top_tables and n_columns <= settings.retrieval_min_columns:
        return False
    try:
        _get(source)
        return True
    except Exception:
        logger.exception("检索器预热失败 | source=%s", source)
        return False


def warm_all() -> None:
    """顺序预热所有数据源(顺序而非并发,避免一次性把全部库的嵌入请求打满 API)。"""
    from app.core.data_sources import load_sources

    for name in load_sources():
        if warm(name):
            logger.info("检索器预热完成 | source=%s", name)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
