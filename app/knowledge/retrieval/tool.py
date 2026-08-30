from agents import FunctionTool, function_tool

from app.core.exceptions import KnowledgeConfigurationError, KnowledgeRetrievalError
from app.knowledge.retrieval.service import KnowledgeSearchService


def create_knowledge_search_tool(service: KnowledgeSearchService) -> FunctionTool:
    @function_tool(
        name_override="search_knowledge_base",
        description_override=(
            "检索已上传的知识库文档。返回相关证据，并将同一文档的多个分片按原文顺序排列。"
        ),
    )
    async def search_knowledge_base(query: str) -> str:
        """Search uploaded knowledge-base documents for source-ordered evidence."""
        try:
            return await service.search(query)
        except (KnowledgeConfigurationError, KnowledgeRetrievalError) as exc:
            return str(exc)

    return search_knowledge_base

__all__ = ["create_knowledge_search_tool"]
