from pathlib import Path

import pytest
from llama_index.core.schema import NodeWithScore, TextNode

from app.core.config import Settings
from app.knowledge.service import NO_EVIDENCE_MESSAGE, KnowledgeSearchService


class FakeRetriever:
    def __init__(self, nodes: list[NodeWithScore]) -> None:
        self.nodes = nodes
        self.queries: list[str] = []

    async def aretrieve(self, query: str) -> list[NodeWithScore]:
        self.queries.append(query)
        return self.nodes


def settings(_tmp_path: Path) -> Settings:
    return Settings(knowledge_top_k=1)


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
