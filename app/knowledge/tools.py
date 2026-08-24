from agents import FunctionTool, function_tool

from app.core.exceptions import KnowledgeConfigurationError, KnowledgeRetrievalError

from .service import KnowledgeSearchService


def create_knowledge_search_tool(service: KnowledgeSearchService) -> FunctionTool:
    @function_tool(
        name_override="search_knowledge_base",
        description_override=(
            "检索项目使用手册。仅用于项目架构、Agent、Session、配置、启动、接口和开发命令问题。"
        ),
    )
    async def search_knowledge_base(query: str) -> str:
        """Search the internal project manual for evidence relevant to the query."""
        try:
            return await service.search(query)
        except (KnowledgeConfigurationError, KnowledgeRetrievalError) as exc:
            return str(exc)

    return search_knowledge_base
