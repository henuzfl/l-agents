from agents import Agent, FunctionTool, Model

from .prompt import KNOWLEDGE_AGENT_INSTRUCTIONS


def create_knowledge_agent(
    model: str | Model,
    knowledge_search_tool: FunctionTool,
) -> Agent[None]:
    return Agent(
        name="knowledge_agent",
        instructions=KNOWLEDGE_AGENT_INSTRUCTIONS,
        model=model,
        tools=[knowledge_search_tool],
    )
