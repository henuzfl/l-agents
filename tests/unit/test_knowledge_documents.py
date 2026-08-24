from app.knowledge.documents import (
    PROJECT_MANUAL_SECTIONS,
    SOURCE_NAME,
    build_project_manual_documents,
    build_project_manual_nodes,
)


def test_project_manual_documents_have_source_and_section_metadata() -> None:
    documents = build_project_manual_documents()
    assert len(documents) == len(PROJECT_MANUAL_SECTIONS)
    assert {document.metadata["source"] for document in documents} == {SOURCE_NAME}
    assert all(document.metadata["section"] for document in documents)


def test_project_manual_is_split_with_metadata_preserved() -> None:
    nodes = build_project_manual_nodes(chunk_size=128, chunk_overlap=20)
    assert nodes
    assert all(node.metadata["source"] == SOURCE_NAME for node in nodes)
    assert all(node.metadata["section"] for node in nodes)
