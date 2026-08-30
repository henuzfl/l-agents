from agents import Runner

from app.auth import AuthService
from app.bootstrap.agents import AgentResources, build_agents
from app.bootstrap.auth import build_auth_service
from app.bootstrap.database import DatabaseResources, build_database_resources
from app.bootstrap.knowledge import (
    build_knowledge_document_service,
    build_knowledge_search_service,
)
from app.bootstrap.models import ModelResources, build_model_resources
from app.chat import ChatService
from app.core.config import Settings
from app.knowledge import KnowledgeDocumentService, KnowledgeSearchService
from app.memory import (
    DeepSeekMemorySummarizer,
    SessionFactory,
    ShortTermMemoryOptimizer,
    ShortTermMemorySettings,
    SummaryStore,
)


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.database: DatabaseResources = build_database_resources(settings)
        self.models: ModelResources = build_model_resources(settings)
        self.knowledge_search_service: KnowledgeSearchService = (
            build_knowledge_search_service(settings)
        )
        self.knowledge_document_service: KnowledgeDocumentService = (
            build_knowledge_document_service(settings, self.database.sessions)
        )
        self.agents: AgentResources = build_agents(
            self.models.model,
            self.knowledge_search_service,
        )
        self.chat_service = ChatService(
            self.agents.manager,
            SessionFactory(self.database.async_engine),
            Runner,
            self._build_memory_optimizer(),
        )
        self.auth_service: AuthService = build_auth_service(settings, self.database.sessions)

        # Compatibility attributes for callers that previously accessed resources directly.
        self.async_engine = self.database.async_engine
        self.db_sessions = self.database.sessions
        self.deepseek_client = self.models.client
        self.model = self.models.model
        self.manager_agent = self.agents.manager
        self.knowledge_agent = self.agents.knowledge
        self.agent2 = self.agents.agent2
        self.agent3 = self.agents.agent3
        self.agent4 = self.agents.agent4

    def _build_memory_optimizer(self) -> ShortTermMemoryOptimizer | None:
        if not self.settings.short_term_memory_enabled:
            return None
        return ShortTermMemoryOptimizer(
            SummaryStore(self.database.sessions),
            DeepSeekMemorySummarizer(
                self.models.client,
                self.settings.deepseek_model,
                self.settings.short_term_summary_target_tokens,
            ),
            ShortTermMemorySettings(
                context_max_tokens=self.settings.short_term_context_max_tokens,
                summary_target_tokens=self.settings.short_term_summary_target_tokens,
                recent_turns=self.settings.short_term_recent_turns,
                min_recent_turns=self.settings.short_term_min_recent_turns,
                summary_batch_turns=self.settings.short_term_summary_batch_turns,
                single_message_max_tokens=self.settings.short_term_single_message_max_tokens,
                fallback_turns=self.settings.short_term_fallback_turns,
            ),
        )

    async def startup(self) -> None:
        await self.knowledge_document_service.recover_interrupted_jobs()
        await self.auth_service.seed_demo_users()

    async def shutdown(self) -> None:
        await self.database.async_engine.dispose()
