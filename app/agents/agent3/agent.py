from agents import Agent, Model

from .prompt import AGENT3_INSTRUCTIONS


def create_agent3(model: str | Model) -> Agent[None]:
    return Agent(name="agent3", instructions=AGENT3_INSTRUCTIONS, model=model)
