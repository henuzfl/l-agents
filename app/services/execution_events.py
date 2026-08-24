from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from agents import AgentToolStreamEvent

NestedEventSink = Callable[[AgentToolStreamEvent], Awaitable[None]]

_nested_event_sink: ContextVar[NestedEventSink | None] = ContextVar(
    "nested_agent_event_sink",
    default=None,
)


async def publish_nested_agent_event(payload: AgentToolStreamEvent) -> None:
    """Forward nested Agent.as_tool events to the currently active request, if any."""
    sink = _nested_event_sink.get()
    if sink is not None:
        await sink(payload)


def bind_nested_event_sink(sink: NestedEventSink) -> Any:
    return _nested_event_sink.set(sink)


def reset_nested_event_sink(token: Any) -> None:
    _nested_event_sink.reset(token)
