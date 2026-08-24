from agents import Agent, FunctionTool, Model

from .prompt import AGENT1_INSTRUCTIONS


def create_agent1(model: str | Model, knowledge_search_tool: FunctionTool) -> Agent[None]:
    return Agent(
        name="agent1",
        instructions=AGENT1_INSTRUCTIONS,
        model=model,
        tools=[knowledge_search_tool],
    )
