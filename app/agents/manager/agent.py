from agents import Agent, Model

from .prompt import MANAGER_INSTRUCTIONS


def create_manager_agent(
    model: str | Model,
    agent1: Agent[None],
    agent2: Agent[None],
    agent3: Agent[None],
    agent4: Agent[None],
) -> Agent[None]:
    return Agent(
        name="manager",
        instructions=MANAGER_INSTRUCTIONS,
        model=model,
        tools=[
            agent1.as_tool("run_agent1", "调用无状态 agent1 并返回其固定文本。"),
            agent2.as_tool("run_agent2", "调用无状态 agent2 并返回其固定文本。"),
            agent3.as_tool("run_agent3", "调用无状态 agent3 并返回其固定文本。"),
            agent4.as_tool("run_agent4", "调用无状态 agent4 并返回其固定文本。"),
        ],
    )
