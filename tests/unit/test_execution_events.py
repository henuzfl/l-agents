import asyncio

import pytest
from agents import Agent, AgentToolStreamEvent, AgentUpdatedStreamEvent

from app.services.execution_events import (
    bind_nested_event_sink,
    publish_nested_agent_event,
    reset_nested_event_sink,
)


@pytest.mark.asyncio
async def test_nested_event_sinks_are_isolated_between_concurrent_requests() -> None:
    barrier = asyncio.Barrier(2)

    async def collect(agent_name: str) -> list[str]:
        received: list[str] = []

        async def sink(payload: AgentToolStreamEvent) -> None:
            received.append(payload["agent"].name)

        token = bind_nested_event_sink(sink)
        agent = Agent(name=agent_name, model="test-model")
        try:
            await barrier.wait()
            await publish_nested_agent_event(
                {
                    "event": AgentUpdatedStreamEvent(new_agent=agent),
                    "agent": agent,
                    "tool_call": None,
                }
            )
        finally:
            reset_nested_event_sink(token)
        return received

    first, second = await asyncio.gather(collect("knowledge_agent"), collect("agent2"))

    assert first == ["knowledge_agent"]
    assert second == ["agent2"]
