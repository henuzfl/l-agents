from app.agents.agent1 import create_agent1
from app.agents.agent1.prompt import AGENT1_FIXED_RESPONSE, AGENT1_INSTRUCTIONS


def test_agent1_is_stateless_and_has_fixed_prompt() -> None:
    agent = create_agent1("test-model")
    assert agent.name == "agent1"
    assert AGENT1_FIXED_RESPONSE == "这是 agent1 的固定返回结果。"
    assert AGENT1_FIXED_RESPONSE in AGENT1_INSTRUCTIONS
    assert agent.tools == []
    assert not hasattr(agent, "session")
