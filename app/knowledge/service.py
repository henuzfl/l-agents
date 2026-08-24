from collections.abc import Callable
from typing import Protocol

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeWithScore

from app.core.config import Settings
from app.core.exceptions import KnowledgeConfigurationError, KnowledgeRetrievalError

from .store import LlamaIndexKnowledgeStore

NO_EVIDENCE_MESSAGE = "知识库中没有足够证据，无法回答该问题。"


class RetrieverLike(Protocol):
    async def aretrieve(self, query: str) -> list[NodeWithScore]: ...


class KnowledgeSearchService:
    def __init__(
        self,
        settings: Settings,
        retriever: RetrieverLike | None = None,
        retriever_factory: Callable[[], BaseRetriever] | None = None,
    ) -> None:
        self._settings = settings
        self._retriever = retriever
        self._retriever_factory = retriever_factory or self._create_retriever

    def _create_retriever(self) -> BaseRetriever:
        return LlamaIndexKnowledgeStore(self._settings).create_retriever()

    def _get_retriever(self) -> RetrieverLike:
        if self._retriever is None:
            self._retriever = self._retriever_factory()
        return self._retriever

    async def search(self, query: str) -> str:
        cleaned_query = query.strip()
        if not cleaned_query:
            return NO_EVIDENCE_MESSAGE
        try:
            nodes = await self._get_retriever().aretrieve(cleaned_query)
        except KnowledgeConfigurationError:
            raise
        except Exception as exc:
            raise KnowledgeRetrievalError("知识库检索暂时不可用。") from exc
        if not nodes:
            return NO_EVIDENCE_MESSAGE
        return self.format_evidence(nodes[: self._settings.knowledge_top_k])

    @staticmethod
    def format_evidence(nodes: list[NodeWithScore]) -> str:
        lines = ["知识库检索到以下证据："]
        for index, item in enumerate(nodes, start=1):
            source = str(item.node.metadata.get("source", "未知文档"))
            section = str(item.node.metadata.get("section", "未知章节"))
            score = f"{item.score:.4f}" if item.score is not None else "unknown"
            content = item.node.get_content().strip()
            lines.extend(
                [
                    f"[{index}] [{source} > {section}] 相关度: {score}",
                    content,
                ]
            )
        return "\n".join(lines)
