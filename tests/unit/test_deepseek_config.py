import pytest
from agents import OpenAIChatCompletionsModel
from pydantic import ValidationError

from app.container import Container
from app.core.config import Settings


def test_container_builds_deepseek_chat_completions_model() -> None:
    settings = Settings(
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
    )
    container = Container(settings)
    assert isinstance(container.model, OpenAIChatCompletionsModel)
    assert container.model.model == "deepseek-chat"
    assert str(container.deepseek_client.base_url) == "https://api.deepseek.com"
    assert [tool.name for tool in container.knowledge_agent.tools] == ["search_knowledge_base"]
    assert container.agent2.tools == []
    assert container.agent3.tools == []
    assert container.agent4.tools == []
    assert container.chat_service._memory_optimizer is not None


def test_short_term_memory_configuration_rejects_invalid_window() -> None:
    with pytest.raises(ValidationError, match="MIN_RECENT_TURNS"):
        Settings(short_term_recent_turns=2, short_term_min_recent_turns=3)
