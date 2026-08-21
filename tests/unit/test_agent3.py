from app.agents.agent3 import create_agent3
from app.agents.agent3.prompt import AGENT3_FIXED_RESPONSE, AGENT3_INSTRUCTIONS


def test_agent3_is_stateless_and_has_fixed_prompt() -> None:
    agent = create_agent3("test-model")
    assert agent.name == "agent3"
    assert AGENT3_FIXED_RESPONSE == "这是 agent3 的固定返回结果。"
    assert AGENT3_FIXED_RESPONSE in AGENT3_INSTRUCTIONS
    assert agent.tools == []
    assert not hasattr(agent, "session")
