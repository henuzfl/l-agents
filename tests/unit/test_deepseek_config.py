from pathlib import Path

from agents import OpenAIChatCompletionsModel

from app.container import Container
from app.core.config import Settings


def test_container_builds_deepseek_chat_completions_model(tmp_path: Path) -> None:
    settings = Settings(
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
        sqlite_session_path=tmp_path / "sessions.db",
    )
    container = Container(settings)
    assert isinstance(container.model, OpenAIChatCompletionsModel)
    assert container.model.model == "deepseek-chat"
    assert str(container.deepseek_client.base_url) == "https://api.deepseek.com"
    assert [tool.name for tool in container.knowledge_agent.tools] == ["search_knowledge_base"]
    assert container.agent2.tools == []
    assert container.agent3.tools == []
    assert container.agent4.tools == []
