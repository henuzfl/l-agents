from agents import function_tool

from app.agents.agent1 import create_agent1
from app.agents.agent1.prompt import AGENT1_INSTRUCTIONS


@function_tool
async def search_knowledge_base(query: str) -> str:
    """Return fake project knowledge evidence."""
    return query


def test_agent1_is_stateless_and_has_only_knowledge_tool() -> None:
    agent = create_agent1("test-model", search_knowledge_base)
    assert agent.name == "agent1"
    assert "必须调用 search_knowledge_base" in AGENT1_INSTRUCTIONS
    assert [tool.name for tool in agent.tools] == ["search_knowledge_base"]
    assert not hasattr(agent, "session")
