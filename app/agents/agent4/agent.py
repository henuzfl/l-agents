from agents import Agent, Model

from .prompt import AGENT4_INSTRUCTIONS


def create_agent4(model: str | Model) -> Agent[None]:
    return Agent(name="agent4", instructions=AGENT4_INSTRUCTIONS, model=model)
