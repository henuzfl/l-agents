import asyncio

from agents import OpenAIChatCompletionsModel, Runner
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.agent2 import create_agent2
from app.agents.agent3 import create_agent3
from app.agents.agent4 import create_agent4
from app.agents.knowledge_agent import create_knowledge_agent
from app.agents.manager import create_manager_agent
from app.auth import AuthService
from app.core.config import Settings
from app.database import create_app_async_engine, create_app_sync_engine
from app.knowledge import (
    KnowledgeDocumentService,
    KnowledgeSearchService,
    create_knowledge_search_tool,
)
from app.memory import (
    DeepSeekMemorySummarizer,
    SessionFactory,
    ShortTermMemoryOptimizer,
    ShortTermMemorySettings,
    SummaryStore,
)
from app.services import ChatService
from app.services.execution_events import publish_nested_agent_event


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.async_engine = create_app_async_engine(settings)
        self.sync_engine = create_app_sync_engine(settings)
        self.db_sessions = async_sessionmaker(
            self.async_engine, class_=AsyncSession, expire_on_commit=False
        )
        api_key = (
            settings.deepseek_api_key.get_secret_value()
            if settings.deepseek_api_key is not None
            else "missing-deepseek-api-key"
        )
        self.deepseek_client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.deepseek_base_url,
        )
        self.model = OpenAIChatCompletionsModel(
            model=settings.deepseek_model,
            openai_client=self.deepseek_client,
        )
        self.knowledge_search_service = KnowledgeSearchService(settings)
        self.knowledge_document_service = KnowledgeDocumentService(
            settings, database_engine=self.sync_engine
        )
        self.knowledge_search_tool = create_knowledge_search_tool(self.knowledge_search_service)
        self.knowledge_agent = create_knowledge_agent(self.model, self.knowledge_search_tool)
        self.agent2 = create_agent2(self.model)
        self.agent3 = create_agent3(self.model)
        self.agent4 = create_agent4(self.model)
        self.manager_agent = create_manager_agent(
            self.model,
            self.knowledge_agent,
            self.agent2,
            self.agent3,
            self.agent4,
            on_stream=publish_nested_agent_event,
        )
        self.session_factory = SessionFactory(self.async_engine)
        memory_optimizer = None
        if settings.short_term_memory_enabled:
            memory_optimizer = ShortTermMemoryOptimizer(
                SummaryStore(self.db_sessions),
                DeepSeekMemorySummarizer(
                    self.deepseek_client,
                    settings.deepseek_model,
                    settings.short_term_summary_target_tokens,
                ),
                ShortTermMemorySettings(
                    context_max_tokens=settings.short_term_context_max_tokens,
                    summary_target_tokens=settings.short_term_summary_target_tokens,
                    recent_turns=settings.short_term_recent_turns,
                    min_recent_turns=settings.short_term_min_recent_turns,
                    summary_batch_turns=settings.short_term_summary_batch_turns,
                    single_message_max_tokens=settings.short_term_single_message_max_tokens,
                    fallback_turns=settings.short_term_fallback_turns,
                ),
            )
        self.chat_service = ChatService(
            self.manager_agent,
            self.session_factory,
            Runner,
            memory_optimizer,
        )
        self.auth_service = AuthService(settings, self.db_sessions)

    async def startup(self) -> None:
        await asyncio.to_thread(self.knowledge_document_service.recover_interrupted_jobs)
        await self.auth_service.seed_demo_users()

    async def shutdown(self) -> None:
        await self.async_engine.dispose()
        self.sync_engine.dispose()
