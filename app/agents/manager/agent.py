from collections.abc import Callable
from typing import Any

from agents import Agent, AgentToolStreamEvent, Model

from .prompt import MANAGER_INSTRUCTIONS


def create_manager_agent(
    model: str | Model,
    knowledge_agent: Agent[None],
    agent2: Agent[None],
    agent3: Agent[None],
    agent4: Agent[None],
    on_stream: Callable[[AgentToolStreamEvent], Any] | None = None,
) -> Agent[None]:
    return Agent(
        name="manager",
        instructions=MANAGER_INSTRUCTIONS,
        model=model,
        tools=[
            knowledge_agent.as_tool(
                "run_knowledge_agent",
                "调用无状态知识检索 Agent，回答项目架构、配置和使用方式问题。",
                on_stream=on_stream,
            ),
            agent2.as_tool(
                "run_agent2", "调用无状态 agent2 并返回其固定文本。", on_stream=on_stream
            ),
            agent3.as_tool(
                "run_agent3", "调用无状态 agent3 并返回其固定文本。", on_stream=on_stream
            ),
            agent4.as_tool(
                "run_agent4", "调用无状态 agent4 并返回其固定文本。", on_stream=on_stream
            ),
        ],
    )
