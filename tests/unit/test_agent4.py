from app.agents.agent4 import create_agent4
from app.agents.agent4.prompt import AGENT4_FIXED_RESPONSE, AGENT4_INSTRUCTIONS


def test_agent4_is_stateless_and_has_fixed_prompt() -> None:
    agent = create_agent4("test-model")
    assert agent.name == "agent4"
    assert AGENT4_FIXED_RESPONSE == "这是 agent4 的固定返回结果。"
    assert AGENT4_FIXED_RESPONSE in AGENT4_INSTRUCTIONS
    assert agent.tools == []
    assert not hasattr(agent, "session")
