from agents import Agent, RunItemStreamEvent, ToolCallItem, ToolCallOutputItem

from app.services.stream_events import SafeTraceMapper


def test_trace_mapper_redacts_tool_arguments_and_outputs() -> None:
    manager = Agent(name="manager", model="test-model")
    mapper = SafeTraceMapper(0.0)
    call = ToolCallItem(
        agent=manager,
        raw_item={
            "type": "function_call",
            "name": "run_knowledge_agent",
            "call_id": "call-1",
            "arguments": "TOP-SECRET-INPUT",
        },
    )
    output = ToolCallOutputItem(
        agent=manager,
        raw_item={
            "type": "function_call_output",
            "call_id": "call-1",
            "output": "TOP-SECRET-OUTPUT",
        },
        output="TOP-SECRET-OUTPUT",
    )

    called = mapper.map(
        RunItemStreamEvent(name="tool_called", item=call),
        scope="outer",
        agent_name="manager",
    )
    completed = mapper.map(
        RunItemStreamEvent(name="tool_output", item=output),
        scope="outer",
        agent_name="manager",
    )

    serialized = f"{called}{completed}"
    assert called is not None and called["tool"] == "run_knowledge_agent"
    assert completed is not None and completed["status"] == "completed"
    assert "TOP-SECRET" not in serialized


def test_trace_mapper_deduplicates_sdk_events() -> None:
    manager = Agent(name="manager", model="test-model")
    mapper = SafeTraceMapper(0.0)
    item = ToolCallItem(
        agent=manager,
        raw_item={"type": "function_call", "name": "run_agent2", "call_id": "same"},
    )
    event = RunItemStreamEvent(name="tool_called", item=item)

    assert mapper.map(event, scope="outer", agent_name="manager") is not None
    assert mapper.map(event, scope="outer", agent_name="manager") is None


def test_trace_mapper_deduplicates_parallel_views_of_same_tool_lifecycle() -> None:
    agent = Agent(name="knowledge_agent", model="test-model")
    mapper = SafeTraceMapper(0.0)
    first = ToolCallItem(
        agent=agent,
        raw_item={"type": "function_call", "name": "search_knowledge_base", "call_id": "a"},
    )
    duplicate = ToolCallItem(
        agent=agent,
        raw_item={"type": "function_call", "name": "search_knowledge_base", "call_id": "b"},
    )

    assert mapper.map(
        RunItemStreamEvent(name="tool_called", item=first),
        scope="nested:knowledge_agent",
        agent_name="knowledge_agent",
    ) is not None
    assert mapper.map(
        RunItemStreamEvent(name="tool_called", item=duplicate),
        scope="nested:knowledge_agent",
        agent_name="knowledge_agent",
    ) is None
