from app.core.retrieval import retrieve_context
from app.core.retrieval.atoms import extract_atoms
from app.core.schema import load_schema


def test_retrieval_keeps_major_name_enum_values():
    atoms = extract_atoms("teaching")
    major_name = next(
        atom for atom in atoms
        if atom.table == "major" and atom.column == "name"
    )
    assert "软件工程" in major_name.value_hints

    schema = load_schema("teaching")
    context = retrieve_context(
        "软件工程专业各年级学生人数是多少？",
        "teaching",
        schema.ddl_text,
    )
    assert context is not None
    assert "软件工程" in context.context_text
