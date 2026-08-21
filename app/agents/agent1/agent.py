from agents import Agent, Model

from .prompt import AGENT1_INSTRUCTIONS


def create_agent1(model: str | Model) -> Agent[None]:
    return Agent(name="agent1", instructions=AGENT1_INSTRUCTIONS, model=model)
