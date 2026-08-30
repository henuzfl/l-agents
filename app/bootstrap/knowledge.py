from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.knowledge import KnowledgeDocumentService, KnowledgeSearchService


def build_knowledge_search_service(settings: Settings) -> KnowledgeSearchService:
    return KnowledgeSearchService(settings)


def build_knowledge_document_service(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
) -> KnowledgeDocumentService:
    return KnowledgeDocumentService(settings, session_maker=sessions)
