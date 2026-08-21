from app.agents.agent1 import create_agent1
from app.agents.agent2 import create_agent2
from app.agents.agent3 import create_agent3
from app.agents.agent4 import create_agent4
from app.agents.manager import create_manager_agent


def test_manager_registers_agents_as_named_tools() -> None:
    manager = create_manager_agent(
        "test-model",
        create_agent1("test-model"),
        create_agent2("test-model"),
        create_agent3("test-model"),
        create_agent4("test-model"),
    )
    assert manager.name == "manager"
    assert [tool.name for tool in manager.tools] == [
        "run_agent1",
        "run_agent2",
        "run_agent3",
        "run_agent4",
    ]
