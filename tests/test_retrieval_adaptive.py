from __future__ import annotations

import networkx as nx

from app.core.retrieval import pipeline
from app.core.retrieval import graph as graph_module
from app.core.retrieval.base import Hit, SchemaAtom
from app.core.retrieval.graph import RelationGraph
from app.core.schema import SchemaInfo


class _FakeRetriever:
    name = "keyword"

    def __init__(self, hits: list[Hit]) -> None:
        self.hits = hits

    def query(self, _question: str, _top_k: int) -> list[Hit]:
        return self.hits


class _NoGlossary:
    def available(self) -> bool:
        return False


def _schema(tables: dict[str, list[str]]) -> SchemaInfo:
    ddl = "CREATE TABLE authorized (id INTEGER);\n" + ("-" * 2000)
    return SchemaInfo(ddl_text=ddl, pure_ddl=ddl, tables=tables)


def test_small_authorized_schema_bypasses_retrieval(monkeypatch):
    monkeypatch.setattr(pipeline.settings, "retrieval_enabled", True)
    monkeypatch.setattr(pipeline.settings, "retrieval_min_tables", 15)
    monkeypatch.setattr(pipeline.settings, "retrieval_min_columns", 120)
    monkeypatch.setattr(
        pipeline,
        "_get",
        lambda _source: (_ for _ in ()).throw(AssertionError("small role view must not build retrieval")),
    )

    result = pipeline.retrieve_context(
        "查询我的课程",
        "teaching",
        _schema({"course": ["id", "name"], "teacher": ["id", "name"]}),
    )

    assert result is None


def test_retrieval_filters_unauthorized_atoms_and_graph_bridges(monkeypatch):
    monkeypatch.setattr(pipeline.settings, "retrieval_enabled", True)
    monkeypatch.setattr(pipeline.settings, "retrieval_min_tables", 0)
    monkeypatch.setattr(pipeline.settings, "retrieval_min_columns", 0)
    monkeypatch.setattr(pipeline.settings, "retrieval_query_expansion", False)
    monkeypatch.setattr(pipeline.settings, "retrieval_backend", "local")
    monkeypatch.setattr(pipeline, "_conditional_glossary", lambda *_args: [])
    atoms = [
        SchemaAtom("teaching", "allowed_a"),
        SchemaAtom("teaching", "allowed_a", "name", "TEXT"),
        SchemaAtom("teaching", "allowed_b"),
        SchemaAtom("teaching", "allowed_b", "title", "TEXT"),
        SchemaAtom("teaching", "forbidden"),
        SchemaAtom("teaching", "forbidden", "secret", "TEXT"),
    ]
    hits = [
        Hit("forbidden.secret", 1.0, "keyword"),
        Hit("allowed_a.name", 0.9, "keyword"),
        Hit("allowed_b.title", 0.8, "keyword"),
    ]
    graph = RelationGraph("teaching")
    graph.g = nx.Graph([("allowed_a", "forbidden"), ("forbidden", "allowed_b")])
    graph.fks = [
        ("allowed_a", "id", "forbidden", "a_id"),
        ("forbidden", "b_id", "allowed_b", "id"),
    ]
    monkeypatch.setattr(
        pipeline,
        "_get",
        lambda _source: (atoms, [_FakeRetriever(hits)], graph, _NoGlossary()),
    )

    result = pipeline.retrieve_context(
        "查询姓名和标题",
        "teaching",
        _schema({"allowed_a": ["id", "name"], "allowed_b": ["id", "title"]}),
    )

    assert result is not None
    assert set(result.tables).issubset({"allowed_a", "allowed_b"})
    assert "forbidden" not in result.context_text
    assert "secret" not in result.context_text


def test_relation_graph_never_uses_unauthorized_bridge():
    graph = RelationGraph("teaching")
    graph.g = nx.Graph([("allowed_a", "forbidden"), ("forbidden", "allowed_b")])
    graph.fks = [
        ("allowed_a", "id", "forbidden", "a_id"),
        ("forbidden", "b_id", "allowed_b", "id"),
    ]

    ranked = graph.rank(
        {"allowed_a": 1.0},
        10,
        allowed_tables={"allowed_a", "allowed_b"},
    )
    connected, joins = graph.connect(
        ["allowed_a", "allowed_b"],
        allowed_tables={"allowed_a", "allowed_b"},
    )

    assert ranked == []
    assert connected == ["allowed_a", "allowed_b"]
    assert joins == []


def test_relation_graph_canonicalizes_case_and_skips_invalid_relations(monkeypatch):
    class _Inspector:
        _columns = {
            "Country": ["id", "name"],
            "League": ["id", "country_id", "name"],
            "Match": ["id", "league_id", "country_id"],
        }

        def get_table_names(self):
            return list(self._columns)

        def get_columns(self, table):
            return [{"name": name} for name in self._columns[table]]

        def get_foreign_keys(self, table):
            if table == "League":
                return [{
                    "constrained_columns": ["country_id"],
                    "referred_table": "country",
                    "referred_columns": ["id"],
                }]
            if table == "Match":
                return [
                    {
                        "constrained_columns": ["league_id"],
                        "referred_table": "League",
                        "referred_columns": ["id"],
                    },
                    {
                        "constrained_columns": ["country_id"],
                        "referred_table": "Country",
                        "referred_columns": [None],
                    },
                    {
                        "constrained_columns": ["country_id"],
                        "referred_table": "MissingTable",
                        "referred_columns": ["id"],
                    },
                ]
            return []

    monkeypatch.setattr(graph_module, "get_source", lambda _source: object())
    monkeypatch.setattr(graph_module, "get_engine", lambda _source: object())
    monkeypatch.setattr(graph_module, "inspect", lambda _engine: _Inspector())
    monkeypatch.setattr(
        graph_module,
        "manual_relations",
        lambda _source: [
            ("Match", "country_id", "Country", "missing_id"),
            ("missing", "id", "Country", "id"),
        ],
    )

    graph = RelationGraph("external")
    graph.build()

    assert set(graph.g.nodes) == {"Country", "League", "Match"}
    assert "country" not in graph.g
    assert graph.fks == [
        ("League", "country_id", "Country", "id"),
        ("Match", "league_id", "League", "id"),
    ]
    assert set(graph.g.edges) == {("Country", "League"), ("League", "Match")}
    assert all(None not in relation for relation in graph.fks)


def test_relation_graph_keeps_valid_manual_relation_without_duplicate(monkeypatch):
    class _Inspector:
        def get_table_names(self):
            return ["Parent", "Child"]

        def get_columns(self, table):
            return [{"name": "id"}] if table == "Parent" else [{"name": "id"}, {"name": "parent_id"}]

        def get_foreign_keys(self, table):
            if table != "Child":
                return []
            return [{
                "constrained_columns": ["parent_id"],
                "referred_table": "Parent",
                "referred_columns": ["id"],
            }]

    monkeypatch.setattr(graph_module, "get_source", lambda _source: object())
    monkeypatch.setattr(graph_module, "get_engine", lambda _source: object())
    monkeypatch.setattr(graph_module, "inspect", lambda _engine: _Inspector())
    monkeypatch.setattr(
        graph_module,
        "manual_relations",
        lambda _source: [("parent", "id", "CHILD", "parent_id")],
    )

    graph = RelationGraph("external")
    graph.build()

    assert set(graph.g.nodes) == {"Parent", "Child"}
    assert graph.fks == [("Child", "parent_id", "Parent", "id")]
    assert list(graph.g.edges) == [("Parent", "Child")]


def test_conditional_glossary_matches_terms_but_rejects_forbidden_references(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "_read_glossary",
        lambda _path: (
            "# Business Terms\n"
            "- 未交作业 = allowed_a.name IS NULL\n"
            "- 隐私预警 = forbidden.secret = 1\n"
        ),
    )
    monkeypatch.setattr(pipeline, "list_table_names", lambda _source: ["allowed_a", "forbidden"])

    matched = pipeline._conditional_glossary(
        "哪些同学未交作业，顺便看隐私预警",
        "teaching",
        {"allowed_a"},
        {"allowed_a"},
    )

    assert [entry.content for entry in matched] == ["未交作业 = allowed_a.name IS NULL"]


def test_compact_teaching_profile_keeps_unfinished_assignment_semantics():
    context = pipeline.profile_context(
        "teaching",
        ["enrollment", "assignment", "assignment_submission"],
        {
            "enrollment": {"student_id", "teaching_class_id"},
            "assignment": {"id", "teaching_class_id", "status", "due_time"},
            "assignment_submission": {"assignment_id", "student_id", "status"},
        },
    )

    assert "使用 LEFT JOIN 关联本人提交" in context
    assert "完全没有提交记录、missing、not_submitted、returned 都属于未完成" in context
    assert "late 是旧数据迟交状态，不能按未提交处理" in context
    assert "“未完成”不等于“未截止”" in context
    assert "用户没有明确要求“已截止/逾期/未截止”时，不得擅自按 due_time 增加时间过滤" in context
    assert "returned=已退回待重交" in context
