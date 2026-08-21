from agents import OpenAIChatCompletionsModel, Runner
from openai import AsyncOpenAI

from app.agents.agent1 import create_agent1
from app.agents.agent2 import create_agent2
from app.agents.agent3 import create_agent3
from app.agents.agent4 import create_agent4
from app.agents.manager import create_manager_agent
from app.core.config import Settings
from app.memory import SessionFactory
from app.services import ChatService


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
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
        self.agent1 = create_agent1(self.model)
        self.agent2 = create_agent2(self.model)
        self.agent3 = create_agent3(self.model)
        self.agent4 = create_agent4(self.model)
        self.manager_agent = create_manager_agent(
            self.model,
            self.agent1,
            self.agent2,
            self.agent3,
            self.agent4,
        )
        self.session_factory = SessionFactory(settings.sqlite_session_path)
        self.chat_service = ChatService(self.manager_agent, self.session_factory, Runner)
