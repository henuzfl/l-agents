from dataclasses import dataclass

from agents import Agent, Model

from app.agents.agent2 import create_agent2
from app.agents.agent3 import create_agent3
from app.agents.agent4 import create_agent4
from app.agents.knowledge_agent import create_knowledge_agent
from app.agents.manager import create_manager_agent
from app.chat.execution_events import publish_nested_agent_event
from app.knowledge import KnowledgeSearchService, create_knowledge_search_tool


@dataclass(frozen=True)
class AgentResources:
    manager: Agent[None]
    knowledge: Agent[None]
    agent2: Agent[None]
    agent3: Agent[None]
    agent4: Agent[None]


def build_agents(model: Model, knowledge_service: KnowledgeSearchService) -> AgentResources:
    knowledge = create_knowledge_agent(
        model,
        create_knowledge_search_tool(knowledge_service),
    )
    agent2 = create_agent2(model)
    agent3 = create_agent3(model)
    agent4 = create_agent4(model)
    manager = create_manager_agent(
        model,
        knowledge,
        agent2,
        agent3,
        agent4,
        on_stream=publish_nested_agent_event,
    )
    return AgentResources(manager, knowledge, agent2, agent3, agent4)
