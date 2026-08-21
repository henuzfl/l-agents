from app.agents.agent2 import create_agent2
from app.agents.agent2.prompt import AGENT2_FIXED_RESPONSE, AGENT2_INSTRUCTIONS


def test_agent2_is_stateless_and_has_fixed_prompt() -> None:
    agent = create_agent2("test-model")
    assert agent.name == "agent2"
    assert AGENT2_FIXED_RESPONSE == "这是 agent2 的固定返回结果。"
    assert AGENT2_FIXED_RESPONSE in AGENT2_INSTRUCTIONS
    assert agent.tools == []
    assert not hasattr(agent, "session")
