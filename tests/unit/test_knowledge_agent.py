from agents import function_tool

from app.agents.knowledge_agent import create_knowledge_agent
from app.agents.knowledge_agent.prompt import KNOWLEDGE_AGENT_INSTRUCTIONS


@function_tool
async def search_knowledge_base(query: str) -> str:
    """Return fake project knowledge evidence."""
    return query


def test_knowledge_agent_is_stateless_and_has_only_knowledge_tool() -> None:
    agent = create_knowledge_agent("test-model", search_knowledge_base)
    assert agent.name == "knowledge_agent"
    assert "必须调用 search_knowledge_base" in KNOWLEDGE_AGENT_INSTRUCTIONS
    assert [tool.name for tool in agent.tools] == ["search_knowledge_base"]
    assert not hasattr(agent, "session")
