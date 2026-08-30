from pathlib import Path

import pytest
from llama_index.core.schema import NodeWithScore, TextNode

from app.core.config import Settings
from app.knowledge.retrieval.events import (
    bind_retrieval_evidence_sink,
    reset_retrieval_evidence_sink,
)
from app.knowledge.service import NO_EVIDENCE_MESSAGE, KnowledgeSearchService


class FakeRetriever:
    def __init__(self, nodes: list[NodeWithScore]) -> None:
        self.nodes = nodes
        self.queries: list[str] = []

    async def aretrieve(self, query: str) -> list[NodeWithScore]:
        self.queries.append(query)
        return self.nodes


def settings(_tmp_path: Path, *, top_k: int = 1) -> Settings:
    return Settings(knowledge_top_k=top_k)


@pytest.mark.asyncio
async def test_search_formats_ranked_evidence_with_citation(tmp_path: Path) -> None:
    nodes = [
        NodeWithScore(
            node=TextNode(
                text="只有 Manager 使用 Session。",
                metadata={"source": "项目使用手册", "section": "会话记忆"},
            ),
            score=0.92345,
        ),
        NodeWithScore(
            node=TextNode(
                text="第二条不会超过 top-k。",
                metadata={"source": "项目使用手册", "section": "其他"},
            ),
            score=0.8,
        ),
    ]
    retriever = FakeRetriever(nodes)
    service = KnowledgeSearchService(settings(tmp_path), retriever=retriever)
    result = await service.search(" Session 如何工作？ ")
    assert retriever.queries == ["Session 如何工作？"]
    assert "[项目使用手册 > 会话记忆]" in result
    assert "相关度: 0.9234" in result
    assert "第二条" not in result


@pytest.mark.asyncio
async def test_search_returns_explicit_message_when_no_evidence(tmp_path: Path) -> None:
    service = KnowledgeSearchService(settings(tmp_path), retriever=FakeRetriever([]))
    assert await service.search("未知问题") == NO_EVIDENCE_MESSAGE
    assert await service.search(" ") == NO_EVIDENCE_MESSAGE


@pytest.mark.asyncio
async def test_search_reorders_selected_chunks_and_publishes_image_asset(tmp_path: Path) -> None:
    task_id = "task-ordered-001"
    object_name = f"2026/08/30/{task_id}/multimodal.pdf"
    nodes = [
        NodeWithScore(
            node=TextNode(
                id_="image-node",
                text="系统处理流程图",
                metadata={
                    "source": "multimodal.pdf",
                    "section": "上传文档",
                    "page_number": 2,
                    "element_index": 3,
                    "element_part": 0,
                    "element_type": "image",
                    "minio_object": object_name,
                    "asset_object": "assets/flow.png",
                },
            ),
            score=0.98,
        ),
        NodeWithScore(
            node=TextNode(
                id_="text-node",
                text="第一步：加载原始文档。",
                metadata={
                    "source": "multimodal.pdf",
                    "section": "上传文档",
                    "page_number": 1,
                    "element_index": 1,
                    "element_part": 0,
                    "element_type": "text",
                    "minio_object": object_name,
                },
            ),
            score=0.91,
        ),
        NodeWithScore(
            node=TextNode(
                id_="code-node",
                text="```python\nchunk(document)\n```",
                metadata={
                    "source": "multimodal.pdf",
                    "section": "上传文档",
                    "page_number": 2,
                    "element_index": 2,
                    "element_part": 0,
                    "element_type": "code",
                    "minio_object": object_name,
                },
            ),
            score=0.94,
        ),
    ]
    received: list[dict[str, object]] = []

    async def collect(items: list[dict[str, object]]) -> None:
        received.extend(items)

    token = bind_retrieval_evidence_sink(collect)
    try:
        result = await KnowledgeSearchService(
            settings(tmp_path, top_k=3), retriever=FakeRetriever(nodes)
        ).search("加载、切分和图片")
    finally:
        reset_retrieval_evidence_sink(token)

    assert result.index("第一步") < result.index("chunk(document)") < result.index("系统处理流程图")
    assert [item["node_id"] for item in received] == ["text-node", "code-node", "image-node"]
    assert received[-1]["asset_url"] == (
        f"/api/v1/knowledge/documents/{task_id}/chunks/image-node/asset"
    )
