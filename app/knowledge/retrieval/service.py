from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import quote

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeWithScore

from app.core.config import Settings
from app.core.exceptions import KnowledgeConfigurationError, KnowledgeRetrievalError
from app.knowledge.storage import LlamaIndexKnowledgeStore

from .events import EvidenceItem, publish_retrieval_evidence

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
        selected = self.order_nodes(nodes[: self._settings.knowledge_top_k])
        await publish_retrieval_evidence(self.build_evidence(selected))
        return self.format_evidence(selected)

    @staticmethod
    def _document_key(item: NodeWithScore) -> str:
        metadata = item.node.metadata
        return str(metadata.get("minio_object") or metadata.get("source") or "未知文档")

    @staticmethod
    def _order_number(metadata: dict[str, Any], key: str) -> int:
        value = metadata.get(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 1_000_000_000

    @classmethod
    def order_nodes(cls, nodes: list[NodeWithScore]) -> list[NodeWithScore]:
        document_rank: dict[str, int] = {}
        ranked = list(enumerate(nodes))
        for relevance_rank, item in ranked:
            document_rank.setdefault(cls._document_key(item), relevance_rank)

        def order_key(entry: tuple[int, NodeWithScore]) -> tuple[int, int, int, int, int]:
            relevance_rank, item = entry
            metadata = item.node.metadata
            return (
                document_rank[cls._document_key(item)],
                cls._order_number(metadata, "page_number"),
                cls._order_number(metadata, "element_index"),
                cls._order_number(metadata, "element_part"),
                relevance_rank,
            )

        return [item for _, item in sorted(ranked, key=order_key)]

    @staticmethod
    def _task_id(metadata: dict[str, Any]) -> str | None:
        explicit = metadata.get("task_id")
        if explicit:
            return str(explicit)
        object_name = str(metadata.get("minio_object", ""))
        parts = object_name.split("/")
        return parts[3] if len(parts) >= 5 else None

    @classmethod
    def build_evidence(cls, nodes: list[NodeWithScore]) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []
        for item in nodes:
            metadata = item.node.metadata
            node_id = str(item.node.node_id)
            task_id = cls._task_id(metadata)
            has_asset = bool(metadata.get("asset_object"))
            asset_url = None
            download_url = None
            if task_id:
                encoded_task = quote(task_id, safe="")
                download_url = f"/api/v1/knowledge/documents/{encoded_task}/download"
                if has_asset:
                    asset_url = (
                        f"/api/v1/knowledge/documents/{encoded_task}/chunks/"
                        f"{quote(node_id, safe='')}/asset"
                    )
            evidence.append(
                {
                    "node_id": node_id,
                    "source": str(metadata.get("source", "未知文档")),
                    "section": str(metadata.get("section", "未知章节")),
                    "page_number": metadata.get("page_number"),
                    "element_type": str(metadata.get("element_type", "text")),
                    "element_index": metadata.get("element_index"),
                    "element_part": metadata.get("element_part"),
                    "language": metadata.get("language"),
                    "content": item.node.get_content().strip(),
                    "score": item.score,
                    "minio_object": metadata.get("minio_object"),
                    "task_id": task_id,
                    "asset_url": asset_url,
                    "download_url": download_url,
                }
            )
        return evidence

    @classmethod
    def merge_evidence(cls, items: list[EvidenceItem]) -> list[EvidenceItem]:
        unique: list[EvidenceItem] = []
        seen: set[str] = set()
        document_rank: dict[str, int] = {}
        for item in items:
            node_id = str(item.get("node_id", ""))
            if not node_id or node_id in seen:
                continue
            seen.add(node_id)
            document_key = str(item.get("minio_object") or item.get("source") or "未知文档")
            document_rank.setdefault(document_key, len(document_rank))
            unique.append(item)

        def order_key(item: EvidenceItem) -> tuple[int, int, int, int]:
            document_key = str(item.get("minio_object") or item.get("source") or "未知文档")
            return (
                document_rank[document_key],
                cls._order_number(item, "page_number"),
                cls._order_number(item, "element_index"),
                cls._order_number(item, "element_part"),
            )

        return sorted(unique, key=order_key)

    @staticmethod
    def format_evidence(nodes: list[NodeWithScore]) -> str:
        lines = ["知识库检索到以下证据（同一文档内已按原文顺序排列）："]
        for index, item in enumerate(nodes, start=1):
            source = str(item.node.metadata.get("source", "未知文档"))
            section = str(item.node.metadata.get("section", "未知章节"))
            element_type = str(item.node.metadata.get("element_type", ""))
            location = f"{source} > {section}"
            if element_type:
                location = f"{location} · {element_type}"
            score = f"{item.score:.4f}" if item.score is not None else "unknown"
            content = item.node.get_content().strip()
            lines.extend([f"[{index}] [{location}] 相关度: {score}", content])
        return "\n".join(lines)

__all__ = ["KnowledgeSearchService", "NO_EVIDENCE_MESSAGE", "RetrieverLike"]
