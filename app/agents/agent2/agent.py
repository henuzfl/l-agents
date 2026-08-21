from agents import Agent, Model

from .prompt import AGENT2_INSTRUCTIONS


def create_agent2(model: str | Model) -> Agent[None]:
    return Agent(name="agent2", instructions=AGENT2_INSTRUCTIONS, model=model)
