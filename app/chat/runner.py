from collections.abc import AsyncIterator
from typing import Any, Protocol

from agents import Agent, RunConfig
from agents.memory import Session


class RunResult(Protocol):
    final_output: Any


class StreamingRunResult(Protocol):
    final_output: Any
    current_agent: Agent[Any]

    def stream_events(self) -> AsyncIterator[object]: ...

    def cancel(self, mode: str = "immediate") -> None: ...


class AgentRunner(Protocol):
    async def run(
        self,
        starting_agent: Agent[None],
        input: str,
        *,
        session: Session,
        run_config: RunConfig | None = None,
    ) -> RunResult: ...

    def run_streamed(
        self,
        starting_agent: Agent[None],
        input: str,
        *,
        session: Session,
        run_config: RunConfig | None = None,
    ) -> StreamingRunResult: ...
